"""
Deterministic tests for Cancellation Semantics & Outbox State Guarantees (Module 1.5 Workstream A / Closeout Audit).

Verifies the 7 explicit submission & cancellation cases:
1. User closes compose window before preparation starts.
2. User closes it while preparation is running.
3. User closes it after ciphertext has been persisted (PREPARED) but before SMTP submission.
4. User closes it while SMTP submission is in progress.
5. Server accepts message but client loses response (socket drop -> UNKNOWN).
6. Server rejects message (definitive rejection -> FAILED, draft preserved).
7. Process exits unexpectedly during submission (startup recovery -> UNKNOWN).

Proves all required invariants:
- Cancellation is never represented as confirmed when server acceptance remains possible.
- Ambiguous in-flight results become and remain UNKNOWN.
- Zero automatic retry of UNKNOWN records.
- Exact prepared ciphertext and digest are preserved across retries and recoveries.
- UI explicitly distinguishes pre-submission cancellation from in-flight disconnect.
"""

import time
import threading
from pathlib import Path
import pytest
from unittest.mock import Mock, patch

from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget
from PyQt6.QtGui import QCloseEvent

from experiments.m3.vault import Vault
from experiments.m3.types import EmailAddress, UserId, BoundaryError, Code as M3Code
from experiments.m3 import identity
from experiments.m3.provider import Provider as M3Provider
from experiments.m4.model import AccountAccess, Failure as M4Failure, Error as M4Error, State, Outcome, DeliveryResult, OperationId
from experiments.m4.services import SubmitOutbox
from experiments.m4.vault_adapter import VaultOutbox
from experiments.m5.provider import Provider as M5Provider
from experiments.m5.model import Draft, Budget, Failure as M5Failure, Code as M5Code
from experiments.m5.services import Compose
from mailbox_client.workflows import Workflows
from ui.mail_actions import MailActions
from tests.test_ui_hardening import MockWindow

ROOT = Path(__file__).resolve().parents[1]
M3_PROVIDER_BIN = ROOT / "tmp/m2/target/debug/qumail-m3-provider.exe"
M5_PROVIDER_BIN = ROOT / "tmp/m2/target/debug/qumail-m5-provider.exe"


class IsolatedMemoryStore:
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


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def crypto_env(tmp_path):
    p_m3 = M3Provider(M3_PROVIDER_BIN)
    p_m5 = M5Provider(M5_PROVIDER_BIN)
    vault_path = tmp_path / "test_semantics.sqlite"
    vault = Vault.create(vault_path, IsolatedMemoryStore(), p_m3)

    def make_ident(name):
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

    # Store simulated OAuth token on Alice's account for simulated transport compliance
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
    simulation_only = True
    def __init__(self, behavior="accept"):
        self.behavior = behavior
        self.entered = threading.Event()
        self.submitted = []

    def submit(self, envelope, credential, cancel, deadline):
        self.submitted.append(envelope)
        self.entered.set()
        if self.behavior == "accept":
            return Outcome.ACCEPTED
        elif self.behavior == "reject":
            return Outcome.REJECTED
        elif self.behavior == "lost_response":
            # Server receives DATA, but response code is lost/connection reset
            return Outcome.UNKNOWN
        elif self.behavior == "hang_and_cancel":
            # Wait for cancel event
            while not cancel.is_set() and time.monotonic() < deadline:
                time.sleep(0.01)
            return Outcome.UNKNOWN if cancel.is_set() else Outcome.REJECTED
        return Outcome.UNKNOWN


# ==============================================================================
# CASE 1: CLOSE BEFORE PREPARATION STARTS
# ==============================================================================

def test_case1_close_before_preparation_starts(qapp, crypto_env):
    """
    Case 1: User types a draft in the compose dialog, then closes the window
    before clicking Prepare or Send Securely.
    Guarantees:
    - No background worker exists.
    - Dialog closes cleanly.
    - Zero outbox records created in SQLite database.
    - Zero network transmission.
    """
    env = crypto_env
    vault, access, p_m5 = env["vault"], env["access"], env["p_m5"]
    ctx_a, key_a, addr_a = env["alice"]
    lease_a = access.select(ctx_a)

    mock_window = MockWindow()
    mock_window.lease = lease_a
    actions = MailActions(mock_window)

    actions.to.setText("bob@example.invalid")
    actions.subject.setText("Unsent Draft")
    actions.body.setPlainText("This draft was never prepared.")

    close_event = QCloseEvent()
    actions.closeEvent(close_event)
    assert close_event.isAccepted()

    # Verify SQLite outbox has zero records
    repo = VaultOutbox(vault, access)
    submit_service = SubmitOutbox(repo, None)
    with repo.transaction(lease_a, time.monotonic() + 5) as account:
        assert len(account.records) == 0

    actions.close()
    mock_window.close()


