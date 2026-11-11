"""
Comprehensive Tests for QuMail M7 — Module 1.6 WS-04:
Durable Outbox, Sent-Folder Reconciliation & Delivery Resilience.

Covers:
- Section 1: Durable Outbox State Machine & Plain-Language Lifecycle (WS-05 Integration Contract).
- Section 2: Boundary Safety & Crash Recovery (Interrupted In-Flight & Zero Automatic Retry Invariant).
- Section 3: Explicit Retry Authorization & Duplicate Protection.
- Section 4: Single-Flight Per-Operation Concurrency Locking.
- Section 5: Outbox Capacity Expansion & FIFO Pruning of Accepted Receipts (M16-OUT-002).
- Section 6: Sent-Folder Reconciliation Engine (M16-OUT-001) - Matching, Absence, Conflict, Skew.
- Section 7: Bounded Backoff Scheduler & Transient Pre-Submission Retry (M16-OUT-003).
- Section 8: Zero-Network Isolation & Sensitive Data Scrubbing.
"""

from __future__ import annotations

from email.message import EmailMessage
from email.utils import formatdate, parsedate_to_datetime
import hashlib
from pathlib import Path
import threading
import time
from typing import Any
import unittest.mock

import pytest

from core.outbox_manager import (
    DEFAULT_MAX_OUTBOX_OPERATIONS,
    OutboxItem,
    OutboxManager,
    OutboxState,
    USER_FACING_STATUS_DETAILS,
    USER_FACING_STATUS_LABELS,
)
from core.outbox_reconciliation import (
    ReconciliationResult,
    ReconciliationScheduler,
    ReconciliationStatus,
    SentFolderReconciler,
    TransientSubmissionRetry,
    normalize_message_id,
    parse_rfc_date_timestamp,
)
from core.vault import identity
from core.vault.types import BoundaryError, Code as M3Code, EmailAddress, KeyHandle, UserId
from core.vault.vault import Vault
from core.outbox.codec import pack, unpack
from core.outbox.model import (
    AccountAccess,
    Binding,
    CredentialHandle,
    DeliveryResult,
    Error as M4Error,
    Failure as M4Failure,
    Lease,
    OperationId,
    Outcome,
    PreparedEnvelope,
    State,
)
from core.outbox.vault_adapter import VaultOutbox
from core.crypto_envelope.model import Attachment, Budget, Draft
from core.crypto_envelope.provider import Provider as M5Provider
from core.crypto_envelope.services import Compose
from mailbox_client.workflows import Workflows

ROOT = Path(__file__).resolve().parents[1]
from core.provider_resolver import resolve_provider
M3_PROVIDER_BIN = resolve_provider("qumail-m3-provider")
M5_PROVIDER_BIN = resolve_provider("qumail-m5-provider")


# =============================================================================
# In-Memory Isolation Fixtures (Strict Zero-Network)
# =============================================================================

class IsolatedMemoryStore:
    """In-memory key-value store for master vault secrets; bypasses Windows Credential Manager."""
    def __init__(self):
        self._data = {}
    def put(self, ident: str, secret: bytes):
        if len(secret) != 32: raise BoundaryError(M3Code.INVALID)
        self._data[ident] = bytes(secret)
    def get(self, ident: str) -> bytes:
        if ident not in self._data: raise BoundaryError(M3Code.STORE)
        return self._data[ident]
    def delete(self, ident: str):
        self._data.pop(ident, None)


