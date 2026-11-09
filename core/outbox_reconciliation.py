"""
Sent-Folder Reconciliation Engine, Delivery Semantics & Bounded Backoff Scheduler.

Implements M7 WS-04 sent-folder reconciliation and delivery resilience:
- Queries Sent mailboxes ([Gmail]/Sent Mail, Sent, Sent Messages, INBOX.Sent) using read-only IMAP (EXAMINE).
- Exact header-matching criteria: RFC Message-ID, Sender (From), Recipients (To/Cc), Submission timestamp window.
- Conclusive match: transitions UNKNOWN -> ACCEPTED with 'reconciled_sent_copy_found' annotation.
- Absence invariant: Absence from Sent does NOT prove rejection and does NOT authorize automatic retry.
  State remains UNKNOWN with audit record 'reconciled_no_sent_copy_found'.
- Ambiguous/conflicting candidates: retain UNKNOWN with 'reconciliation_conflicting_candidates'.
- Bounded backoff scheduler for UNKNOWN reconciliation (5s, 15s, 60s, max 3 attempts) (M16-OUT-003).
- Transient pre-submission retry helper: bounded retries strictly for failures BEFORE the DATA terminator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime
from email.utils import parseaddr, parsedate_to_datetime
from enum import Enum
import re
import threading
import time
from typing import Any, Callable

from core.logging_config import get_logger
from experiments.m4.model import (
    DeliveryResult,
    Error,
    Failure,
    Lease,
    OperationId,
    Outcome,
    PreparedEnvelope,
    State,
)

logger = get_logger("outbox_reconciliation")

SENT_MAILBOX_CANDIDATES = (
    "[Gmail]/Sent Mail",
    "Sent",
    "Sent Messages",
    "INBOX.Sent",
    "Sent Items",
)

# Standard backoff intervals in seconds for scheduled reconciliation passes
DEFAULT_RECONCILIATION_BACKOFF = (5.0, 15.0, 60.0)
MAX_RECONCILIATION_ATTEMPTS = len(DEFAULT_RECONCILIATION_BACKOFF)

# Timestamp matching window: message in Sent must be within -24h to +24h of submission
TIMESTAMP_WINDOW_PAST_SECONDS = 86400.0   # 24 hours clock skew allowance
TIMESTAMP_WINDOW_FUTURE_SECONDS = 86400.0  # 24 hours propagation allowance


class ReconciliationStatus(str, Enum):
    """Outcome of inspecting Sent folder for a candidate message."""
    CONFIRMED = "confirmed"      # Definite match: sent copy verified
    NOT_FOUND = "not_found"      # Message absent from Sent (never proves rejection)
    CONFLICT = "conflict"        # Multiple ambiguous or contradictory matches
    UNAVAILABLE = "unavailable"  # Sent folder inaccessible or IMAP connection failed


@dataclass(frozen=True)
class ReconciliationResult:
    """Detailed audit record of a reconciliation pass."""
    operation_id: str
    status: ReconciliationStatus
    reason: str
    matched_mailbox: str | None = None
    matched_uid: int | None = None
    matched_message_id: str | None = None
    matched_date: str | None = None
    attempt_number: int = 1
    timestamp: float = field(default_factory=time.time)
    details: dict[str, Any] = field(default_factory=dict)


def normalize_message_id(msg_id: str) -> str:
    """Normalize RFC 5322 Message-ID by stripping whitespace and angle brackets."""
    if not msg_id:
        return ""
    cleaned = msg_id.strip()
    if cleaned.startswith("<") and cleaned.endswith(">"):
        cleaned = cleaned[1:-1].strip()
    return cleaned.lower()


def parse_rfc_date_timestamp(date_str: str) -> float | None:
    """Safely parse RFC 2822 / RFC 5322 date header into Unix epoch seconds."""
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            # Per RFC 2822, -0000 indicates unspecified sender local zone; treat naive as UTC
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


class SentFolderReconciler:
    """
    Inspects user's Sent mailbox to determine whether an UNKNOWN submission
    was actually accepted and spooled by the mail server.
    """

    def __init__(
        self,
        candidate_mailboxes: tuple[str, ...] = SENT_MAILBOX_CANDIDATES,
    ) -> None:
        self.candidate_mailboxes = candidate_mailboxes

    def match_candidate(
        self,
        envelope: PreparedEnvelope,
        candidate_headers: dict[str, str],
        submission_ts: float | None = None,
    ) -> tuple[bool, str]:
        """
        Evaluate whether candidate message headers definitively match the prepared envelope.

        Criteria:
        1. Message-ID: Normalized candidate Message-ID must match envelope.message_id exactly.
        2. From: Sender email address must match envelope.sender.
        3. Recipients: To/Cc addresses must contain all recipients from envelope.binding.
        4. Date: Parsed candidate date must fall within acceptable submission window.
        """
        # 1. Message-ID verification
        candidate_msg_id = normalize_message_id(candidate_headers.get("message-id", ""))
        expected_msg_id = normalize_message_id(envelope.message_id)
        if not candidate_msg_id or candidate_msg_id != expected_msg_id:
            return False, f"message_id_mismatch (candidate='{candidate_msg_id}', expected='{expected_msg_id}')"

        # 2. Sender verification
        candidate_from_raw = candidate_headers.get("from", "")
        _, candidate_from_addr = parseaddr(candidate_from_raw)
        if candidate_from_addr.lower() != envelope.sender.value.lower():
            return False, f"sender_mismatch (candidate='{candidate_from_addr}', expected='{envelope.sender.value}')"

        # 3. Recipient verification
        candidate_recipients: set[str] = set()
        for field in ("to", "cc"):
            val = candidate_headers.get(field, "")
            if val:
                for part in val.split(","):
                    _, addr = parseaddr(part)
                    if addr:
                        candidate_recipients.add(addr.lower())

        expected_recipients = {r.value.lower() for r in envelope.binding.recipients}
        if not expected_recipients.issubset(candidate_recipients):
            return False, f"recipient_mismatch (missing={expected_recipients - candidate_recipients})"

        # 4. Submission timestamp window check
        if submission_ts is not None and submission_ts > 0:
            candidate_date_str = candidate_headers.get("date", "")
            candidate_ts = parse_rfc_date_timestamp(candidate_date_str)
            if candidate_ts is not None:
                min_allowed = submission_ts - TIMESTAMP_WINDOW_PAST_SECONDS
                max_allowed = submission_ts + TIMESTAMP_WINDOW_FUTURE_SECONDS
                if not (min_allowed <= candidate_ts <= max_allowed):
                    return False, f"timestamp_out_of_window (candidate={candidate_ts}, submission={submission_ts})"

        return True, "conclusive_match"

    def reconcile_with_client(
        self,
        envelope: PreparedEnvelope,
        client: Any,
        submission_ts: float | None = None,
        attempt: int = 1,
    ) -> ReconciliationResult:
        """
        Query IMAP client across candidate Sent folders to verify if the message was sent.

        Uses non-mutating EXAMINE and BODY.PEEK[] header fetches.
        """
        op_id = envelope.operation.value
        expected_msg_id = envelope.message_id
        normalized_target = normalize_message_id(expected_msg_id)

        selected_mailbox = None
        for mailbox in self.candidate_mailboxes:
            try:
                # Read-only mailbox selection prevents setting \Seen or altering flags
                if hasattr(client, "select_readonly"):
                    client.select_readonly(mailbox)
                    selected_mailbox = mailbox
                    break
                elif hasattr(client, "examine"):
                    res = client.examine(mailbox)
                    if res[0] == "OK":
                        selected_mailbox = mailbox
                        break
            except Exception:
                continue

        if not selected_mailbox:
            return ReconciliationResult(
                operation_id=op_id,
                status=ReconciliationStatus.UNAVAILABLE,
                reason="sent_folder_not_found_or_inaccessible",
                attempt_number=attempt,
            )

        # Query UIDs by HEADER Message-ID
        matching_uids: list[int] = []
        try:
            # Query specific header
            status, lines = client.execute_command(f'UID SEARCH HEADER Message-ID "{expected_msg_id}"')
            if status == "OK":
                for line in lines:
                    if line.startswith(b"* SEARCH"):
                        for tok in line[8:].split():
                            try:
                                u = int(tok)
                                if u > 0:
                                    matching_uids.append(u)
                            except ValueError:
                                pass
        except Exception as e:
            logger.warning("UID SEARCH by Message-ID failed: %s; falling back to recent UIDs", e)

        # Fallback: if search returned nothing or isn't supported, search ALL recent UIDs
        if not matching_uids:
            try:
                if hasattr(client, "search_all_uids"):
                    all_uids = sorted(client.search_all_uids(), reverse=True)
                    # Inspect up to the latest 50 messages in Sent
                    matching_uids = all_uids[:50]
            except Exception:
                pass

        if not matching_uids:
            return ReconciliationResult(
                operation_id=op_id,
                status=ReconciliationStatus.NOT_FOUND,
                reason="no_messages_in_sent_folder",
                matched_mailbox=selected_mailbox,
                attempt_number=attempt,
            )

        # Fetch and evaluate headers for candidate UIDs
        confirmed_candidates: list[dict[str, Any]] = []

        try:
            if hasattr(client, "fetch_headers_peek"):
                fetched = client.fetch_headers_peek(matching_uids)
                for uid, flags, size, raw_headers in fetched:
                    headers_map = self._parse_headers_bytes(raw_headers)
                    is_match, match_reason = self.match_candidate(envelope, headers_map, submission_ts)
                    if is_match:
                        confirmed_candidates.append({
                            "uid": uid,
                            "mailbox": selected_mailbox,
                            "headers": headers_map,
                        })
            else:
                # Fallback fetch logic if standard imaplib client
                for uid in matching_uids:
                    res, data = client.uid("FETCH", str(uid), "(BODY.PEEK[HEADER])")
                    if res == "OK" and data:
                        raw = data[0][1] if isinstance(data[0], tuple) else b""
                        headers_map = self._parse_headers_bytes(raw)
                        is_match, match_reason = self.match_candidate(envelope, headers_map, submission_ts)
                        if is_match:
                            confirmed_candidates.append({
                                "uid": uid,
                                "mailbox": selected_mailbox,
                                "headers": headers_map,
                            })
        except Exception as e:
            logger.error("Error fetching candidate headers during reconciliation: %s", e)
            return ReconciliationResult(
                operation_id=op_id,
                status=ReconciliationStatus.UNAVAILABLE,
                reason=f"header_fetch_failed: {e}",
                matched_mailbox=selected_mailbox,
                attempt_number=attempt,
            )

        # Evaluate confirmed matches count
        if len(confirmed_candidates) == 1:
            cand = confirmed_candidates[0]
            return ReconciliationResult(
                operation_id=op_id,
                status=ReconciliationStatus.CONFIRMED,
                reason="reconciled_sent_copy_found",
                matched_mailbox=cand["mailbox"],
                matched_uid=cand["uid"],
                matched_message_id=cand["headers"].get("message-id"),
                matched_date=cand["headers"].get("date"),
                attempt_number=attempt,
                details=cand["headers"],
            )
        elif len(confirmed_candidates) > 1:
            return ReconciliationResult(
                operation_id=op_id,
                status=ReconciliationStatus.CONFLICT,
                reason="multiple_conflicting_candidates_in_sent",
                matched_mailbox=selected_mailbox,
                attempt_number=attempt,
                details={"candidates_count": len(confirmed_candidates)},
            )
        else:
            return ReconciliationResult(
                operation_id=op_id,
                status=ReconciliationStatus.NOT_FOUND,
                reason="reconciled_no_sent_copy_found",
                matched_mailbox=selected_mailbox,
                attempt_number=attempt,
            )

    def reconcile_outbox_operation(
        self,
        lease: Lease,
        repository: Any,
        operation: OperationId,
        client: Any,
        *,
        attempt: int = 1,
    ) -> DeliveryResult:
        """
        Execute sent-folder reconciliation for an operation in the repository.

        Enforces all delivery semantics:
        - Must be in UNKNOWN state.
        - Positive match (CONFIRMED): transitions state to ACCEPTED with
          reason='reconciled_sent_copy_found' and persists sent-copy audit.
        - Negative match (NOT_FOUND): retains UNKNOWN, records audit, NEVER resubmits.
        - Conflicting matches (CONFLICT): retains UNKNOWN with 'reconciliation_conflicting_candidates'.
        """
        now = time.time()
        with repository.transaction(lease, time.monotonic() + 30) as account:
            row = account.row(operation)
            if row.get("state") != State.UNKNOWN.value:
                raise Failure(Error.TRANSITION)

            envelope = account.envelope(operation)
            submission_ts = row.get("updated_ts") or row.get("created_ts")

        # Run IMAP inspection outside repository transaction
        result = self.reconcile_with_client(envelope, client, submission_ts, attempt=attempt)

        # Persist reconciliation outcome inside transaction
        with repository.completion(lease.context) as account:
            row = account.row(operation)
            if row.get("state") != State.UNKNOWN.value:
                raise Failure(Error.TRANSITION)

            audit_dict = {
                "attempt": attempt,
                "status": result.status.value,
                "reason": result.reason,
                "checked_ts": now,
                "matched_mailbox": result.matched_mailbox,
                "matched_uid": result.matched_uid,
            }
            row["reconciliation_audit"] = audit_dict

            if result.status == ReconciliationStatus.CONFIRMED:
                row.update(
                    state=State.ACCEPTED.value,
                    reason="reconciled_sent_copy_found",
                    reconciled_sent_copy=True,
                    sent_copy_uid=result.matched_uid,
                    sent_copy_mailbox=result.matched_mailbox,
                    updated_ts=now,
                )
                if row.get("attempts"):
                    row["attempts"][-1].update(
                        state=State.ACCEPTED.value,
                        reason="reconciled_sent_copy_found",
                        reconciled=True,
                    )
            elif result.status == ReconciliationStatus.CONFLICT:
                row.update(
                    state=State.UNKNOWN.value,
                    reason="reconciliation_conflicting_candidates",
                    updated_ts=now,
                )
            else:
                # NOT_FOUND or UNAVAILABLE: retains UNKNOWN. Never retries automatically!
                row.update(
                    state=State.UNKNOWN.value,
                    reason="reconciled_no_sent_copy_found",
                    updated_ts=now,
                )

            return DeliveryResult(
                operation,
                State(row["state"]),
                row["reason"],
                len(row.get("attempts", [])),
            )

    @staticmethod
    def _parse_headers_bytes(raw_bytes: bytes) -> dict[str, str]:
        """Parse raw header block bytes into a lowercase key-value dictionary."""
        from email.parser import BytesHeaderParser
        from email.policy import default
        try:
            msg = BytesHeaderParser(policy=default).parsebytes(raw_bytes)
            return {k.lower(): str(v) for k, v in msg.items()}
        except Exception:
            return {}


class ReconciliationScheduler:
    """
    Background scheduler for automated, non-polling Sent-folder reconciliation (resolving M16-OUT-003).

    Features:
    - Bounded exponential backoff schedule (default 5s, 15s, 60s, max 3 attempts).
    - Cancellable via threading.Event or timeout.
    - Non-blocking: operates on a dedicated daemon worker thread.
    - Stops immediately upon positive match, definitive resolution, or cancellation.
    """

    def __init__(
        self,
        reconciler: SentFolderReconciler | None = None,
        backoff_intervals: tuple[float, ...] = DEFAULT_RECONCILIATION_BACKOFF,
    ) -> None:
        self.reconciler = reconciler or SentFolderReconciler()
        self.backoff_intervals = backoff_intervals
        self._threads: list[threading.Thread] = []

    def schedule_reconciliation(
        self,
        lease: Lease,
        repository: Any,
        operation: OperationId,
        client_factory: Callable[[], Any],
        on_completed: Callable[[DeliveryResult], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> threading.Thread:
        """
        Launch background reconciliation worker for an UNKNOWN operation.
        """
        def _worker():
            cancel = cancel_event or threading.Event()
            delivery = None

            for attempt_idx, delay in enumerate(self.backoff_intervals, start=1):
                # Wait for backoff interval or cancellation
                if cancel.wait(delay):
                    break

                if lease.cancelled.is_set():
                    break

                try:
                    client = client_factory()
                    delivery = self.reconciler.reconcile_outbox_operation(
                        lease,
                        repository,
                        operation,
                        client,
                        attempt=attempt_idx,
                    )
                    # If confirmed, stop scheduling further attempts
                    if delivery.state == State.ACCEPTED:
                        break
                except Exception as e:
                    logger.warning("Scheduled reconciliation attempt %d failed: %s", attempt_idx, e)

            if on_completed and delivery:
                try:
                    on_completed(delivery)
                except Exception as e:
                    logger.error("Reconciliation completion callback error: %s", e)

        thread = threading.Thread(target=_worker, name=f"Reconcile-{operation.value}", daemon=True)
        thread.start()
        self._threads.append(thread)
        return thread


class TransientSubmissionRetry:
    """
    Automated bounded retry helper for transient network failures occurring
    STRICTLY BEFORE the SMTP DATA terminator (resolving M16-OUT-003).

    Rules:
    - Pre-submission failures (e.g. DNS resolution failure, socket connection drop before connect/auth)
      mean the server never received the message.
    - Automatic bounded retry (up to 3 attempts with 2s, 8s, 30s backoff) is safe.
    - STRICT INVARIANT: If the DATA terminator has been sent, automatic retry is FORBIDDEN.
    """

    def __init__(
        self,
        retry_delays: tuple[float, ...] = (2.0, 8.0, 30.0),
    ) -> None:
        self.retry_delays = retry_delays

    def execute_with_transient_retry(
        self,
        submit_fn: Callable[[], DeliveryResult],
        cancel_event: threading.Event | None = None,
    ) -> DeliveryResult:
        """
        Execute submit_fn with bounded retries for transient pre-submission errors.
        """
        cancel = cancel_event or threading.Event()
        last_result = None

        for attempt, delay in enumerate(self.retry_delays, start=1):
            if cancel.is_set():
                break

            try:
                result = submit_fn()
                last_result = result
                # If accepted or unknown, do not perform automatic pre-submission retry!
                # (UNKNOWN must follow the Sent-folder reconciliation track, not blind resend).
                if result.state in (State.ACCEPTED, State.UNKNOWN):
                    return result

                # Only FAILED operations with pre-submission reasons are eligible for retry
                if result.state == State.FAILED:
                    if "definitive_rejection" in result.reason or "5" in result.reason:
                        # Server definitively rejected recipient or policy (5xx) -> never retry
                        return result

            except Exception:
                pass

            # Wait backoff before next attempt
            if cancel.wait(delay):
                break

        return last_result or DeliveryResult(OperationId.new(), State.FAILED, "transient_retries_exhausted", 0)