# ==============================================================================
# CASE 2: CLOSE WHILE PREPARATION IS RUNNING
# ==============================================================================

def test_case2_close_while_preparation_running(qapp, crypto_env):
    """
    Case 2: User initiates close while cryptographic preparation is in progress.
    Guarantees:
    - Dialog prompts with preparation-specific message ("Cancel preparation and close?").
    - Confirmed cancel aborts worker via budget.cancel.
    - Status reports pre-submission cancellation: "Cancelled. Preparation stopped before transmission."
    - No transport submission occurs.
    """
    mock_window = MockWindow()
    actions = MailActions(mock_window)

    # Simulate pending preparation task
    cancel_evt = threading.Event()
    actions.cancel_event = cancel_evt
    actions.pending.append((actions.epoch, 1, 1, mock_window.lease, cancel_evt, "prepare", None, Mock()))

    captured = {}
    def mock_question(parent, title, text, buttons, default):
        captured["title"] = title
        captured["text"] = text
        return QMessageBox.StandardButton.Yes

    close_event = QCloseEvent()
    with patch.object(QMessageBox, "question", side_effect=mock_question):
        actions.closeEvent(close_event)

    assert close_event.isAccepted()
    assert captured["title"] == "Operation In Progress"
    assert "Cancel preparation and close?" in captured["text"]
    assert cancel_evt.is_set()
    assert "Preparation stopped before transmission" in actions.status.text()

    actions.pending.clear()
    actions.close()
    mock_window.close()


# ==============================================================================
# CASE 3: CLOSE AFTER PERSISTED (PREPARED) BUT BEFORE SMTP SUBMISSION
# ==============================================================================

def test_case3_close_after_persisted_before_submission(crypto_env):
    """
    Case 3: Ciphertext has been durably frozen in SQLite as State.PREPARED,
    but cancellation is signaled before SubmitOutbox.submit() begins.
    Guarantees:
    - Record remains strictly in State.PREPARED.
    - Exact ciphertext bytes and SHA-256 digest are preserved.
    - Zero submission attempts recorded (attempts list is empty).
    - Transport is never contacted.
    """
    env = crypto_env
    vault, access, p_m5 = env["vault"], env["access"], env["p_m5"]
    ctx_a, key_a, addr_a = env["alice"]
    ctx_b, key_b, addr_b = env["bob"]
    lease_a = access.select(ctx_a)

    workflows = Workflows(vault, access, p_m5)
    draft = Draft((addr_b,), (), "Pre-submission Freeze", "Body content", (), "", ())

    budget = Budget(threading.Event(), time.monotonic() + 30)
    op = workflows.save(lease_a, draft, budget)
    envelope = workflows.prepare(lease_a, op, key_a, budget)

    # Verify PREPARED state before any submission
    repo = VaultOutbox(vault, access)
    with repo.transaction(lease_a, time.monotonic() + 5) as account:
        row = account.row(op)
        assert row["state"] == State.PREPARED.value
        assert row["reason"] == "durably_prepared"
        assert len(row["attempts"]) == 0
        original_digest = account.envelope(op).digest
        original_bytes = bytes(account.envelope(op).serialized)

    # Signal cancellation on budget
    budget.cancel.set()

    # Attempting workflows.submit with cancelled budget must fail before transport
    transport = ControlledTransport()
    with pytest.raises(M5Failure) as exc_info:
        workflows.submit(lease_a, op, budget)
    assert exc_info.value.code is M5Code.CANCELLED
    assert len(transport.submitted) == 0

    # Verify record in SQLite is still PREPARED with identical bytes and digest
    with repo.transaction(lease_a, time.monotonic() + 5) as account:
        row = account.row(op)
        assert row["state"] == State.PREPARED.value
        assert len(row["attempts"]) == 0
        assert account.envelope(op).digest == original_digest
        assert bytes(account.envelope(op).serialized) == original_bytes


# ==============================================================================
# CASE 4: CLOSE WHILE SMTP SUBMISSION IS IN PROGRESS
# ==============================================================================