@pytest.fixture
def crypto_env(tmp_path):
    """Sets up Alice and Bob inside an isolated SQLite vault with enrolled identities."""
    from core.vault.provider import Provider as M3Provider
    p_m3 = M3Provider(M3_PROVIDER_BIN)
    p_m5 = M5Provider(M5_PROVIDER_BIN)
    vault_path = tmp_path / "ws04_vault.sqlite"
    vault = Vault.create(vault_path, IsolatedMemoryStore(), p_m3)

    def make_ident(name: str):
        addr = f"{name}@example.invalid"
        return identity.validated_google_claims(
            dict(
                iss="https://accounts.google.com", aud="test-client", sub=name,
                email=addr, hd="example.invalid", email_verified=True, nonce="n"*32,
                exp=int(time.time()) + 3600
            ),
            "test-client", "n"*32
        )

    id_alice = make_ident("alice")
    ctx_alice, key_alice = vault.enroll(id_alice, id_alice.addresses[0], UserId.new())

    id_bob = make_ident("bob")
    ctx_bob, key_bob = vault.enroll(id_bob, id_bob.addresses[0], UserId.new())

    root_bob = vault.import_contact(ctx_alice, EmailAddress("bob@example.invalid"), vault.export_public(ctx_bob, key_bob))
    vault.pin_contact(ctx_alice, EmailAddress("bob@example.invalid"), root_bob, "in-person")

    root_alice = vault.import_contact(ctx_bob, EmailAddress("alice@example.invalid"), vault.export_public(ctx_alice, key_alice))
    vault.pin_contact(ctx_bob, EmailAddress("alice@example.invalid"), root_alice, "in-person")

    # Store synthetic OAuth token on Alice's account for transport qualification
    vault.store_oauth(ctx_alice, id_alice, dict(access_token="simulated-test-token", expiry=int(time.time()) + 3600))

    access = AccountAccess()

    return {
        "vault": vault,
        "access": access,
        "p_m3": p_m3,
        "p_m5": p_m5,
        "alice": (ctx_alice, key_alice, "alice@example.invalid"),
        "bob": (ctx_bob, key_bob, "bob@example.invalid"),
    }


class ControlledTransport:
    """Mock protocol transport that can simulate success, definitive rejection, or ambiguous in-flight drops."""
    simulation_only = True

    def __init__(self, outcome: Outcome = Outcome.ACCEPTED, delay: float = 0.0):
        self.outcome = outcome
        self.delay = delay
        self.submitted_envelopes: list[PreparedEnvelope] = []
        self.entered_event = threading.Event()

    def submit(self, envelope: PreparedEnvelope, credential: CredentialHandle, cancel: threading.Event, deadline: float) -> Outcome:
        self.submitted_envelopes.append(envelope)
        self.entered_event.set()
        if self.delay > 0:
            time.sleep(self.delay)
        if cancel.is_set():
            return Outcome.UNKNOWN
        return self.outcome


class MockIMAPSentClient:
    """Mock IMAP protocol client with simulated Sent folder and search capabilities."""
    def __init__(self, initial_messages: list[dict[str, Any]] | None = None, available_folders: list[str] | None = None):
        self.available_folders = available_folders if available_folders is not None else ["[Gmail]/Sent Mail"]
        self.selected_mailbox: str | None = None
        self.messages: dict[int, dict[str, Any]] = {}
        self.command_log: list[str] = []

        if initial_messages:
            for idx, msg in enumerate(initial_messages, start=1):
                self.messages[idx] = msg

    def select_readonly(self, mailbox: str) -> int:
        self.command_log.append(f"EXAMINE {mailbox}")
        if mailbox in self.available_folders:
            self.selected_mailbox = mailbox
            return 123456
        raise ValueError(f"Mailbox {mailbox} not found")

    def execute_command(self, cmd_str: str) -> tuple[str, list[bytes]]:
        self.command_log.append(cmd_str)
        if cmd_str.startswith("UID SEARCH HEADER Message-ID"):
            # Extract target Message-ID
            import re
            m = re.search(r'Message-ID "(.*)"', cmd_str)
            target = m.group(1).strip("<>").strip().lower() if m else ""
            matched_uids = []
            for uid, data in self.messages.items():
                msg_id = data.get("Message-ID", "").strip("<>").strip().lower()
                if msg_id == target:
                    matched_uids.append(uid)
            if matched_uids:
                uids_str = " ".join(str(u) for u in matched_uids)
                return "OK", [f"* SEARCH {uids_str}".encode()]
            return "OK", [b"* SEARCH"]

        elif cmd_str == "UID SEARCH ALL":
            uids_str = " ".join(str(u) for u in sorted(self.messages.keys()))
            return "OK", [f"* SEARCH {uids_str}".encode()]

        return "OK", []

    def fetch_headers_peek(self, uids: list[int]) -> list[tuple[int, list[str], int, bytes]]:
        results = []
        for uid in uids:
            if uid in self.messages:
                data = self.messages[uid]
                msg = EmailMessage()
                for k, v in data.items():
                    msg[k] = v
                raw_bytes = msg.as_bytes()
                results.append((uid, [r"\Seen"], len(raw_bytes), raw_bytes))
        return results

    def search_all_uids(self) -> set[int]:
        return set(self.messages.keys())


