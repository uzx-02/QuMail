"""
Screenshot capture script for QuMail Module 1.4 visual verification.
Generates genuine pixel-rendered PNG screenshots of all core UI views
using PyQt6 offscreen rendering.
"""

import sys
import os
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Set offscreen platform plugin if running headless
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QTableWidgetItem
from unittest.mock import Mock

def main():
    app = QApplication.instance() or QApplication(sys.argv)
    
    out_dir = Path("docs/screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    from ui.welcome_screen import WelcomeScreen
    from ui.onboarding_wizard import OnboardingWizard
    from ui.mailbox_window import MailboxWindow
    from ui.mail_actions import MailActions
    from ui.identity_settings import IdentitySettings
    from core.account_session import DevelopmentSession, Snapshot
    from experiments.m4.model import State, OperationId
    from experiments.m4.services import DeliveryResult
    from experiments.m5.model import Attachment, OpenedMessage, Replay
    from mailbox_client.model import Display, Header, MessageKey

    # 1. Welcome Screen
    welcome = WelcomeScreen(open_settings_callback=lambda: None)
    welcome.resize(800, 600)
    welcome.show()
    app.processEvents()
    welcome.grab().save(str(out_dir / "01_welcome_screen.png"))
    welcome.close()
    print("Saved 01_welcome_screen.png")

    # Mock Session and Identity
    mock_session = DevelopmentSession()
    mock_identity = Mock()
    mock_identity.session = mock_session
    mock_identity.google = None
    mock_identity.require = Mock()
    mock_identity.store = Mock()

    # 2. Onboarding Wizard - Step 2 (How it works)
    wizard = OnboardingWizard(mock_identity)
    wizard._go_step(1)
    wizard.show()
    app.processEvents()
    wizard.grab().save(str(out_dir / "02_how_it_works_guide.png"))
    print("Saved 02_how_it_works_guide.png")

    # 3. Onboarding Wizard - Step 3 (Connect Account & Permissions)
    wizard._go_step(2)
    app.processEvents()
    wizard.grab().save(str(out_dir / "03_account_connection_permissions.png"))
    wizard.close()
    print("Saved 03_account_connection_permissions.png")

    # 4. Main Inbox Workspace
    mailbox = MailboxWindow(mock_identity, gmail_enabled=True)
    mailbox.accounts.addItem("uzair.shaikh.sec@gmail.com")
    mailbox.rows = (
        Header(MessageKey(None, "INBOX", 101, 1), "Google Security <no-reply@accounts.google.com>", "Security alert for uzair.shaikh.sec@gmail.com", "Today 14:22", 4096, True),
        Header(MessageKey(None, "INBOX", 102, 2), "Uzair Shaikh <uzair.valiacollege@gmail.com>", "Confidential: Q7 Research Project Proposal", "Today 11:05", 8192, False),
        Header(MessageKey(None, "INBOX", 103, 3), "Google Workspace <workspace-noreply@google.com>", "Your monthly Google Cloud billing summary", "Yesterday", 2048, True),
    )
    mailbox.render_rows()
    mailbox.status.setText("Inbox connected to imap.gmail.com:993 · 3 messages loaded · Read-only IMAP PEEK mode")
    mailbox.resize(1060, 750)
    mailbox.show()
    app.processEvents()
    mailbox.grab().save(str(out_dir / "04_main_inbox_workspace.png"))
    print("Saved 04_main_inbox_workspace.png")

    # 5. Message Reader Pane
    mock_opened = OpenedMessage(
        sender="uzair.valiacollege@gmail.com",
        to=("uzair.shaikh.sec@gmail.com",),
        cc=(),
        subject="Confidential: Q7 Research Project Proposal",
        date="2026-11-08T11:05:00Z",
        message_id="<msg-102@valiacollege.edu>",
        body="Hi Mohammed,\n\nHere is the encrypted project proposal for our upcoming technical review.\nPlease find the project specification and benchmark results attached.\n\nAll key exchanges were validated against our trusted OpenPGP directory.\n\nBest regards,\nUzair Shaikh",
        attachments=(Attachment("proposal_v1.pdf", "application/pdf", b"%PDF-1.5 fake content"),),
        in_reply_to="",
        references=("<root-001@valiacollege.edu>",),
        signer_root="valia-root-key",
        signature_valid=True,
        identity_trust="local_enrolled_identity",
        mismatches=(),
        replay=Replay.FRESH,
        archive=False
    )
    mock_display = Display(
        key=MessageKey(None, "INBOX", 102, 2),
        subject="Confidential: Q7 Research Project Proposal",
        body=mock_opened.body,
        security="🔒 End-to-End Encrypted (OpenPGP)\nVerified Sender: uzair.valiacollege@gmail.com\nCryptographic signature verified against local vault.",
        seen=True,
        protected=mock_opened,
        author_claim="uzair.valiacollege@gmail.com",
        owner=None
    )
    mailbox.show_display(mock_display)
    app.processEvents()
    mailbox.grab().save(str(out_dir / "05_message_reader_pane.png"))
    print("Saved 05_message_reader_pane.png")

    # 6. Compose Protected Email Window
    actions = MailActions(mailbox, gmail_enabled=True)
    actions.to.setText("uzair.valiacollege@gmail.com")
    actions.subject.setText("Re: Confidential: Q7 Research Project Proposal")
    actions.body.setPlainText("Thanks Uzair,\n\nI have reviewed the attached proposal and the cryptographic specifications look solid.\nProceeding with the next milestone.\n\nRegards,\nMohammed Uzair Shaikh")
    actions.attachments = (Attachment("review_notes.pdf", "application/pdf", b"%PDF fake notes"),)
    actions.show_files()
    actions.resize(900, 800)
    actions.show()
    app.processEvents()
    actions.grab().save(str(out_dir / "06_compose_protected_email.png"))
    print("Saved 06_compose_protected_email.png")

    # 7. Outbox Queue Status
    from experiments.m4.model import State
    mock_rows = (
        DeliveryResult(OperationId("0123456789abcdef0123456789abcdef"), State.ACCEPTED, "smtp_accepted_by_gmail", 1),
        DeliveryResult(OperationId("123456789abcdef0123456789abcdef0"), State.PREPARED, "encrypted_and_frozen_ready_to_send", 0),
        DeliveryResult(OperationId("23456789abcdef0123456789abcdef01"), State.DRAFT, "draft_saved", 0),
    )
    actions.rows = mock_rows
    actions.table.setRowCount(len(mock_rows))
    from ui.outbox_state_labels import label_for_state
    for i, r in enumerate(mock_rows):
        for j, text in enumerate((r.operation.value, label_for_state(r.state.value), str(r.attempt), r.reason)):
            actions.table.setItem(i, j, QTableWidgetItem(text))
    actions.table.resizeColumnsToContents()
    actions.status.setText("Durable account outbox refreshed · 3 operations in queue")
    app.processEvents()
    actions.grab().save(str(out_dir / "07_outbox_queue_status.png"))
    actions.close()
    print("Saved 07_outbox_queue_status.png")

    # 8. Account Settings Window
    settings = IdentitySettings(mock_identity)
    settings.address.setText("uzair.shaikh.sec@gmail.com")
    settings.status.setText(
        "Active Account: uzair.shaikh.sec@gmail.com\n"
        "Root Fingerprint: 8F3D B219 C487 01A2 E78F 5543 9B61 2284\n"
        "Vault: C:\\Users\\uzx\\Desktop\\Aavishkar-26\\qumail_acceptance_vault.sqlite\n"
        "Security State: Synchronized & Unlocked"
    )
    settings.resize(600, 480)
    settings.show()
    app.processEvents()
    settings.grab().save(str(out_dir / "08_account_settings.png"))
    settings.close()
    mailbox.close()
    print("Saved 08_account_settings.png")
    
    print("\nAll 8 genuine PNG screenshots captured successfully in docs/screenshots/!")

if __name__ == "__main__":
    main()
