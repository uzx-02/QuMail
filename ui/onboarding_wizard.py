"""
Guided account onboarding wizard for QuMail employees.

Provides a 4-step progressive onboarding flow:
  1. Welcome & Introduction
  2. How Protected Email Works (plain corporate language)
  3. Permission Transparency & Google Account Connection
  4. Local Security Vault Readiness Confirmation

Avoids exposing database internals, cryptographic revisions, or raw settings.
"""

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QStackedWidget, QFrame, QMessageBox
)

from ui.design_system import C, GLOBAL_STYLESHEET


class _BrandIcon(QWidget):
    """Painted QuMail 'Q' shield logo."""
    def __init__(self, size: int = 56, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self._size
        cx = s / 2
        grad = QLinearGradient(0.0, 0.0, float(s), float(s))
        grad.setColorAt(0, QColor(C["accent"]))
        grad.setColorAt(1, QColor(C["accent_glow"]))

        shield = QPainterPath()
        shield.moveTo(cx, s * 0.05)
        shield.lineTo(s * 0.9, s * 0.22)
        shield.lineTo(s * 0.9, s * 0.58)
        shield.quadTo(s * 0.9, s * 0.90, cx, s * 0.96)
        shield.quadTo(s * 0.1, s * 0.90, s * 0.1, s * 0.58)
        shield.lineTo(s * 0.1, s * 0.22)
        shield.closeSubpath()
        p.fillPath(shield, grad)

        p.setPen(QColor("#FFFFFF"))
        f = p.font()
        f.setPointSize(int(s * 0.38))
        f.setBold(True)
        p.setFont(f)
        p.drawText(0, 0, s, s, Qt.AlignmentFlag.AlignCenter, "Q")


class OnboardingWizard(QDialog):
    """Guided onboarding dialog for first-run or new account setup."""

    completed = pyqtSignal(str)  # Emits connected email on completion

    def __init__(self, identity_service, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.identity = identity_service
        self.setWindowTitle("QuMail Setup Guide")
        self.setFixedSize(620, 520)
        self.setStyleSheet(GLOBAL_STYLESHEET)

        self._build_ui()

        # Connect session updates to detect completed authorization
        if hasattr(self.identity, 'session'):
            self.identity.session.changed.connect(self._on_session_changed)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        # Top progress indicator
        self._step_label = QLabel("STEP 1 OF 4")
        self._step_label.setStyleSheet(f"color: {C['accent_light']}; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        layout.addWidget(self._step_label)

        # Stacked pages
        self._stack = QStackedWidget()
        self._stack.addWidget(self._page_welcome())      # 0
        self._stack.addWidget(self._page_how_it_works()) # 1
        self._stack.addWidget(self._page_connect())      # 2
        self._stack.addWidget(self._page_ready())        # 3

        layout.addWidget(self._stack, stretch=1)

    # ── Page 1: Welcome ───────────────────────────────────────────────────────
    def _page_welcome(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 8, 0, 0)
        l.setSpacing(16)

        logo = _BrandIcon(size=64)
        l.addWidget(logo, alignment=Qt.AlignmentFlag.AlignLeft)

        title = QLabel("Welcome to QuMail")
        title.setStyleSheet(f"color: {C['text_primary']}; font-size: 24px; font-weight: 700;")
        l.addWidget(title)

        desc = QLabel(
            "QuMail is your corporate email client designed for high-assurance confidentiality.\n\n"
            "Unlike conventional email, your protected messages are encrypted directly on your computer "
            "before transmission. Only your intended recipients can decrypt and read your communications."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {C['text_secondary']}; font-size: 13px; line-height: 1.5;")
        l.addWidget(desc)

        l.addStretch()

        btn = QPushButton("Get Started →")
        btn.setStyleSheet(f"background: {C['accent']}; color: #FFF; font-weight: 700; padding: 12px 24px; border-radius: 8px;")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self._go_step(1))
        l.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)
        return w

    # ── Page 2: How Protected Email Works ────────────────────────────────────
    def _page_how_it_works(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 8, 0, 0)
        l.setSpacing(14)

        title = QLabel("How Protected Email Works")
        title.setStyleSheet(f"color: {C['text_primary']}; font-size: 20px; font-weight: 700;")
        l.addWidget(title)

        pillars = [
            ("🔒 Local Encryption", "Your messages and attachments are encrypted locally using recipient-owned OpenPGP keys. Cloud servers never hold your decryption keys."),
            ("🛡️ Cryptographic Verification", "Every sent email is cryptographically signed with your identity root. Recipients verify your authentic identity before release."),
            ("📜 Honest Delivery States", "QuMail distinguishes server acceptance from confirmed delivery. You always know the true cryptographic state of your outbox."),
        ]
        for header, text in pillars:
            box = QFrame()
            box.setStyleSheet(f"background: {C['bg_card']}; border: 1px solid {C['border']}; border-radius: 8px; padding: 10px;")
            bl = QVBoxLayout(box)
            bl.setSpacing(4)
            h = QLabel(header)
            h.setStyleSheet(f"color: {C['text_primary']}; font-weight: 600; font-size: 13px;")
            b = QLabel(text)
            b.setWordWrap(True)
            b.setStyleSheet(f"color: {C['text_secondary']}; font-size: 12px;")
            bl.addWidget(h)
            bl.addWidget(b)
            l.addWidget(box)

        l.addStretch()

        bar = QHBoxLayout()
        back = QPushButton("← Back")
        back.setStyleSheet(f"background: transparent; color: {C['text_secondary']}; border: 1px solid {C['border']}; padding: 10px 18px; border-radius: 8px;")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(lambda: self._go_step(0))
        bar.addWidget(back)
        bar.addStretch()

        next_btn = QPushButton("Next: Connect Account →")
        next_btn.setStyleSheet(f"background: {C['accent']}; color: #FFF; font-weight: 700; padding: 10px 22px; border-radius: 8px;")
        next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        next_btn.clicked.connect(lambda: self._go_step(2))
        bar.addWidget(next_btn)
        l.addLayout(bar)
        return w

    # ── Page 3: Connect Account & Permission Transparency ────────────────────
    def _page_connect(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 8, 0, 0)
        l.setSpacing(14)

        title = QLabel("Connect Your Google Account")
        title.setStyleSheet(f"color: {C['text_primary']}; font-size: 20px; font-weight: 700;")
        l.addWidget(title)

        info = QLabel(
            "QuMail connects to Gmail using standard Google OAuth 2.0 PKCE authentication.\n"
            "Your password is never accessed or stored. Security tokens are protected by your "
            "Windows Credential Manager."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {C['text_secondary']}; font-size: 12px;")
        l.addWidget(info)

        perm_box = QFrame()
        perm_box.setStyleSheet(f"background: {C['bg_card']}; border: 1px solid {C['border']}; border-radius: 8px; padding: 10px;")
        pbl = QVBoxLayout(perm_box)
        pbl.setSpacing(6)
        pbl.addWidget(QLabel("<b>Requested Permissions:</b>", styleSheet=f"color: {C['text_primary']};"))
        pbl.addWidget(QLabel("• <b>Read mail (IMAP PEEK):</b> Fetches incoming protected messages without changing read states on Google.", styleSheet=f"color: {C['text_secondary']}; font-size: 11px;"))
        pbl.addWidget(QLabel("• <b>Send mail (SMTP):</b> Submits encrypted OpenPGP ciphertext through your Gmail account.", styleSheet=f"color: {C['text_secondary']}; font-size: 11px;"))
        l.addWidget(perm_box)

        lbl = QLabel("Your Gmail Address:")
        lbl.setStyleSheet(f"color: {C['text_primary']}; font-weight: 600; font-size: 12px;")
        l.addWidget(lbl)

        self._email_input = QLineEdit()
        self._email_input.setPlaceholderText("user@gmail.com")
        self._email_input.setStyleSheet(f"background: {C['bg_hover']}; border: 1px solid {C['border']}; border-radius: 6px; padding: 8px 12px; font-size: 13px; color: {C['text_primary']};")
        l.addWidget(self._email_input)

        self._auth_status = QLabel("")
        self._auth_status.setWordWrap(True)
        self._auth_status.setStyleSheet(f"color: {C['accent_light']}; font-size: 12px;")
        l.addWidget(self._auth_status)

        l.addStretch()

        bar = QHBoxLayout()
        back = QPushButton("← Back")
        back.setStyleSheet(f"background: transparent; color: {C['text_secondary']}; border: 1px solid {C['border']}; padding: 10px 18px; border-radius: 8px;")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(lambda: self._go_step(1))
        bar.addWidget(back)
        bar.addStretch()

        self._connect_btn = QPushButton("Connect with Google")
        self._connect_btn.setStyleSheet(f"background: {C['accent']}; color: #FFF; font-weight: 700; padding: 10px 22px; border-radius: 8px;")
        self._connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._connect_btn.clicked.connect(self._start_connection)
        bar.addWidget(self._connect_btn)
        l.addLayout(bar)
        return w

    # ── Page 4: Security Readiness ───────────────────────────────────────────
    def _page_ready(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 16, 0, 0)
        l.setSpacing(16)
        l.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("✅")
        icon.setStyleSheet("font-size: 48px;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(icon)

        title = QLabel("Security Environment Ready")
        title.setStyleSheet(f"color: {C['text_primary']}; font-size: 22px; font-weight: 700;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(title)

        self._ready_details = QLabel("Your account is connected and your local vault is initialized.")
        self._ready_details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ready_details.setWordWrap(True)
        self._ready_details.setStyleSheet(f"color: {C['text_secondary']}; font-size: 13px;")
        l.addWidget(self._ready_details)

        l.addStretch()

        finish_btn = QPushButton("Enter QuMail Mailbox →")
        finish_btn.setStyleSheet(f"background: {C['online']}; color: #000; font-weight: 700; font-size: 14px; padding: 12px 32px; border-radius: 8px;")
        finish_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        finish_btn.clicked.connect(self.accept)
        l.addWidget(finish_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        return w

    # ── Navigation & Actions ─────────────────────────────────────────────────
    def _go_step(self, step: int) -> None:
        if step < self._stack.currentIndex():
            self._cancel_auth()
        self._step_label.setText(f"STEP {step + 1} OF 4")
        self._stack.setCurrentIndex(step)

    def _start_connection(self) -> None:
        address = self._email_input.text().strip()
        if not address or "@" not in address:
            self._auth_status.setText("⚠️ Please enter a valid Gmail address.")
            return

        # Explicit confirmation for vault lifecycle (A3 requirement: no silent vault creation or unlock)
        try:
            snapshot = self.identity.session.snapshot
            if snapshot.locked:
                vault_path = str(self.identity.path) if hasattr(self.identity, 'path') else 'vault.sqlite'
                vault_exists = hasattr(self.identity, 'path') and self.identity.path.exists()
                if vault_exists:
                    reply = QMessageBox.question(
                        self,
                        'Unlock Security Vault',
                        f'An existing security vault was found at:\n\n{vault_path}\n\n'
                        'Unlock this vault to enroll your account?',
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes
                    )
                    if reply != QMessageBox.StandardButton.Yes:
                        self._auth_status.setText('Cancelled. Existing vault was not unlocked.')
                        return
                    self.identity.unlock(create=False)
                else:
                    reply = QMessageBox.question(
                        self,
                        'Create Security Vault',
                        f'No security vault database exists at:\n\n{vault_path}\n\n'
                        'A new encrypted local vault database will be created on disk.\n\n'
                        'Do you want to initialize a new vault?',
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No
                    )
                    if reply != QMessageBox.StandardButton.Yes:
                        self._auth_status.setText('Cancelled. No new vault was created.')
                        return
                    self.identity.unlock(create=True)
        except Exception as exc:
            self._auth_status.setText(f"⚠️ Vault initialization error: {exc}")
            return

        self._connect_btn.setEnabled(False)
        self._auth_status.setText("⏳ Opening browser for Google authorization…")

        # Start Google authorization flow via identity operations
        if hasattr(self.parent(), 'settings') and hasattr(self.parent().settings, 'start_auth'):
            self.parent().settings.address.setText(address)
            self.parent().settings.start_auth('enroll')
        else:
            # Fallback direct call if settings widget is available
            try:
                from core.settings_operations import Operations
                ops = Operations(self.identity)
                ops.start('enroll', address)
            except Exception as e:
                self._auth_status.setText(f"⚠️ Authorization start failed: {e}")
                self._connect_btn.setEnabled(True)

    def _cancel_auth(self) -> None:
        self._connect_btn.setEnabled(True)
        self._auth_status.setText("")
        if hasattr(self.parent(), 'settings') and hasattr(self.parent().settings, 'cancel'):
            self.parent().settings.cancel()

    def closeEvent(self, event) -> None:
        self._cancel_auth()
        event.accept()

    def _on_session_changed(self, snapshot) -> None:
        if snapshot.active and not snapshot.locked:
            self._ready_details.setText(
                f"Account: <b>{snapshot.active.address}</b><br><br>"
                f"OpenPGP Root Key: <tt>{snapshot.active.root}</tt><br>"
                f"Encrypted Vault: <b>Active & Ready</b>"
            )
            self.completed.emit(snapshot.active.address)
            self._go_step(3)