# =============================================================================
# Helper function to create prepared messages
# =============================================================================

def create_prepared_message(env: dict[str, Any], text: str = "Test payload") -> tuple[Workflows, Lease, OperationId, PreparedEnvelope]:
    vault, access, p_m5 = env["vault"], env["access"], env["p_m5"]
    ctx_a, key_a, addr_a = env["alice"]
    lease = access.select(ctx_a)
    budget = Budget(threading.Event(), time.monotonic() + 30)

    wf = Workflows(vault, access, p_m5)
    draft = Draft(to=("bob@example.invalid",), cc=(), subject="Test Subject", body=text, attachments=())
    op = wf.save(lease, draft, budget)
    envelope = wf.prepare(lease, op, key_a, budget)
    return wf, lease, op, envelope


# =============================================================================
# SECTION 1: Durable Outbox State Machine & Plain-Language Lifecycle
# =============================================================================

def test_outbox_state_machine_happy_path(crypto_env):
    """
    Verifies normal submission lifecycle:
    DRAFT -> PREPARED -> SUBMITTING -> ACCEPTED.
    Verifies user-facing status mappings (WS-05 Integration Contract):
    - Status label: 'Accepted by your mail server'
    - Status never claims 'delivered to recipient'
    """
    wf, lease, op, envelope = create_prepared_message(crypto_env)
    repo = wf.repository
    manager = OutboxManager(repo, ControlledTransport(Outcome.ACCEPTED))

    # Inspect before submission: PREPARED
    item_prep = manager.inspect_item(lease, op)
    assert item_prep.state == OutboxState.PREPARED
    assert item_prep.status_label == USER_FACING_STATUS_LABELS[OutboxState.PREPARED.value]

    # Execute submission
    result = manager.submit(lease, op)
    assert result.state == State.ACCEPTED
    assert result.reason == "server_accepted_not_delivered"

    # Inspect after submission: ACCEPTED
    item_acc = manager.inspect_item(lease, op)
    assert item_acc.state == OutboxState.ACCEPTED
    assert item_acc.status_label == "Accepted by your mail server"
    assert "delivered to recipient" not in item_acc.status_label.lower()
    assert "delivery to recipient mailboxes depends on remote servers" in item_acc.status_detail.lower()
    assert item_acc.can_retry is False


def test_outbox_state_machine_definitive_rejection(crypto_env):
    """
    Verifies definitive rejection (e.g. 5xx SMTP error):
    Transitions to FAILED.
    - Status label: 'Submission failed'
    - Can retry: True, requires_duplicate_ack: False
    """
    wf, lease, op, envelope = create_prepared_message(crypto_env)
    manager = OutboxManager(wf.repository, ControlledTransport(Outcome.REJECTED))

    result = manager.submit(lease, op)
    assert result.state == State.FAILED
    assert result.reason == "definitive_rejection_or_stopped_before_data"

    item = manager.inspect_item(lease, op)
    assert item.state == OutboxState.FAILED
    assert item.status_label == "Submission failed"
    assert item.can_retry is True
    assert item.requires_duplicate_ack is False


def test_outbox_state_machine_in_flight_ambiguous_unknown(crypto_env):
    """
    Verifies ambiguous in-flight outcome (e.g. lost response after DATA terminator):
    Transitions to UNKNOWN.
    - Status label: 'Could not confirm whether this message was sent'
    - Status detail warns: 'Retrying may send a duplicate.'
    - Can retry: True, requires_duplicate_ack: True
    """
    wf, lease, op, envelope = create_prepared_message(crypto_env)
    manager = OutboxManager(wf.repository, ControlledTransport(Outcome.UNKNOWN))

    result = manager.submit(lease, op)
    assert result.state == State.UNKNOWN
    assert result.reason == "acceptance_unknown_duplicate_risk"

    item = manager.inspect_item(lease, op)
    assert item.state == OutboxState.UNKNOWN
    assert item.status_label == "Could not confirm whether this message was sent"
    assert "Retrying may send a duplicate" in item.status_detail
    assert item.can_retry is True
    assert item.requires_duplicate_ack is True


# =============================================================================
# SECTION 2: Boundary Safety & Crash Recovery
# =============================================================================

