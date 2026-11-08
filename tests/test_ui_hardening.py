"""
Unit and integration tests for UX Security Hardening (Module 1.5 Workstream A).

Verifies:
- A1: Compose text preservation on failure/unknown, close guard during active work.
- A2: Truthful security indicator badge states (no false encryption claims).
- A3: Onboarding wizard explicit vault confirmation (no silent creation/unlock) and safe cancellation.
"""

from unittest.mock import Mock, patch
from concurrent.futures import ThreadPoolExecutor
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget
from PyQt6.QtGui import QCloseEvent

from ui.mail_actions import MailActions
from ui.onboarding_wizard import OnboardingWizard
from core.account_session import DevelopmentSession, Snapshot
from experiments.m4.model import State, OperationId
from experiments.m4.services import DeliveryResult
from experiments.m5.model import Draft


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class MockWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.identity = Mock()
        self.identity.session = DevelopmentSession()
        self.lease = Mock()
        self.epoch = 1
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.display = None
        self.content = Mock()
        self.security = Mock()
        self.attachments = Mock()

    def cancel(self, clear_actions=False):
        pass


def test_security_badge_truthful_states(qapp):
    """
    A2: Verify that MailActions badge is initialized to 'draft' (neutral plaintext claim),
    never claiming encryption until the message is actually prepared.
    """
    mock_window = MockWindow()
    actions = MailActions(mock_window, gmail_enabled=False)

    # Initially in draft mode
    assert "Draft" in actions.badge.text()
    assert "Not yet encrypted" in actions.badge.text()

    # Recipient keys verified
    actions.set_security_badge("keys_verified")
    assert "Recipient Keys Verified" in actions.badge.text()

    # Recipient keys unverified/missing
    actions.set_security_badge("keys_unverified")
    assert "Keys Unverified" in actions.badge.text()

    # Encrypted & prepared
    actions.set_security_badge("encrypted_prepared")
    assert "End-to-End Encrypted (OpenPGP)" in actions.badge.text()
    assert "Ready to Send" in actions.badge.text()

    # Submitting
    actions.set_security_badge("submitting")
    assert "Sending Securely" in actions.badge.text()

    # Accepted
    actions.set_security_badge("accepted")
    assert "Accepted by Mail Server" in actions.badge.text()

    # Failed
    actions.set_security_badge("failed")
    assert "Send Failed" in actions.badge.text()

    # Unknown
    actions.set_security_badge("unknown")
    assert "Delivery Uncertain" in actions.badge.text()

    actions.close()
    mock_window.close()