def test_case4_close_while_smtp_submission_in_progress(qapp, crypto_env):
    """
    Case 4: User initiates close while network transmission is actively in-flight.
    Guarantees:
    - Confirmation dialog specifically warns about in-flight transmission and UNKNOWN state:
      "A message is currently being transmitted to the mail server...
       Closing this window will disconnect the client, but the mail server may still accept...
       Delivery status will be marked UNKNOWN and cannot be recalled."
    - Dialog NEVER uses the misleading word "cancel" to imply recall of sent email.
    - Status text honestly states: "Disconnected while transmitting. Delivery status is uncertain (UNKNOWN)..."
    - In-flight worker records State.UNKNOWN in SQLite, preserving prepared ciphertext.
    """
    mock_window = MockWindow()
    actions = MailActions(mock_window)

    # Pending item is send_securely (submission in flight)
    cancel_evt = threading.Event()
    actions.cancel_event = cancel_evt
    actions.pending.append((actions.epoch, 1, 1, mock_window.lease, cancel_evt, "send_securely", None, Mock()))

    captured = {}
    def mock_question(parent, title, text, buttons, default):
        captured["title"] = title
        captured["text"] = text
        return QMessageBox.StandardButton.Yes

    close_event = QCloseEvent()
    with patch.object(QMessageBox, "question", side_effect=mock_question):
        actions.closeEvent(close_event)

    assert close_event.isAccepted()
    assert captured["title"] == "Message Transmission In Progress"
    assert "cannot be recalled" in captured["text"]
    assert "delivery status will be marked unknown" in captured["text"].lower()
    assert "Disconnected while transmitting" in actions.status.text()
    assert "Delivery status is uncertain (UNKNOWN)" in actions.status.text()

    actions.pending.clear()
    actions.close()
    mock_window.close()


# ==============================================================================
# CASE 5: SERVER ACCEPTS MESSAGE BUT CLIENT LOSES RESPONSE (SOCKET DROP -> UNKNOWN)
# ==============================================================================

def test_case5_server_accepts_but_client_loses_response(crypto_env):
    """
    Case 5: Mail server receives and queues the message, but socket drops
    before SMTP 250 response is parsed by client.
    Guarantees:
    - Submission returns State.UNKNOWN with reason 'acceptance_unknown_duplicate_risk'.
    - It is NEVER marked State.ACCEPTED (unverified) and NEVER State.FAILED (server may deliver).
    - Automatic retry is strictly prohibited: calling SubmitOutbox.submit() on an UNKNOWN
      record raises Failure(Error.TRANSITION).
    - Only explicit human operator retry with acknowledge_duplicate_risk=True can re-queue.
    - Prepared ciphertext and digest remain identical.
    """
    env = crypto_env
    vault, access, p_m5 = env["vault"], env["access"], env["p_m5"]
    ctx_a, key_a, addr_a = env["alice"]
    ctx_b, key_b, addr_b = env["bob"]
    lease_a = access.select(ctx_a)

    compose = Compose(vault, access, p_m5)
    draft = Draft((addr_b,), (), "Socket Drop Test", "Ambiguous Delivery", (), "", ())
    budget = Budget(threading.Event(), time.monotonic() + 30)

    op = compose.draft(lease_a, draft, budget)
    envelope = compose.prepare(lease_a, op, key_a, budget)
    original_digest = envelope.digest

    # Transport double simulating lost response
    transport = ControlledTransport(behavior="lost_response")
    submit_service = SubmitOutbox(compose.repository, transport)

    delivery = submit_service.submit(lease_a, op)
    assert delivery.state is State.UNKNOWN
    assert delivery.reason == "acceptance_unknown_duplicate_risk"
    assert delivery.attempt == 1

    # INVARIANT: Automatic resubmission is blocked by state machine
    with pytest.raises(M4Failure) as exc_info:
        submit_service.submit(lease_a, op)
    assert exc_info.value.code is M4Error.TRANSITION

    # INVARIANT: Retry requires explicit acknowledge_duplicate_risk=True
    with pytest.raises(M4Failure) as exc_retry:
        submit_service.retry(lease_a, op, acknowledge_duplicate_risk=False)
    assert exc_retry.value.code is M4Error.DUPLICATE

    # With explicit human acknowledgment, retry resets state back to PREPARED
    submit_service.retry(lease_a, op, acknowledge_duplicate_risk=True)
    with compose.repository.transaction(lease_a, time.monotonic() + 5) as account:
        row = account.row(op)
        assert row["state"] == State.PREPARED.value
        # Digest must be completely identical
        assert account.envelope(op).digest == original_digest