def test_crash_recovery_transitions_submitting_to_unknown(crypto_env):
    """
    Verifies that if the application or system crashes while an operation
    is in SUBMITTING, recovery transitions it strictly to UNKNOWN.
    """
    wf, lease, op, envelope = create_prepared_message(crypto_env)
    repo = wf.repository

    # Manually simulate an uncommitted crash during SUBMITTING
    with repo.transaction(lease, time.monotonic() + 10) as account:
        row = account.row(op)
        row.update(state=State.SUBMITTING.value, reason="submission_intent_committed")
        row.setdefault("attempts", []).append({
            "number": 1,
            "identity": "test-attempt-1",
            "state": State.SUBMITTING.value,
            "reason": "submission_intent_committed",
            "started_ts": time.time(),
        })

    # Run recovery
    manager = OutboxManager(repo, None)
    recovered = manager.recover(lease)
    assert op in recovered

    item = manager.inspect_item(lease, op)
    assert item.state == OutboxState.UNKNOWN
    assert item.reason == "interrupted_acceptance_unknown"


def test_mandatory_invariant_zero_automatic_retry_of_unknown(crypto_env):
    """
    MANDATORY INVARIANT:
    UNKNOWN records must NEVER be automatically resubmitted across restarts,
    recoveries, or background polling loops.
    """
    wf, lease, op, envelope = create_prepared_message(crypto_env)
    repo = wf.repository

    # Move to UNKNOWN
    manager = OutboxManager(repo, ControlledTransport(Outcome.UNKNOWN))
    manager.submit(lease, op)

    item_before = manager.inspect_item(lease, op)
    assert item_before.state == OutboxState.UNKNOWN
    assert item_before.attempts_count == 1

    # Simulate 5 subsequent recoveries / startup sweeps
    for _ in range(5):
        recovered = manager.recover(lease)
        # An operation already in UNKNOWN must not be modified
        assert op not in recovered
        item_check = manager.inspect_item(lease, op)
        assert item_check.state == OutboxState.UNKNOWN
        assert item_check.attempts_count == 1  # ZERO resends!


# =============================================================================
# SECTION 3: Explicit Retry Authorization & Duplicate Protection
# =============================================================================

def test_retry_unknown_requires_duplicate_risk_acknowledgment(crypto_env):
    """
    Verifies that retrying an UNKNOWN operation without acknowledge_duplicate_risk=True
    is strictly rejected with Failure(Error.DUPLICATE).
    """
    wf, lease, op, envelope = create_prepared_message(crypto_env)
    manager = OutboxManager(wf.repository, ControlledTransport(Outcome.UNKNOWN))
    manager.submit(lease, op)

    # 1. Attempt retry without acknowledgment -> FAILS
    with pytest.raises(M4Failure) as exc:
        manager.authorize_retry(lease, op, acknowledge_duplicate_risk=False)
    assert exc.value.code == M4Error.DUPLICATE

    # State remains UNKNOWN
    assert manager.inspect_item(lease, op).state == OutboxState.UNKNOWN

    # 2. Attempt retry WITH acknowledgment -> SUCCEEDS
    manager.authorize_retry(lease, op, acknowledge_duplicate_risk=True)

    # State transitions back to PREPARED
    item = manager.inspect_item(lease, op)
    assert item.state == OutboxState.PREPARED
    assert item.reason == "explicit_retry_authorized"


def test_exact_ciphertext_and_digest_preserved_on_retry(crypto_env):
    """
    Verifies that retrying a message preserves the exact original ciphertext,
    message_id, and SHA-256 digest without re-encryption or header mutation.
    """
    wf, lease, op, envelope_orig = create_prepared_message(crypto_env)
    manager = OutboxManager(wf.repository, ControlledTransport(Outcome.REJECTED))
    manager.submit(lease, op)

    # Authorize retry
    manager.authorize_retry(lease, op)

    # Submit second attempt with success
    manager.transport = ControlledTransport(Outcome.ACCEPTED)
    manager.submit(lease, op)

    # Inspect submitted envelope
    envelope_retry = manager.transport.submitted_envelopes[0]
    assert envelope_retry.operation == envelope_orig.operation
    assert envelope_retry.message_id == envelope_orig.message_id
    assert envelope_retry.serialized == envelope_orig.serialized
    assert envelope_retry.digest == envelope_orig.digest


