"""
Comprehensive Tests for QuMail M7 — Module 1.6 WS-05:
Complete Three-Pane Email Experience & Zero-Cryptographic-Friction UX.

Covers:
- Section 1: Three-Pane Layout, Resizing & Navigation Structure.
- Section 2: Folder Navigation & Live Unread Badges (WS-03 Integration).
- Section 3: Message Selection, Filtering & Inline Reading Pane Rendering.
- Section 4: Security Indicators & Trust Presentation (WS-02 Contract).
- Section 5: Zero-Friction Secure Compose & Draft Workflows.
- Section 6: Outbox Spool Presentation & Explicit Duplicate-Risk Retry (WS-04 Contract).
- Section 7: Attachment Pipeline Interaction (Listing, Safe Export, Execution Block).
- Section 8: Synchronization State Indicators & Non-Blocking GUI Lifecycle.
- Section 9: Application Settings, Preferences & Themes (Dark/Light).
- Section 10: Clean Shutdown, Resource Cleanup & Memory Safety.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any
from unittest.mock import Mock, patch

import pytest
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox, QWidget

from core.outbox_manager import OutboxItem, OutboxState
from core.security_indicators import BadgeLevel, IndicatorCode, SecurityIndicator
from experiments.m3 import identity
from experiments.m3.types import AccountContext, BoundaryError, Code as M3Code, EmailAddress, KeyHandle, UserId
from experiments.m3.vault import Vault
from experiments.m4.model import AccountAccess, DeliveryResult, Error as M4Error, Failure as M4Failure, Lease, OperationId, Outcome, State
from experiments.m5.model import Attachment, Budget, Draft
from experiments.m5.provider import Provider as M5Provider
from mailbox_client.model import Display, Header, MessageKey, Page
from mailbox_client.workflows import Workflows
from ui.compose_dialog import ComposeDialog
from ui.design_system import C
from ui.mailbox_window import MailboxWindow
from ui.message_list_pane import MessageListPane, format_message_date
from ui.navigation_pane import NavigationPane
from ui.reading_pane import ReadingPane
from ui.security_badge_widget import SecurityBanner, SecurityPill
from ui.settings_dialog import SettingsDialog

ROOT = Path(__file__).resolve().parents[1]
from core.provider_resolver import resolve_provider
M3_PROVIDER_BIN = resolve_provider("qumail-m3-provider")
M5_PROVIDER_BIN = resolve_provider("qumail-m5-provider")


# =============================================================================
# In-Memory Test Fixtures
# =============================================================================

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
    from experiments.m3.provider import Provider as M3Provider
    p_m3 = M3Provider(M3_PROVIDER_BIN)
    p_m5 = M5Provider(M5_PROVIDER_BIN)
    vault_path = tmp_path / "ws05_vault.sqlite"
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


def make_mock_identity(crypto_env):
    """Build mock identity service bound to crypto_env."""
    from core.account_session import DevelopmentSession, AccountView, Snapshot
    session = DevelopmentSession()
    ctx_a, key_a, addr_a = crypto_env["alice"]

    acc = AccountView(
        context=ctx_a,
        key=key_a,
        address=addr_a,
        root="mock_root_fingerprint",
        lifecycle="Active",
    )
    session.snapshot = Snapshot(
        generation=1,
        locked=False,
        accounts=(acc,),
        active=acc,
    )

    mock_id = Mock()
    mock_id.session = session
    mock_id.google = None
    mock_id.require = Mock(return_value=crypto_env["vault"])
    mock_id.lock = Mock()
    return mock_id


# =============================================================================
# SECTION 1: Three-Pane Layout, Resizing & Navigation Structure
# =============================================================================

def test_three_pane_desktop_layout_initialization(qapp, crypto_env):
    """
    Verifies that MailboxWindow initializes with a horizontal splitter
    hosting the three primary panes:
    - NavigationPane (left, width ~220px)
    - MessageListPane (middle, width ~380px)
    - ReadingPane (right, inline reader)
    """
    mock_identity = make_mock_identity(crypto_env)
    window = MailboxWindow(mock_identity, gmail_enabled=False)

    try:
        window.show()
        qapp.processEvents()

        assert hasattr(window, "splitter")
        assert window.splitter.count() == 3

        pane1 = window.splitter.widget(0)
        pane2 = window.splitter.widget(1)
        pane3 = window.splitter.widget(2)

        assert isinstance(pane1, NavigationPane)
        assert isinstance(pane2, MessageListPane)
        assert isinstance(pane3, ReadingPane)

        sizes = window.splitter.sizes()
        assert len(sizes) == 3
        assert sizes[0] > 0
        assert sizes[1] > 0
        assert sizes[2] > 0
    finally:
        window.close()


def test_responsive_minimum_dimensions(qapp, crypto_env):
    """
    Verifies that the window enforces sensible minimum desktop dimensions (940x600).
    """
    mock_identity = make_mock_identity(crypto_env)
    window = MailboxWindow(mock_identity, gmail_enabled=False)
    try:
        min_size = window.minimumSize()
        assert min_size.width() >= 940
        assert min_size.height() >= 600
    finally:
        window.close()


# =============================================================================
# SECTION 2: Folder Navigation & Live Unread Badges (WS-03 Integration)
# =============================================================================

def test_folder_navigation_switching(qapp, crypto_env):
    """
    Verifies that clicking folders in NavigationPane emits folder_selected
    and switches views in the message list pane.
    """
    mock_identity = make_mock_identity(crypto_env)
    window = MailboxWindow(mock_identity, gmail_enabled=False)

    try:
        window.show()
        qapp.processEvents()

        # Switch to Sent
        window.navigation_pane.folder_selected.emit("sent")
        assert window.current_folder == "sent"
        assert window.message_list_pane.folder_title.text() == "Sent Mail"

        # Switch to Outbox
        window.navigation_pane.folder_selected.emit("outbox")
        assert window.current_folder == "outbox"
        assert window.message_list_pane.folder_title.text() == "Outbox"

        # Switch back to Inbox
        window.navigation_pane.folder_selected.emit("inbox")
        assert window.current_folder == "inbox"
        assert window.message_list_pane.folder_title.text() == "Inbox"
    finally:
        window.close()


def test_live_unread_badge_counting(qapp, crypto_env):
    """
    Verifies that unread counts dynamically update the badge on the Inbox folder
    and inside the message list pane header.
    """
    mock_identity = make_mock_identity(crypto_env)
    window = MailboxWindow(mock_identity, gmail_enabled=False)

    try:
        window.show()
        qapp.processEvents()

        # Simulate headers loaded: 3 total, 2 unread
        ctx_a, *_ = crypto_env["alice"]
        k1 = MessageKey(ctx_a, "INBOX", 1, 1)
        k2 = MessageKey(ctx_a, "INBOX", 1, 2)
        k3 = MessageKey(ctx_a, "INBOX", 1, 3)
        h1 = Header(k1, "alice@example.invalid", "First message", "Mon, 9 Nov 2026 10:00:00 -0000", 1024, False)
        h2 = Header(k2, "bob@example.invalid", "Second message", "Mon, 9 Nov 2026 11:00:00 -0000", 2048, False)
        h3 = Header(k3, "carol@example.invalid", "Third message", "Mon, 9 Nov 2026 12:00:00 -0000", 512, True)

        window.rows = (h1, h2, h3)
        window.render_rows()
        qapp.processEvents()

        # Verify badge in NavigationPane for Inbox
        inbox_widget = window.navigation_pane._folder_widgets["inbox"]
        assert not inbox_widget.badge.isHidden()
        assert inbox_widget.badge.text() == "2"

        # Verify count label in MessageListPane
        assert "2 unread" in window.message_list_pane.count_lbl.text()
    finally:
        window.close()


# =============================================================================
# SECTION 3: Message Selection, Filtering & Inline Reading Pane
# =============================================================================

def test_instant_search_filtering_in_message_list(qapp, crypto_env):
    """
    Verifies that typing in the search box filters message cards across
    sender and subject.
    """
    pane = MessageListPane()
    messages = [
        ("key1", {"sender": "Alice Smith", "subject": "Quarterly Budget", "snippet": "Draft plan", "seen": False}),
        ("key2", {"sender": "Bob Jones", "subject": "Security Review", "snippet": "Approved", "seen": True}),
        ("key3", {"sender": "Carol Danvers", "subject": "Lunch Plans", "snippet": "Pizza?", "seen": True}),
    ]
    pane.set_messages(messages)

    assert pane.list_widget.count() == 3

    # Filter by 'Security'
    pane.search_input.setText("security")
    assert pane.list_widget.count() == 1
    item = pane.list_widget.item(0)
    assert item.data(Qt.ItemDataRole.UserRole) == "key2"

    # Filter by sender 'Alice'
    pane.search_input.setText("alice")
    assert pane.list_widget.count() == 1
    assert pane.list_widget.item(0).data(Qt.ItemDataRole.UserRole) == "key1"

    # Clear search
    pane.search_input.clear()
    assert pane.list_widget.count() == 3


def test_unread_only_filter_toggle(qapp, crypto_env):
    """
    Verifies toggling between 'All' and 'Unread' tabs filters read messages out.
    """
    pane = MessageListPane()
    messages = [
        ("key1", {"sender": "Alice", "subject": "Unread 1", "seen": False}),
        ("key2", {"sender": "Bob", "subject": "Read 1", "seen": True}),
        ("key3", {"sender": "Carol", "subject": "Unread 2", "seen": False}),
    ]
    pane.set_messages(messages)
    assert pane.list_widget.count() == 3

    # Click Unread tab
    pane._set_filter_tab(True)
    assert pane.list_widget.count() == 2

    # Click All tab
    pane._set_filter_tab(False)
    assert pane.list_widget.count() == 3


def test_inline_reading_pane_rendering_without_popups(qapp, crypto_env):
    """
    Verifies that ReadingPane renders message contents inline:
    - Subject, sender, recipients, date, and body rendered directly.
    - No separate popup dialog is launched.
    """
    reading_pane = ReadingPane()

    indicator = SecurityIndicator.secured("Alice Smith")
    reading_pane.show_message(
        subject="Project Alpha Launch",
        sender="Alice Smith <alice@example.invalid>",
        recipients="Bob <bob@example.invalid>",
        date_str="Nov 9, 2026, 10:45 AM",
        body="Here is the launch brief.\nAll systems are go.",
        indicator=indicator,
        attachments=[],
    )

    reading_pane.show()
    qapp.processEvents()

    assert not reading_pane.content_container.isHidden()
    assert reading_pane.empty_container.isHidden()
    assert reading_pane.subject_lbl.text() == "Project Alpha Launch"
    assert "Alice Smith" in reading_pane.sender_val.text()
    assert "Here is the launch brief." in reading_pane.body_view.toPlainText()
    assert not reading_pane.security_banner.isHidden()


# =============================================================================
# SECTION 4: Security Indicators & Trust Presentation (WS-02 Contract)
# =============================================================================

def test_security_indicator_vocabulary_rendering(qapp):
    """
    Verifies that all 5 required security indicator vocabulary states render
    with appropriate badges and plain-language guidance:
    1. Verified and secure (Green)
    2. Encrypted, identity unverified (Amber)
    3. External correspondent (Neutral/Blue)
    4. Security verification failed (Red Alert)
    5. Security information unavailable (Gray Neutral)
    """
    banner = SecurityBanner()

    # 1. Verified and Secure
    sec = SecurityIndicator.secured("alice@example.invalid")
    banner.set_indicator(sec)
    assert banner.level_badge.text() == "SECURE"
    assert "Secured by QuMail" in banner.headline_label.text()
    assert "Verified corporate identity" in banner.desc_label.text()

    # 2. Encrypted, Identity Unverified
    caut = SecurityIndicator.encrypted_unverified("unknown@example.invalid")
    banner.set_indicator(caut)
    assert banner.level_badge.text() == "CAUTION"
    assert "Identity Unverified" in banner.headline_label.text()

    # 3. External Correspondent
    ext = SecurityIndicator.external_correspondent("external@partner.invalid")
    banner.set_indicator(ext)
    assert banner.level_badge.text() == "NEUTRAL"
    assert "External Correspondent" in banner.headline_label.text()

    # 4. Security Verification Failed (Signature Invalid)
    alert = SecurityIndicator.signature_invalid()
    banner.set_indicator(alert)
    assert banner.level_badge.text() == "ALERT"
    assert "Signature Invalid" in banner.headline_label.text()
    assert "DO NOT trust this message" in banner.advice_label.text()

    # 5. Security Information Unavailable
    unavail = SecurityIndicator.verification_unavailable("Network offline")
    banner.set_indicator(unavail)
    assert banner.level_badge.text() == "NEUTRAL"
    assert "Unavailable" in banner.headline_label.text()


# =============================================================================
# SECTION 5: Zero-Friction Secure Compose & Draft Workflows
# =============================================================================

def test_compose_dialog_save_draft_and_recipient_trust(qapp, crypto_env):
    """
    Verifies that ComposeDialog allows drafting without cryptographic jargon:
    - To, Subject, Body input.
    - Live recipient validation via Workflows.
    - Draft saved durably in the vault.
    """
    vault, access, p_m5 = crypto_env["vault"], crypto_env["access"], crypto_env["p_m5"]
    ctx_a, key_a, addr_a = crypto_env["alice"]
    lease = access.select(ctx_a)

    wf = Workflows(vault, access, p_m5)
    dialog = ComposeDialog(wf, lease)

    dialog.to_input.setText("bob@example.invalid")
    dialog.subject_input.setText("Confidential Project")
    dialog.body_input.setPlainText("This is confidential draft content.")

    # Save draft
    dialog._on_save_draft()
    assert dialog.operation is not None
    assert "Draft saved locally" in dialog.status_lbl.text()

    dialog.close()


def test_compose_dialog_send_securely_workflow(qapp, crypto_env):
    """
    Verifies that clicking 'Send Securely' automatically handles:
    1. Draft save
    2. Post-quantum cryptographic preparation and sealing
    3. Outbox submission
    Without asking the employee to select algorithms or keys.
    """
    vault, access, p_m5 = crypto_env["vault"], crypto_env["access"], crypto_env["p_m5"]
    ctx_a, key_a, addr_a = crypto_env["alice"]
    lease = access.select(ctx_a)

    class ControlledTransport:
        simulation_only = True
        def submit(self, envelope, credential, cancel, deadline):
            return Outcome.ACCEPTED

    wf = Workflows(vault, access, p_m5, transport_factory=lambda creds: ControlledTransport())
    dialog = ComposeDialog(wf, lease)

    dialog.to_input.setText("bob@example.invalid")
    dialog.subject_input.setText("Secure Send Test")
    dialog.body_input.setPlainText("Payload securely transmitted.")

    # Mock QMessageBox to prevent blocking unit test
    with patch.object(QMessageBox, "information") as mock_info:
        dialog._on_send_securely()
        assert mock_info.called
        assert "Accepted by your mail server" in mock_info.call_args[0][2]

    dialog.close()


# =============================================================================
# SECTION 6: Outbox Spool Presentation & Explicit Duplicate-Risk Retry (WS-04)
# =============================================================================

def test_outbox_spool_presentation_plain_language_labels(qapp, crypto_env):
    """
    Verifies that ComposeDialog's Outbox tab displays WS-04 plain-language statuses:
    - 'Draft saved locally'
    - 'Accepted by your mail server'
    - 'Could not confirm whether this message was sent'
    """
    vault, access, p_m5 = crypto_env["vault"], crypto_env["access"], crypto_env["p_m5"]
    ctx_a, key_a, addr_a = crypto_env["alice"]
    lease = access.select(ctx_a)
    budget = Budget(threading.Event(), time.monotonic() + 30)

    wf = Workflows(vault, access, p_m5)
    # Create draft
    op = wf.save(lease, Draft(("bob@example.invalid",), (), "Outbox Test", "Body", ()), budget)

    dialog = ComposeDialog(wf, lease)
    dialog.refresh_outbox()

    assert dialog.outbox_table.rowCount() >= 1
    status_item = dialog.outbox_table.item(0, 0)
    assert status_item.text() == "Draft saved locally"

    dialog.close()


def test_retry_unknown_requires_explicit_user_confirmation(qapp, crypto_env):
    """
    CRITICAL INVARIANT:
    Retrying an UNKNOWN delivery requires explicit confirmation of duplicate-delivery risk.
    Verifies warning prompt and rejection when canceled.
    """
    vault, access, p_m5 = crypto_env["vault"], crypto_env["access"], crypto_env["p_m5"]
    ctx_a, key_a, addr_a = crypto_env["alice"]
    lease = access.select(ctx_a)
    budget = Budget(threading.Event(), time.monotonic() + 30)

    class ControlledTransport:
        simulation_only = True
        def submit(self, envelope, credential, cancel, deadline):
            return Outcome.ACCEPTED

    wf = Workflows(vault, access, p_m5, transport_factory=lambda creds: ControlledTransport())
    op = wf.save(lease, Draft(("bob@example.invalid",), (), "Unknown Send", "Body", ()), budget)
    wf.prepare(lease, op, key_a, budget)

    # Move to UNKNOWN
    with wf.repository.transaction(lease, budget.deadline) as account:
        account.row(op).update(state=State.UNKNOWN.value, reason="acceptance_unknown_duplicate_risk")

    dialog = ComposeDialog(wf, lease)
    dialog.refresh_outbox()
    dialog.outbox_table.setCurrentCell(0, 0)

    # 1. User clicks No / Cancel -> retry aborted
    with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.No):
        dialog._on_retry_selected()
        with wf.repository.transaction(lease, budget.deadline) as account:
            assert account.row(op)["state"] == State.UNKNOWN.value

    # 2. User clicks Yes -> authorized and retried
    with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
        with patch.object(QMessageBox, "information"), patch.object(QMessageBox, "critical"):
            dialog._on_retry_selected()
            with wf.repository.transaction(lease, budget.deadline) as account:
                # State moved to ACCEPTED or SUBMITTING
                assert account.row(op)["state"] in (State.PREPARED.value, State.SUBMITTING.value, State.ACCEPTED.value)

    dialog.close()


# =============================================================================
# SECTION 7: Attachment Pipeline Interaction
# =============================================================================

def test_attachment_card_listing_and_export(qapp, crypto_env, tmp_path):
    """
    Verifies that attachments render on AttachmentCards and export atomically.
    """
    reading_pane = ReadingPane()

    att_data = b"Hello, post-quantum secure PDF content."
    attachments = [{
        "name": "corporate_report.pdf",
        "size": len(att_data),
        "media_type": "application/pdf",
        "data": att_data,
    }]

    reading_pane.show_message(
        subject="Report Attached",
        sender="alice@example.invalid",
        recipients="You",
        date_str="Nov 9, 2026",
        body="Please find report attached.",
        attachments=attachments,
    )

    reading_pane.show()
    qapp.processEvents()
    assert not reading_pane.attachments_container.isHidden()
    assert reading_pane.attachments_card_layout.count() == 1

    # Verify Save As signal emission
    exported_args = None
    def on_export(idx, dest):
        nonlocal exported_args
        exported_args = (idx, dest)

    reading_pane.export_attachment_requested.connect(on_export)

    target_file = str(tmp_path / "saved_report.pdf")
    with patch.object(QFileDialog, "getSaveFileName", return_value=(target_file, "PDF")):
        reading_pane._on_save_attachment(0)

    assert exported_args == (0, target_file)


def test_executable_attachment_execution_blocked(qapp, crypto_env):
    """
    STRICT SECURITY INVARIANT:
    Direct execution of binary/executable files (.exe, .bat, .cmd, .ps1, .vbs)
    is strictly blocked by policy.
    """
    mock_identity = make_mock_identity(crypto_env)
    window = MailboxWindow(mock_identity, gmail_enabled=False)

    window.display = Mock(sender="alice@example.invalid")
    window.reading_pane.current_attachments = [{
        "name": "malware.exe",
        "size": 4096,
        "media_type": "application/x-msdownload",
        "data": b"MZ...",
    }]

    with patch.object(QMessageBox, "critical") as mock_crit:
        window.on_open_attachment(0)
        assert mock_crit.called
        assert "block" in mock_crit.call_args[0][1].lower()
        assert "blocked" in mock_crit.call_args[0][2].lower()

    window.close()


# =============================================================================
# SECTION 8: Synchronization State Indicators & Non-Blocking GUI
# =============================================================================

def test_sync_state_indicator_updates(qapp, crypto_env):
    """
    Verifies that synchronization states (Idle, Syncing, Reconnecting, Offline)
    update the navigation pane's status dot and label unobtrusively.
    """
    nav = NavigationPane()

    nav.set_sync_state("Idle")
    assert nav.sync_status_lbl.text() == "Idle"

    nav.set_sync_state("Syncing…")
    assert "Synchronizing" in nav.sync_status_lbl.text()

    nav.set_sync_state("Reconnecting…")
    assert "Reconnecting" in nav.sync_status_lbl.text()

    nav.set_sync_state("Offline")
    assert "Offline" in nav.sync_status_lbl.text()


# =============================================================================
# SECTION 9: Application Settings, Preferences & Themes (Dark/Light)
# =============================================================================

def test_settings_dialog_tabs_and_theme_switching(qapp, crypto_env):
    """
    Verifies SettingsDialog displays Account, Sync, Security, and Appearance tabs,
    and emits theme_changed signal upon selection.
    """
    dialog = SettingsDialog(account_email="alice@example.invalid")

    assert dialog.email_val.text() == "alice@example.invalid"

    theme_selected = None
    def on_theme(th):
        nonlocal theme_selected
        theme_selected = th

    dialog.theme_changed.connect(on_theme)

    # Switch to Light Theme
    dialog.theme_combo.setCurrentIndex(1)
    assert theme_selected == "light"

    # Switch back to Dark Theme
    dialog.theme_combo.setCurrentIndex(0)
    assert theme_selected == "dark"

    dialog.close()


# =============================================================================
# SECTION 10: Clean Shutdown, Resource Cleanup & Memory Safety
# =============================================================================

def test_clean_window_shutdown_releases_resources(qapp, crypto_env):
    """
    Verifies that closing MailboxWindow stops polling timers, disposes settings,
    locks identity session, and terminates thread pool without hanging.
    """
    mock_identity = make_mock_identity(crypto_env)
    window = MailboxWindow(mock_identity, gmail_enabled=False)

    window.show()
    qapp.processEvents()

    assert window.timer.isActive()

    window.close()
    assert window.timer.isActive() is False
    assert mock_identity.lock.called
    assert window.pool._shutdown is True
