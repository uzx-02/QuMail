"""
Durable Outbox State Machine, Lifecycle Management & Delivery Semantics.

Implements the M7 WS-04 durable outbox architecture:
- Explicit state machine: DRAFT, PREPARED, SUBMITTING, ACCEPTED, UNKNOWN, FAILED.
- Plain-language user-facing status labels and explanations (WS-05 integration contract).
- Invariant: Server acceptance is NEVER equated with recipient delivery.
- Crash-safe boundary recovery: in-flight disconnects and crashes recover to UNKNOWN.
- Mandatory invariant: UNKNOWN is NEVER automatically retried across restarts or background workers.
- Explicit single-attempt retry authorization with duplicate risk acknowledgment.
- Single-flight per-operation concurrency locking preventing double-sends.
- Outbox capacity expansion to 256 operations with FIFO pruning of old ACCEPTED receipts (M16-OUT-002).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
import hashlib
import time
from typing import Any, Callable, ContextManager

from experiments.m3.types import AccountContext, EmailAddress, KeyHandle
from experiments.m4.codec import pack, unpack
from experiments.m4.model import (
    Binding,
    CredentialHandle,
    DeliveryResult,
    Error,
    Failure,
    Lease,
    OperationId,
    Outcome,
    PreparedEnvelope,
    State,
)
from experiments.m4.ownership import worker_lock

# Configurable capacity constants (resolving M16-OUT-002)
DEFAULT_MAX_OUTBOX_OPERATIONS = 256
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_PRUNE_AGE_SECONDS = 30 * 86400  # 30 days


class OutboxState(str, Enum):
    """Explicit outbox lifecycle states."""
    DRAFT = "Draft"
    PREPARED = "Prepared"
    SUBMITTING = "Submitting"
    ACCEPTED = "Accepted"
    UNKNOWN = "Unknown"
    FAILED = "Failed"


# Plain-language user-facing mappings (WS-05 integration contract)
USER_FACING_STATUS_LABELS: dict[str, str] = {
    OutboxState.DRAFT.value: "Draft saved locally",
    OutboxState.PREPARED.value: "Queued for secure sending",
    OutboxState.SUBMITTING.value: "Sending to mail server...",
    OutboxState.ACCEPTED.value: "Accepted by your mail server",
    OutboxState.UNKNOWN.value: "Could not confirm whether this message was sent",
    OutboxState.FAILED.value: "Submission failed",
}

USER_FACING_STATUS_DETAILS: dict[str, str] = {
    OutboxState.DRAFT.value: "Draft is stored securely in your local encrypted vault.",
    OutboxState.PREPARED.value: "Message has been encrypted and signed. Ready for transmission.",
    OutboxState.SUBMITTING.value: "Connecting to server and transmitting encrypted payload.",
    OutboxState.ACCEPTED.value: "Your email provider accepted the message for delivery. Delivery to recipient mailboxes depends on remote servers.",
    OutboxState.UNKNOWN.value: "Network connection was interrupted after sending. The server may or may not have accepted the message. Check Sent Mail or authorize a retry with duplicate risk.",
    OutboxState.FAILED.value: "The mail server definitively rejected the message before transmission completed.",
}


@dataclass(frozen=True)
class OutboxItem:
    """Application-level presentation model for an outbox entry."""
    operation_id: str
    account_id: str
    message_id: str
    state: OutboxState
    reason: str
    attempts_count: int
    created_ts: float
    updated_ts: float
    status_label: str
    status_detail: str
    can_retry: bool
    requires_duplicate_ack: bool
    reconciled_sent_copy: bool
    sender: str = ""
    recipients: tuple[str, ...] = ()
    digest: str = ""
    reconciliation_audit: dict[str, Any] | None = None

    @classmethod
    def from_row(cls, operation: OperationId, row: dict[str, Any]) -> OutboxItem:
        state_str = row.get("state", OutboxState.DRAFT.value)
        try:
            state = OutboxState(state_str)
        except ValueError:
            state = OutboxState.UNKNOWN

        reason = row.get("reason", "")
        attempts = row.get("attempts", [])
        attempts_count = len(attempts)
        reconciled = bool(row.get("reconciled_sent_copy", False))

        # Determine user-facing labels
        if reconciled and state == OutboxState.ACCEPTED:
            label = "A sent copy was found"
            detail = "Verified in your Sent folder. Your mail server accepted and recorded the message."
        elif state == OutboxState.UNKNOWN:
            label = USER_FACING_STATUS_LABELS[OutboxState.UNKNOWN.value]
            detail = USER_FACING_STATUS_DETAILS[OutboxState.UNKNOWN.value] + " Retrying may send a duplicate."
        else:
            label = USER_FACING_STATUS_LABELS.get(state.value, state.value)
            detail = USER_FACING_STATUS_DETAILS.get(state.value, reason)

        can_retry = state in (OutboxState.FAILED, OutboxState.UNKNOWN) and attempts_count < DEFAULT_MAX_ATTEMPTS
        requires_duplicate_ack = state == OutboxState.UNKNOWN

        # Extract metadata from prepared data if available
        prepared_data = row.get("prepared", {})
        recipients = tuple(prepared_data.get("recipients", []))
        sender = prepared_data.get("sender", "")
        digest = prepared_data.get("digest", "")

        return cls(
            operation_id=operation.value,
            account_id=str(row.get("account", "")),
            message_id=str(row.get("message_id", "")),
            state=state,
            reason=reason,
            attempts_count=attempts_count,
            created_ts=float(row.get("created_ts", 0.0)),
            updated_ts=float(row.get("updated_ts", 0.0)),
            status_label=label,
            status_detail=detail,
            can_retry=can_retry,
            requires_duplicate_ack=requires_duplicate_ack,
            reconciled_sent_copy=reconciled,
            sender=sender,
            recipients=recipients,
            digest=digest,
            reconciliation_audit=row.get("reconciliation_audit"),
        )


class OutboxManager:
    """
    Manager for durable outbox operations, capacity management, crash recovery,
    and single-flight submission locking.
    """

    def __init__(
        self,
        repository: Any,
        transport: Any | None = None,
        max_operations: int = DEFAULT_MAX_OUTBOX_OPERATIONS,
        allow_external: bool = False,
    ) -> None:
        if transport is not None and not (
            allow_external is True
            or getattr(transport, "simulation_only", False) is True
            or getattr(transport, "loopback_only", False) is True
        ):
            raise Failure(Error.TRANSPORT)
        self.repository = repository
        self.transport = transport
        self.max_operations = max_operations

    def inspect_item(self, lease: Lease, operation: OperationId) -> OutboxItem:
        """Inspect a specific outbox item and return its presentation model."""
        with self.repository.transaction(lease, time.monotonic() + 30) as account:
            row = account.row(operation)
            return OutboxItem.from_row(operation, row)

    def list_items(self, lease: Lease) -> tuple[OutboxItem, ...]:
        """List all outbox items for the account ordered by creation time."""
        with self.repository.transaction(lease, time.monotonic() + 30) as account:
            items = []
            for op_id_str, row in account.records.items():
                items.append(OutboxItem.from_row(OperationId(op_id_str), row))
            # Sort newest first by created_ts
            items.sort(key=lambda x: x.created_ts or 0.0, reverse=True)
            return tuple(items)

    def recover(self, lease: Lease) -> tuple[OperationId, ...]:
        """
        Scan for in-flight operations left in SUBMITTING (e.g. from crash or abrupt exit).

        Transitions them to UNKNOWN with reason 'interrupted_acceptance_unknown'.
        MANDATORY INVARIANT: Never resubmits or retries automatically!
        """
        recovered: list[OperationId] = []
        now = time.time()
        with self.repository.transaction(lease, time.monotonic() + 30) as account:
            pending = [
                OperationId(i)
                for i, r in account.records.items()
                if r.get("state") == State.SUBMITTING.value
            ]

        for operation in pending:
            try:
                with self.repository.ownership(lease.context, operation):
                    with self.repository.transaction(lease, time.monotonic() + 30) as account:
                        row = account.row(operation)
                        if row.get("state") == State.SUBMITTING.value:
                            row.update(
                                state=State.UNKNOWN.value,
                                reason="interrupted_acceptance_unknown",
                                updated_ts=now,
                            )
                            if row.get("attempts"):
                                row["attempts"][-1].update(
                                    state=State.UNKNOWN.value,
                                    reason="interrupted_acceptance_unknown",
                                    ended_ts=now,
                                )
                            recovered.append(operation)
            except Failure as error:
                if error.code is not Error.BUSY:
                    raise

        return tuple(recovered)

    def authorize_retry(
        self,
        lease: Lease,
        operation: OperationId,
        *,
        acknowledge_duplicate_risk: bool = False,
    ) -> None:
        """
        Explicitly authorize a single resubmission attempt for a FAILED or UNKNOWN operation.

        - If state is FAILED: authorized without duplicate risk warning.
        - If state is UNKNOWN: STRICTLY REQUIRES acknowledge_duplicate_risk=True.
          Otherwise raises Failure(Error.DUPLICATE).
        - Transitions state back to PREPARED.
        - Preserves exact frozen ciphertext, message_id, and digest.
        """
        now = time.time()
        with self.repository.transaction(lease, time.monotonic() + 30) as account:
            row = account.row(operation)
            current_state = row.get("state")

            if current_state not in (State.FAILED.value, State.UNKNOWN.value):
                raise Failure(Error.TRANSITION)

            if current_state == State.UNKNOWN.value and acknowledge_duplicate_risk is not True:
                raise Failure(Error.DUPLICATE)

            if len(row.get("attempts", [])) >= DEFAULT_MAX_ATTEMPTS:
                raise Failure(Error.LIMIT)

            # Re-verify that prepared envelope matches current account binding
            account.check_prepared(account.envelope(operation))

            row.update(
                state=State.PREPARED.value,
                reason="explicit_retry_authorized",
                user_authorized_retry=True,
                duplicate_warning_acknowledged=bool(acknowledge_duplicate_risk),
                updated_ts=now,
            )

    def submit(
        self,
        lease: Lease,
        operation: OperationId,
        *,
        until: float | None = None,
    ) -> DeliveryResult:
        """
        Execute durable submission of a PREPARED message.

        Enforces boundary safety:
        - Acquires per-operation lock (worker_lock) preventing concurrent sends.
        - Pre-submission commit transitions state to SUBMITTING.
        - If transport fails before DATA terminator: definitive failure -> FAILED.
        - If transport fails after DATA terminator or while awaiting response -> UNKNOWN.
        - If completion commit fails or aborts -> evaluates to UNKNOWN.
        """
        if self.transport is None:
            raise Failure(Error.TRANSPORT)

        until = (time.monotonic() + 30) if until is None else until
        now = time.time()

        with self.repository.ownership(lease.context, operation):
            # 1. Pre-submission transition to SUBMITTING inside transaction
            with self.repository.transaction(lease, until) as account:
                row = account.row(operation)
                if row.get("state") != State.PREPARED.value:
                    raise Failure(Error.TRANSITION)
                if len(row.get("attempts", [])) >= DEFAULT_MAX_ATTEMPTS:
                    raise Failure(Error.LIMIT)

                envelope = account.envelope(operation)
                account.check_prepared(envelope)

                credential = CredentialHandle(lease.context)
                attempt_id = OperationId.new().value
                attempt_entry = {
                    "number": len(row.get("attempts", [])) + 1,
                    "identity": attempt_id,
                    "state": State.SUBMITTING.value,
                    "reason": "submission_intent_committed",
                    "digest": envelope.digest,
                    "started_ts": now,
                }
                row.setdefault("attempts", []).append(attempt_entry)
                row.update(
                    state=State.SUBMITTING.value,
                    reason="submission_intent_committed",
                    updated_ts=now,
                )
                attempt_num = len(row["attempts"])

            # 2. Check cancellation before touching transport
            if lease.cancelled.is_set() or time.monotonic() >= until:
                return DeliveryResult(
                    operation,
                    State.UNKNOWN,
                    "recover_durable_submission_intent",
                    attempt_num,
                )

            # 3. Transport submission outside transaction
            try:
                outcome = self.transport.submit(envelope, credential, lease.cancelled, until)
            except Exception:
                outcome = Outcome.UNKNOWN

            if type(outcome) is not Outcome:
                outcome = Outcome.UNKNOWN

            state_map = {
                Outcome.ACCEPTED: (State.ACCEPTED, "server_accepted_not_delivered"),
                Outcome.REJECTED: (State.FAILED, "definitive_rejection_or_stopped_before_data"),
                Outcome.UNKNOWN: (State.UNKNOWN, "acceptance_unknown_duplicate_risk"),
            }
            target_state, target_reason = state_map[outcome]
            finished_ts = time.time()

            # 4. Completion commit inside short transaction
            try:
                with self.repository.completion(lease.context) as account:
                    row = account.row(operation)
                    if (
                        row.get("state") != State.SUBMITTING.value
                        or row.get("attempts", [{}])[-1].get("identity") != attempt_id
                    ):
                        raise Failure(Error.TRANSITION)
                    row.update(
                        state=target_state.value,
                        reason=target_reason,
                        updated_ts=finished_ts,
                    )
                    row["attempts"][-1].update(
                        state=target_state.value,
                        reason=target_reason,
                        ended_ts=finished_ts,
                    )
                    return DeliveryResult(
                        operation,
                        State(row["state"]),
                        row["reason"],
                        len(row["attempts"]),
                    )
            except Failure:
                return DeliveryResult(
                    operation,
                    State.UNKNOWN,
                    "recover_durable_submission_intent",
                    attempt_num,
                )

    def prune_accepted(
        self,
        lease: Lease,
        *,
        max_retain: int = DEFAULT_MAX_OUTBOX_OPERATIONS,
        max_age_seconds: float = DEFAULT_PRUNE_AGE_SECONDS,
    ) -> int:
        """
        Prune old ACCEPTED operations to manage outbox capacity (resolving M16-OUT-002).

        Rules:
        - NEVER prunes DRAFT, PREPARED, SUBMITTING, UNKNOWN, or FAILED operations.
        - Only prunes operations in ACCEPTED state.
        - Deletes oldest ACCEPTED records (FIFO by updated_ts/created_ts) if count > max_retain,
          or if older than max_age_seconds.
        - Returns count of pruned operations.
        """
        pruned_count = 0
        now = time.time()
        with self.repository.transaction(lease, time.monotonic() + 30) as account:
            records = account.records

            # Identify candidates for pruning: strictly ACCEPTED
            accepted_keys = [
                k for k, r in records.items()
                if r.get("state") == State.ACCEPTED.value
            ]

            # Sort oldest first by updated_ts or created_ts
            accepted_keys.sort(
                key=lambda k: records[k].get("updated_ts") or records[k].get("created_ts") or 0.0
            )

            to_delete: list[str] = []

            # 1. Check age threshold (only if positive max_age_seconds provided)
            if max_age_seconds > 0:
                for k in accepted_keys:
                    ts = records[k].get("updated_ts") or records[k].get("created_ts") or 0.0
                    if ts > 0 and (now - ts) > max_age_seconds:
                        to_delete.append(k)

            # 2. Check capacity limit
            total_after_age = len(records) - len(to_delete)
            if total_after_age > max_retain:
                remaining_accepted = [k for k in accepted_keys if k not in to_delete]
                excess = total_after_age - max_retain
                to_delete.extend(remaining_accepted[:excess])

            for k in to_delete:
                del records[k]
                pruned_count += 1

        return pruned_count

    def ensure_capacity_for_new_draft(self, lease: Lease) -> None:
        """
        Ensure space is available for creating a new draft by pruning oldest ACCEPTED
        records if queue size approaches or equals max_operations.
        """
        with self.repository.transaction(lease, time.monotonic() + 30) as account:
            if len(account.records) < self.max_operations:
                return

        # Try pruning ACCEPTED records
        self.prune_accepted(lease, max_retain=self.max_operations - 1, max_age_seconds=0.0)

        # Re-check capacity
        with self.repository.transaction(lease, time.monotonic() + 30) as account:
            if len(account.records) >= self.max_operations:
                raise Failure(Error.LIMIT)