def test_max_attempts_limit_enforced(crypto_env):
    """
    Verifies that after 3 failed attempts, further retries are rejected
    with Failure(Error.LIMIT).
    """
    wf, lease, op, envelope = create_prepared_message(crypto_env)
    manager = OutboxManager(wf.repository, ControlledTransport(Outcome.REJECTED))

    # Attempt 1
    manager.submit(lease, op)
    assert manager.inspect_item(lease, op).attempts_count == 1

    # Attempt 2
    manager.authorize_retry(lease, op)
    manager.submit(lease, op)
    assert manager.inspect_item(lease, op).attempts_count == 2

    # Attempt 3
    manager.authorize_retry(lease, op)
    manager.submit(lease, op)
    assert manager.inspect_item(lease, op).attempts_count == 3

    # Attempt 4 should fail at retry authorization
    with pytest.raises(M4Failure) as exc:
        manager.authorize_retry(lease, op)
    assert exc.value.code == M4Error.LIMIT


# =============================================================================
# SECTION 4: Single-Flight Per-Operation Concurrency Locking
# =============================================================================

def test_concurrent_submission_of_same_operation_blocked(crypto_env):
    """
    Verifies that two workers attempting to submit the same operation concurrently
    are prevented by per-operation worker_lock (second raises Failure(Error.BUSY)).
    """
    wf, lease, op, envelope = create_prepared_message(crypto_env)
    repo = wf.repository

    # Worker 1 starts submission with a delay
    transport1 = ControlledTransport(Outcome.ACCEPTED, delay=0.5)
    manager1 = OutboxManager(repo, transport1)

    worker2_error = None
    def run_worker2():
        nonlocal worker2_error
        # Wait until worker 1 enters
        transport1.entered_event.wait(timeout=2.0)
        manager2 = OutboxManager(repo, ControlledTransport(Outcome.ACCEPTED))
        try:
            manager2.submit(lease, op)
        except M4Failure as e:
            worker2_error = e

    t2 = threading.Thread(target=run_worker2)
    t2.start()

    res1 = manager1.submit(lease, op)
    t2.join(timeout=3.0)

    assert res1.state == State.ACCEPTED
    assert worker2_error is not None
    assert worker2_error.code == M4Error.BUSY


# =============================================================================
# SECTION 5: Outbox Capacity Expansion & FIFO Pruning (M16-OUT-002)
# =============================================================================

def test_outbox_capacity_supports_50_plus_operations(crypto_env):
    """
    Verifies M16-OUT-002:
    Outbox capacity expands beyond the rigid 16-operation limit to 256.
    Queueing 50 operations succeeds cleanly without Failure(Error.LIMIT).
    """
    vault, access, p_m5 = crypto_env["vault"], crypto_env["access"], crypto_env["p_m5"]
    ctx_a, key_a, addr_a = crypto_env["alice"]
    lease = access.select(ctx_a)
    budget = Budget(threading.Event(), time.monotonic() + 30)

    wf = Workflows(vault, access, p_m5)

    created_ops = []
    for i in range(50):
        draft = Draft(to=("bob@example.invalid",), cc=(), subject=f"Bulk Draft {i}", body="payload", attachments=())
        op = wf.save(lease, draft, budget)
        created_ops.append(op)

    assert len(created_ops) == 50
    items = wf.outbox_items(lease, budget)
    assert len(items) >= 50