def test_compose_editor_text_preserved_on_failure(qapp):
    """
    A1: Verify that when submission fails or is uncertain (UNKNOWN),
    the editor text is NOT cleared, preserving user input.
    """
    mock_window = MockWindow()
    mock_window.identity.session.snapshot = Snapshot(generation=1, locked=False, accounts=(), active=Mock(key=Mock()))
    mock_window.lease = Mock()

    actions = MailActions(mock_window, gmail_enabled=True)
    actions.to.setText("recipient@example.com")
    actions.subject.setText("Important Subject")
    actions.body.setPlainText("Confidential message body")

    # Simulate submission returning FAILED
    failed_res = DeliveryResult(OperationId("0123456789abcdef0123456789abcdef"), State.FAILED, "definitive_rejection", 1)
    future = Mock()
    future.done.return_value = True
    future.result.return_value = ("submitted", failed_res)

    actions.pending.append((
        actions.epoch, actions.window.epoch, 1, actions.window.lease,
        Mock(is_set=lambda: False), "send_securely", None, future
    ))

    with patch.object(actions, "start"):  # mock out outbox refresh call
        actions.poll()

    # Verification: fields must still contain the original draft!
    assert actions.to.text() == "recipient@example.com"
    assert actions.subject.text() == "Important Subject"
    assert actions.body.toPlainText() == "Confidential message body"
    assert "Send Failed" in actions.badge.text()

    # Simulate submission returning UNKNOWN
    unknown_res = DeliveryResult(OperationId("0123456789abcdef0123456789abcdef"), State.UNKNOWN, "acceptance_unknown", 1)
    future_unk = Mock()
    future_unk.done.return_value = True
    future_unk.result.return_value = ("submitted", unknown_res)

    actions.pending.append((
        actions.epoch, actions.window.epoch, 1, actions.window.lease,
        Mock(is_set=lambda: False), "send_securely", None, future_unk
    ))

    with patch.object(actions, "start"):
        actions.poll()

    # Verification: text must remain intact on UNKNOWN as well!
    assert actions.to.text() == "recipient@example.com"
    assert "Delivery Uncertain" in actions.badge.text()

    # Simulate submission returning ACCEPTED
    accepted_res = DeliveryResult(OperationId("0123456789abcdef0123456789abcdef"), State.ACCEPTED, "server_accepted", 1)
    future_acc = Mock()
    future_acc.done.return_value = True
    future_acc.result.return_value = ("submitted", accepted_res)

    actions.pending.append((
        actions.epoch, actions.window.epoch, 1, actions.window.lease,
        Mock(is_set=lambda: False), "send_securely", None, future_acc
    ))

    with patch.object(actions, "start"):
        actions.poll()

    # Verification: now that server accepted it, draft is safely cleared
    assert actions.to.text() == ""
    assert actions.body.toPlainText() == ""
    assert "Accepted by Mail Server" in actions.badge.text()

    actions.close()
    mock_window.close()


def test_compose_close_guard_when_pending(qapp):
    """
    A1: Verify that closing MailActions while an operation is pending
    prompts the user and prevents accidental closure if rejected.
    """
    mock_window = MockWindow()
    actions = MailActions(mock_window)
    actions.pending.append(("active_task",))

    close_event = QCloseEvent()

    # User clicks 'No' (do not cancel)
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
        actions.closeEvent(close_event)
        assert not close_event.isAccepted()  # Event was ignored; window stays open

    # User clicks 'Yes' (confirm cancellation)
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        actions.closeEvent(close_event)
        assert close_event.isAccepted()

    actions.pending.clear()
    actions.close()
    mock_window.close()


def test_onboarding_no_silent_vault_creation_or_unlock(qapp):
    """
    A3: Verify that the onboarding wizard never silently creates or unlocks a vault.
    If the user declines the confirmation prompt, the operation cancels cleanly.
    """
    mock_identity = Mock()
    mock_identity.session.snapshot.locked = True
    mock_identity.session.snapshot.active = None
    mock_identity.path = Mock()
    mock_identity.path.exists.return_value = False  # Vault does not exist

    wizard = OnboardingWizard(mock_identity)
    wizard._email_input.setText("alice@gmail.com")

    # User declines to create new vault
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
        wizard._start_connection()
        assert mock_identity.unlock.call_count == 0
        assert "No new vault was created" in wizard._auth_status.text()

    # User confirms creation of new vault
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        with patch.object(wizard, "parent", return_value=None):
            wizard._start_connection()
            assert mock_identity.unlock.call_count == 1
            mock_identity.unlock.assert_called_with(create=True)

    wizard.close()


def test_onboarding_safe_cancellation(qapp):
    """
    A3: Verify that cancelling or navigating back in the onboarding wizard
    resets connect button state and stops any active auth.
    """
    mock_identity = Mock()
    mock_identity.session.snapshot.locked = False
    mock_identity.session.snapshot.active = None

    wizard = OnboardingWizard(mock_identity)
    mock_parent = Mock()
    with patch.object(wizard, "parent", return_value=mock_parent):
        wizard._connect_btn.setEnabled(False)
        wizard._auth_status.setText("Working...")
        wizard._cancel_auth()

        assert wizard._connect_btn.isEnabled()
        assert wizard._auth_status.text() == ""
        assert mock_parent.settings.cancel.call_count == 1

    wizard.close()