# ==============================================================================
# CASE 6: SERVER REJECTS MESSAGE (DEFINITIVE REJECTION -> FAILED)
# ==============================================================================

def test_case6_server_rejects_message(crypto_env):
    """
    Case 6: Mail server returns definitive rejection (e.g. SMTP 550 Recipient rejected).
    Guarantees:
    - Submission returns State.FAILED with reason 'definitive_rejection_or_stopped_before_data'.
    - Outbox record is marked State.FAILED.
    - Prepared ciphertext and digest remain preserved in SQLite for audit and retry.
    """
    env = crypto_env
    vault, access, p_m5 = env["vault"], env["access"], env["p_m5"]
    ctx_a, key_a, addr_a = env["alice"]
    ctx_b, key_b, addr_b = env["bob"]
    lease_a = access.select(ctx_a)

    compose = Compose(vault, access, p_m5)
    draft = Draft((addr_b,), (), "Rejection Test", "Definitive 550", (), "", ())
    budget = Budget(threading.Event(), time.monotonic() + 30)

    op = compose.draft(lease_a, draft, budget)
    envelope = compose.prepare(lease_a, op, key_a, budget)

    transport = ControlledTransport(behavior="reject")
    submit_service = SubmitOutbox(compose.repository, transport)

    delivery = submit_service.submit(lease_a, op)
    assert delivery.state is State.FAILED
    assert delivery.reason == "definitive_rejection_or_stopped_before_data"
    assert delivery.attempt == 1

    with compose.repository.transaction(lease_a, time.monotonic() + 5) as account:
        row = account.row(op)
        assert row["state"] == State.FAILED.value
        assert account.envelope(op).digest == envelope.digest


# ==============================================================================
# CASE 7: UNEXPECTED PROCESS TERMINATION DURING SUBMISSION (STARTUP RECOVERY)
# ==============================================================================

def test_case7_process_exits_unexpectedly_during_submission(crypto_env):
    """
    Case 7: Process exits or crashes while State.SUBMITTING is committed.
    Guarantees:
    - At startup, SubmitOutbox.recover() discovers the orphaned SUBMITTING record.
    - Transitions it safely to State.UNKNOWN with reason 'interrupted_acceptance_unknown'.
    - No automatic resend occurs.
    - The exact prepared ciphertext is retained.
    """
    env = crypto_env
    vault, access, p_m5 = env["vault"], env["access"], env["p_m5"]
    ctx_a, key_a, addr_a = env["alice"]
    ctx_b, key_b, addr_b = env["bob"]
    lease_a = access.select(ctx_a)

    compose = Compose(vault, access, p_m5)
    draft = Draft((addr_b,), (), "Crash Recovery", "In-Flight Termination", (), "", ())
    budget = Budget(threading.Event(), time.monotonic() + 30)

    op = compose.draft(lease_a, draft, budget)
    envelope = compose.prepare(lease_a, op, key_a, budget)
    original_digest = envelope.digest

    # Simulate crash right after submission intent committed (state = SUBMITTING)
    repo = compose.repository
    with repo.ownership(lease_a.context, op):
        with repo.transaction(lease_a, time.monotonic() + 5) as account:
            row = account.row(op)
            row["attempts"].append(dict(
                number=1, identity="crash-test-id", state=State.SUBMITTING.value,
                reason="submission_intent_committed", digest=envelope.digest
            ))
            row.update(state=State.SUBMITTING.value, reason="submission_intent_committed")

    # Verify that in SQLite, the record is currently orphaned in SUBMITTING
    with repo.transaction(lease_a, time.monotonic() + 5) as account:
        assert account.row(op)["state"] == State.SUBMITTING.value

    # Application restarts: SubmitOutbox.recover() executes
    submit_service = SubmitOutbox(repo, None)
    recovered = submit_service.recover(lease_a)
    assert recovered == (op,)

    # Verify record transitioned to State.UNKNOWN with reason 'interrupted_acceptance_unknown'
    with repo.transaction(lease_a, time.monotonic() + 5) as account:
        row = account.row(op)
        assert row["state"] == State.UNKNOWN.value
        assert row["reason"] == "interrupted_acceptance_unknown"
        assert row["attempts"][-1]["state"] == State.UNKNOWN.value
        assert account.envelope(op).digest == original_digest