def test_fifo_pruning_of_accepted_records_never_touches_pending(crypto_env):
    """
    Verifies FIFO pruning logic:
    - Prunes oldest ACCEPTED records.
    - NEVER deletes DRAFT, PREPARED, SUBMITTING, UNKNOWN, or FAILED records.
    """
    vault, access, p_m5 = crypto_env["vault"], crypto_env["access"], crypto_env["p_m5"]
    ctx_a, key_a, addr_a = crypto_env["alice"]
    lease = access.select(ctx_a)
    budget = Budget(threading.Event(), time.monotonic() + 30)

    wf = Workflows(vault, access, p_m5)
    repo = wf.repository
    manager = OutboxManager(repo, ControlledTransport(Outcome.ACCEPTED), max_operations=10)

    # Create 5 ACCEPTED items and 5 DRAFT/PREPARED/UNKNOWN items
    accepted_ops = []
    for i in range(5):
        draft = Draft(to=("bob@example.invalid",), cc=(), subject=f"Acc {i}", body=f"b{i}", attachments=())
        op = wf.save(lease, draft, budget)
        wf.prepare(lease, op, key_a, budget)
        manager.submit(lease, op)
        accepted_ops.append(op)

    # Create 1 DRAFT
    draft_op = wf.save(lease, Draft(to=("bob@example.invalid",), cc=(), subject="Pending Draft", body="b", attachments=()), budget)

    # Create 1 UNKNOWN
    unkn_op = wf.save(lease, Draft(to=("bob@example.invalid",), cc=(), subject="Unkn", body="b", attachments=()), budget)
    wf.prepare(lease, unkn_op, key_a, budget)
    manager_unkn = OutboxManager(repo, ControlledTransport(Outcome.UNKNOWN))
    manager_unkn.submit(lease, unkn_op)

    # Total records = 7. Prune with max_retain=4
    pruned = manager.prune_accepted(lease, max_retain=4, max_age_seconds=0.0)
    assert pruned == 3  # Pruned 3 of the 5 accepted records

    # Verify that DRAFT and UNKNOWN remain intact
    with repo.transaction(lease, time.monotonic() + 10) as account:
        assert draft_op.value in account.records
        assert unkn_op.value in account.records
        # Exactly 2 accepted ops remain + 1 draft + 1 unkn = 4 records
        assert len(account.records) == 4


# =============================================================================
# SECTION 6: Sent-Folder Reconciliation Engine (M16-OUT-001)
# =============================================================================

def test_reconciliation_conclusive_match_in_sent_folder(crypto_env):
    """
    Verifies M16-OUT-001:
    When an UNKNOWN operation's exact Message-ID, sender, recipients, and timestamp
    match a message in the Sent folder:
    - Transitions UNKNOWN -> ACCEPTED.
    - Reason: 'reconciled_sent_copy_found'.
    - Annotation: 'A sent copy was found'.
    """
    wf, lease, op, envelope = create_prepared_message(crypto_env)
    manager = OutboxManager(wf.repository, ControlledTransport(Outcome.UNKNOWN))
    manager.submit(lease, op)

    # Setup simulated Sent folder containing matching message
    sent_msg = {
        "From": envelope.sender.value,
        "To": envelope.binding.recipients[0].value,
        "Subject": "Test Subject",
        "Date": formatdate(time.time()),
        "Message-ID": envelope.message_id,
    }
    mock_imap = MockIMAPSentClient([sent_msg])

    # Execute reconciliation
    reconciler = SentFolderReconciler()
    result = reconciler.reconcile_outbox_operation(lease, wf.repository, op, mock_imap)

    assert result.state == State.ACCEPTED
    assert result.reason == "reconciled_sent_copy_found"

    item = manager.inspect_item(lease, op)
    assert item.state == OutboxState.ACCEPTED
    assert item.reconciled_sent_copy is True
    assert item.status_label == "A sent copy was found"


def test_reconciliation_absence_from_sent_retains_unknown_and_never_auto_retries(crypto_env):
    """
    CRITICAL INVARIANT:
    Absence from Sent folder does NOT prove rejection!
    - Operation remains UNKNOWN.
    - Reason: 'reconciled_no_sent_copy_found'.
    - Invariant: NEVER automatically retries or resends.
    """
    wf, lease, op, envelope = create_prepared_message(crypto_env)
    manager = OutboxManager(wf.repository, ControlledTransport(Outcome.UNKNOWN))
    manager.submit(lease, op)

    # Empty Sent folder
    mock_imap = MockIMAPSentClient([])

    reconciler = SentFolderReconciler()
    result = reconciler.reconcile_outbox_operation(lease, wf.repository, op, mock_imap)

    assert result.state == State.UNKNOWN
    assert result.reason == "reconciled_no_sent_copy_found"

    item = manager.inspect_item(lease, op)
    assert item.state == OutboxState.UNKNOWN
    assert item.attempts_count == 1  # ZERO resends!


def test_reconciliation_delayed_appearance_workflow(crypto_env):
    """
    Verifies reconciliation over delayed appearance:
    - Pass 1: message not yet in Sent folder -> remains UNKNOWN.
    - Pass 2: message appears in Sent folder -> transitions to ACCEPTED.
    """
    wf, lease, op, envelope = create_prepared_message(crypto_env)
    manager = OutboxManager(wf.repository, ControlledTransport(Outcome.UNKNOWN))
    manager.submit(lease, op)

    reconciler = SentFolderReconciler()

    # Pass 1: Empty Sent folder
    client1 = MockIMAPSentClient([])
    res1 = reconciler.reconcile_outbox_operation(lease, wf.repository, op, client1, attempt=1)
    assert res1.state == State.UNKNOWN

    # Pass 2: Sent folder now has the message
    sent_msg = {
        "From": envelope.sender.value,
        "To": envelope.binding.recipients[0].value,
        "Subject": "Delayed Sent",
        "Date": formatdate(time.time()),
        "Message-ID": envelope.message_id,
    }
    client2 = MockIMAPSentClient([sent_msg])
    res2 = reconciler.reconcile_outbox_operation(lease, wf.repository, op, client2, attempt=2)
    assert res2.state == State.ACCEPTED
    assert res2.reason == "reconciled_sent_copy_found"


def test_reconciliation_conflicting_candidates_retains_unknown(crypto_env):
    """
    Verifies that multiple conflicting candidate messages in Sent folder
    cause reconciliation to evaluate to CONFLICT and retain UNKNOWN.
    """
    wf, lease, op, envelope = create_prepared_message(crypto_env)
    manager = OutboxManager(wf.repository, ControlledTransport(Outcome.UNKNOWN))
    manager.submit(lease, op)

    msg1 = {
        "From": envelope.sender.value,
        "To": envelope.binding.recipients[0].value,
        "Date": formatdate(time.time()),
        "Message-ID": envelope.message_id,
    }
    msg2 = {
        "From": envelope.sender.value,
        "To": envelope.binding.recipients[0].value,
        "Date": formatdate(time.time() + 10),
        "Message-ID": envelope.message_id,
    }
    mock_imap = MockIMAPSentClient([msg1, msg2])

    reconciler = SentFolderReconciler()
    result = reconciler.reconcile_outbox_operation(lease, wf.repository, op, mock_imap)

    assert result.state == State.UNKNOWN
    assert result.reason == "reconciliation_conflicting_candidates"


def test_reconciliation_header_mismatches_rejected(crypto_env):
    """
    Verifies that candidate messages with mismatched From, To, or out-of-bounds timestamps
    are not falsely matched:
    - Mismatched From address
    - Mismatched recipient address
    - Timestamp 2 years in past (replay)
    """
    wf, lease, op, envelope = create_prepared_message(crypto_env)
    reconciler = SentFolderReconciler()

    # 1. Mismatched From
    headers_bad_from = {
        "from": "attacker@example.invalid",
        "to": envelope.binding.recipients[0].value,
        "message-id": envelope.message_id,
        "date": formatdate(time.time()),
    }
    matched, reason = reconciler.match_candidate(envelope, headers_bad_from, time.time())
    assert matched is False
    assert "sender_mismatch" in reason

    # 2. Mismatched Recipient
    headers_bad_to = {
        "from": envelope.sender.value,
        "to": "someoneelse@example.invalid",
        "message-id": envelope.message_id,
        "date": formatdate(time.time()),
    }
    matched, reason = reconciler.match_candidate(envelope, headers_bad_to, time.time())
    assert matched is False
    assert "recipient_mismatch" in reason

    # 3. Timestamp out of window (2 years in past)
    old_time = time.time() - (2 * 365 * 86400)
    headers_old_date = {
        "from": envelope.sender.value,
        "to": envelope.binding.recipients[0].value,
        "message-id": envelope.message_id,
        "date": formatdate(old_time),
    }
    matched, reason = reconciler.match_candidate(envelope, headers_old_date, time.time())
    assert matched is False
    assert "timestamp_out_of_window" in reason


# =============================================================================
# SECTION 7: Bounded Backoff Scheduler & Transient Pre-Submission Retry (M16-OUT-003)
# =============================================================================

def test_reconciliation_scheduler_background_resolution(crypto_env):
    """
    Verifies M16-OUT-003:
    ReconciliationScheduler executes backoff reconciliation in the background
    and completes upon finding the message.
    """
    wf, lease, op, envelope = create_prepared_message(crypto_env)
    manager = OutboxManager(wf.repository, ControlledTransport(Outcome.UNKNOWN))
    manager.submit(lease, op)

    sent_msg = {
        "From": envelope.sender.value,
        "To": envelope.binding.recipients[0].value,
        "Subject": "Background Reconciliation Test",
        "Date": formatdate(time.time()),
        "Message-ID": envelope.message_id,
    }

    # Custom short intervals for unit test (0.05s, 0.1s)
    scheduler = ReconciliationScheduler(backoff_intervals=(0.05, 0.1))
    completed_event = threading.Event()
    final_result = None

    def on_done(res):
        nonlocal final_result
        final_result = res
        completed_event.set()

    thread = scheduler.schedule_reconciliation(
        lease,
        wf.repository,
        op,
        client_factory=lambda: MockIMAPSentClient([sent_msg]),
        on_completed=on_done,
    )
    thread.join(timeout=2.0)
    assert completed_event.is_set()
    assert final_result.state == State.ACCEPTED


def test_reconciliation_scheduler_clean_cancellation(crypto_env):
    """
    Verifies that cancelling the scheduler stops background worker threads
    cleanly without hanging.
    """
    wf, lease, op, envelope = create_prepared_message(crypto_env)
    manager = OutboxManager(wf.repository, ControlledTransport(Outcome.UNKNOWN))
    manager.submit(lease, op)

    # 10 second backoff to test cancellation
    scheduler = ReconciliationScheduler(backoff_intervals=(10.0, 10.0))
    cancel_event = threading.Event()

    thread = scheduler.schedule_reconciliation(
        lease,
        wf.repository,
        op,
        client_factory=lambda: MockIMAPSentClient([]),
        cancel_event=cancel_event,
    )
    # Trigger cancellation
    cancel_event.set()
    thread.join(timeout=1.0)
    assert not thread.is_alive()


def test_transient_submission_retry_for_pre_submission_errors(crypto_env):
    """
    Verifies M16-OUT-003:
    TransientSubmissionRetry executes bounded retry (up to 3 attempts with backoff)
    for pre-submission connection failures occurring BEFORE DATA terminator.
    """
    call_count = 0
    def flaky_pre_submission():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            # Pre-submission failure (e.g. DNS failure)
            return DeliveryResult(OperationId.new(), State.FAILED, "pre_submission_dns_failure", call_count)
        return DeliveryResult(OperationId.new(), State.ACCEPTED, "server_accepted_not_delivered", call_count)

    retry_helper = TransientSubmissionRetry(retry_delays=(0.01, 0.02, 0.05))
    result = retry_helper.execute_with_transient_retry(flaky_pre_submission)

    assert result.state == State.ACCEPTED
    assert call_count == 3


def test_transient_retry_never_retries_unknown_outcome():
    """
    CRITICAL INVARIANT:
    TransientSubmissionRetry must NEVER automatically retry an UNKNOWN outcome.
    UNKNOWN outcomes must immediately return to transition to Sent-folder reconciliation.
    """
    call_count = 0
    def ambiguous_submission():
        nonlocal call_count
        call_count += 1
        return DeliveryResult(OperationId.new(), State.UNKNOWN, "acceptance_unknown_duplicate_risk", call_count)

    retry_helper = TransientSubmissionRetry(retry_delays=(0.01, 0.02, 0.05))
    result = retry_helper.execute_with_transient_retry(ambiguous_submission)

    assert result.state == State.UNKNOWN
    assert call_count == 1  # Did NOT retry!


# =============================================================================
# SECTION 8: Zero-Network Isolation & Sensitive Data Scrubbing
# =============================================================================

def test_outbox_items_presentation_scrubs_sensitive_secrets(crypto_env):
    """
    Verifies that OutboxItem presentation models and audit records
    do not contain raw private keys, passwords, or OAuth bearer tokens.
    """
    wf, lease, op, envelope = create_prepared_message(crypto_env)
    manager = OutboxManager(wf.repository, ControlledTransport(Outcome.ACCEPTED))
    manager.submit(lease, op)

    item = manager.inspect_item(lease, op)
    item_str = str(item)

    # Check for secrets leakage
    assert "simulated-test-token" not in item_str
    assert "secret" not in item_str
    assert "private" not in item_str
    assert item.digest != ""
    assert len(item.digest) == 64
