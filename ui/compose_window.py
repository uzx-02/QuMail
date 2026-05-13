# ui/compose_window.py — Email composition view.
# Single responsibility: present the compose form, drive the full send pipeline
# (recipient check → encrypt → encapsulate → send → certificate → PDF → portal),
# and report the outcome to the user in plain language.
# All pipeline work runs on a background thread to keep the UI responsive.
# Do not implement crypto, transport, or certificate logic here — delegate only.

import os
import subprocess
import sys
from dataclasses import dataclass

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QClipboard, QPainter, QColor, QPainterPath, QLinearGradient
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QScrollArea,
    QFrame,
)

from core.config import TQR_LEVEL_AES, TQR_LEVEL_MLKEM, TQR_LEVEL_OTP
from core.session import session


# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------

_C = {
    "bg_base":       "#0D1117",
    "bg_sidebar":    "#161B22",
    "bg_card":       "#1C2231",
    "bg_hover":      "#21293A",
    "accent":        "#6366F1",
    "accent_light":  "#818CF8",
    "accent_glow":   "#4F46E5",
    "accent_muted":  "#1E2238",
    "text_primary":  "#E6EDF3",
    "text_secondary":"#8B949E",
    "text_tertiary": "#484F58",
    "border":        "#21262D",
    "online":        "#22C55E",
    "offline":       "#EF4444",
}


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LEVEL_LABELS: dict[int, str] = {
    TQR_LEVEL_OTP:   "Maximum",
    TQR_LEVEL_AES:   "High",
    TQR_LEVEL_MLKEM: "Quantum-Safe",
}
_LEVEL_ICONS: dict[int, str] = {
    TQR_LEVEL_OTP:   "🔒",
    TQR_LEVEL_AES:   "🛡️",
    TQR_LEVEL_MLKEM: "⚛️",
}
_LEVEL_TOOLTIPS: dict[int, str] = {
    TQR_LEVEL_OTP:   "One-time quantum key — strongest protection. Requires active Quantum Network.",
    TQR_LEVEL_AES:   "Quantum-seeded AES-256 — strong and fast. Requires Quantum Network.",
    TQR_LEVEL_MLKEM: "Post-quantum ML-KEM — works offline, no Quantum Network required.",
}
_LEVEL_COLORS: dict[int, tuple[str, str, str]] = {
    # (active_fg, active_bg, hover_bg)
    TQR_LEVEL_OTP:   ("#D1FAE5", "#064E3B", "#065F46"),
    TQR_LEVEL_AES:   ("#DBEAFE", "#1E3A5F", "#1E40AF"),
    TQR_LEVEL_MLKEM: ("#EDE9FE", "#2E1065", "#3B0764"),
}
_ORDERED_LEVELS: list[int] = [TQR_LEVEL_OTP, TQR_LEVEL_AES, TQR_LEVEL_MLKEM]


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

_STYLE_FIELD_LABEL = f"""
    QLabel {{
        color: {_C['text_secondary']};
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.5px;
    }}
"""
_STYLE_INPUT = f"""
    QLineEdit, QPlainTextEdit {{
        color: {_C['text_primary']};
        background-color: transparent;
        border: none;
        border-bottom: 1px solid {_C['border']};
        border-radius: 0px;
        padding: 8px 2px;
        font-size: 13px;
        selection-background-color: {_C['accent_muted']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus {{
        border-bottom: 2px solid {_C['accent']};
    }}
"""
_STYLE_SEND_BTN = f"""
    QPushButton {{
        font-size: 14px;
        font-weight: 700;
        color: #FFFFFF;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {_C['accent']}, stop:1 {_C['accent_glow']});
        border: none;
        border-radius: 10px;
        padding: 12px 32px;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {_C['accent_light']}, stop:1 {_C['accent']});
    }}
    QPushButton:pressed {{
        background-color: {_C['accent_glow']};
    }}
    QPushButton:disabled {{
        background: {_C['bg_card']};
        color: {_C['text_tertiary']};
    }}
"""
_STYLE_HINT_LABEL = f"""
    QLabel {{
        color: {_C['text_tertiary']};
        font-size: 11px;
        font-style: italic;
    }}
"""
_STYLE_CARD = f"""
    QWidget#compose_card {{
        background-color: {_C['bg_card']};
        border: 1px solid {_C['border']};
        border-radius: 12px;
    }}
"""


# ---------------------------------------------------------------------------
# Security Level Pill Selector
# ---------------------------------------------------------------------------

class _SecurityPillSelector(QWidget):
    """
    Three pill buttons for selecting the encryption level.
    Each pill has a distinct colour, icon, and label.
    Emits level_changed(int) when selection changes.
    """

    level_changed = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._selected: int = session.tqr_level
        self._buttons: dict[int, QPushButton] = {}
        self._build()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        for level in _ORDERED_LEVELS:
            icon  = _LEVEL_ICONS[level]
            label = _LEVEL_LABELS[level]
            btn = QPushButton(f"{icon}  {label}")
            btn.setToolTip(_LEVEL_TOOLTIPS[level])
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(False)
            btn.setFixedHeight(34)
            btn.clicked.connect(lambda checked, lv=level: self._select(lv))
            self._buttons[level] = btn
            layout.addWidget(btn)

        layout.addStretch()
        self._refresh_styles()

    def _pill_style(self, level: int) -> str:
        active = level == self._selected
        if active:
            fg, bg, hover = _LEVEL_COLORS[level]
        else:
            fg, bg, hover = (_C["text_secondary"], _C["bg_hover"], _C["bg_card"])
        return (
            f"QPushButton {{ color: {fg}; background: {bg}; border: 1px solid "
            f"{'transparent' if not active else fg + '44'}; border-radius: 8px; "
            f"font-size: 12px; font-weight: {'700' if active else '400'}; padding: 4px 14px; }}"
            f"QPushButton:hover {{ background: {hover}; color: {fg if active else _C['text_primary']}; }}"
        )

    def _select(self, level: int) -> None:
        if level == self._selected:
            return
        self._selected = level
        self._refresh_styles()
        self.level_changed.emit(level)

    def _refresh_styles(self) -> None:
        for level, btn in self._buttons.items():
            btn.setStyleSheet(self._pill_style(level))

    def selected_level(self) -> int:
        return self._selected

    def set_level(self, level: int) -> None:
        if level in self._buttons:
            self._selected = level
            self._refresh_styles()


# ---------------------------------------------------------------------------
# Send Pipeline (data classes + worker — logic unchanged)
# ---------------------------------------------------------------------------

@dataclass
class _SendPayload:
    sender:        str
    recipient:     str
    subject:       str
    body:          str
    tqr_level:     int
    portal_mode:   bool
    sae_id:        str


@dataclass
class _SendResult:
    cert_id:      str
    pdf_path:     str
    portal_url:   str | None


class _SendWorker(QObject):
    finished = pyqtSignal(object)
    failed   = pyqtSignal(str)

    def __init__(self, payload: _SendPayload) -> None:
        super().__init__()
        self._payload = payload

    def run(self) -> None:
        try:
            result = self._execute()
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(_user_message_for(exc))

    def _execute(self) -> _SendResult:
        from crypto.tqr import encrypt
        from mime.encapsulator import encapsulate
        from transport.smtp_sender import send_email
        from certificates.cert_generator import generate
        from certificates.pdf_export import export

        p = self._payload
        plaintext = p.body.encode("utf-8")

        result_dict, private_key = encrypt(
            plaintext=plaintext,
            tqr_level=p.tqr_level,
            sae_id=p.sae_id,
            recipient_is_qumail=not p.portal_mode,
        )
        ciphertext: bytes = result_dict["ciphertext"]
        metadata:   dict  = result_dict["metadata"]

        mime_message = encapsulate(
            sender=p.sender, recipient=p.recipient, subject=p.subject,
            ciphertext=ciphertext, metadata=metadata,
        )
        send_email(p.sender, p.recipient, mime_message)

        key_id = metadata.get("key_id", "")
        cert, json_path = generate(
            tqr_level=p.tqr_level, key_id=key_id,
            sender=p.sender, recipient_email=p.recipient,
        )
        session.last_key_uuid  = key_id or None
        session.last_cert_path = json_path

        pdf_path = export(json_path)

        portal_url: str | None = None
        if p.portal_mode:
            from portal.portal_server import store_session, start as start_portal
            portal_url = store_session(ciphertext, metadata, private_key)
            # In cloud mode the Cloud Run service handles requests — no local server needed.
            if os.getenv("PORTAL_MODE", "local").lower() != "cloud":
                start_portal()

        if private_key and key_id:
            _persist_send_key(key_id, private_key)

        return _SendResult(cert_id=cert.cert_id, pdf_path=pdf_path, portal_url=portal_url)


def _persist_send_key(cert_id: str, private_key: bytes) -> None:
    import stat
    try:
        from cryptography.fernet import Fernet
        from core.config import SEND_KEYS_DIR
        _MASTER_KEY_PATH = "secrets/oauth_master.key"
        os.makedirs(SEND_KEYS_DIR, exist_ok=True)
        try:
            os.chmod(SEND_KEYS_DIR, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        except OSError:
            pass
        with open(_MASTER_KEY_PATH, "rb") as f:
            fernet = Fernet(f.read())
        encrypted_key = fernet.encrypt(private_key)
        key_path = os.path.join(SEND_KEYS_DIR, f"{cert_id}.key")
        with open(key_path, "wb") as f:
            f.write(encrypted_key)
        try:
            os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    except Exception:
        pass


def _user_message_for(exc: Exception) -> str:
    name = type(exc).__name__
    _map = {
        "CertGenerationError": "The encryption certificate could not be saved.",
        "PdfExportError":      "The certificate PDF could not be created.",
        "SMTPSenderError":     "The message could not be sent. Check your connection.",
        "RecipientCheckError": "Could not verify the recipient on the Quantum Network.",
        "TQREncryptionError":  "Message encryption failed. Please try again.",
        "TQRKeyError":         "A required quantum key could not be retrieved.",
        "TQRLevelError":       "The selected security level is not supported.",
    }
    return _map.get(name, f"Something went wrong: {exc}")


# ---------------------------------------------------------------------------
# Compose Window
# ---------------------------------------------------------------------------

class ComposeWindow(QWidget):
    """
    Full-page card compose view with a dark enterprise design.
    Fields use Gmail-style borderless-with-underline inputs inside a card.
    The security level selector uses coloured pill chips.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _SendWorker | None = None
        self._build_ui()
        session.account_changed.connect(self._on_account_changed)

    def _on_account_changed(self, email: str) -> None:
        """
        Clear all compose fields when the active account changes.
        Prevents draft content from one account context leaking into another.
        """
        self._to_field.clear()
        self._subject_field.clear()
        self._body_field.clear()

    # --- UI Construction ---

    def _build_ui(self) -> None:
        # Outer layout — scroll area so small windows don't truncate
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Page header
        header = QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet(
            f"background-color: {_C['bg_sidebar']}; border-bottom: 1px solid {_C['border']};"
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(28, 0, 28, 0)

        title = QLabel("New Message")
        title.setStyleSheet(
            f"color: {_C['text_primary']}; font-size: 18px; font-weight: 700;"
        )
        header_layout.addWidget(title)
        header_layout.addStretch()
        outer.addWidget(header)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {_C['bg_base']}; border: none; }}"
        )

        content = QWidget()
        content.setStyleSheet(f"background: {_C['bg_base']};")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(40, 32, 40, 32)
        content_layout.setSpacing(0)

        # Card
        card = QWidget()
        card.setObjectName("compose_card")
        card.setStyleSheet(_STYLE_CARD)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 24, 28, 28)
        card_layout.setSpacing(0)

        # ── To field ───────────────────────────────────────────
        card_layout.addWidget(self._field_label("TO"))
        self._to_field = QLineEdit()
        self._to_field.setPlaceholderText("recipient@example.com")
        self._to_field.setStyleSheet(_STYLE_INPUT)
        card_layout.addWidget(self._to_field)
        card_layout.addSpacing(16)

        # ── Subject field ──────────────────────────────────────
        card_layout.addWidget(self._field_label("SUBJECT"))
        self._subject_field = QLineEdit()
        self._subject_field.setPlaceholderText("Enter a subject…")
        self._subject_field.setStyleSheet(_STYLE_INPUT)
        card_layout.addWidget(self._subject_field)
        card_layout.addSpacing(16)

        # ── Divider ────────────────────────────────────────────
        div = QWidget()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background-color: {_C['border']};")
        card_layout.addWidget(div)
        card_layout.addSpacing(16)

        # ── Message body ───────────────────────────────────────
        card_layout.addWidget(self._field_label("MESSAGE"))
        self._body_field = QPlainTextEdit()
        self._body_field.setPlaceholderText("Write your message here…")
        self._body_field.setStyleSheet(_STYLE_INPUT)
        self._body_field.setMinimumHeight(240)
        card_layout.addWidget(self._body_field)
        card_layout.addSpacing(28)

        # ── Security Level ─────────────────────────────────────
        security_label_row = QHBoxLayout()
        security_label_row.addWidget(self._field_label("ENCRYPTION LEVEL"))
        security_label_row.addStretch()
        card_layout.addLayout(security_label_row)
        card_layout.addSpacing(10)

        self._toggle = _SecurityPillSelector()
        self._toggle.level_changed.connect(self._on_level_changed)
        card_layout.addWidget(self._toggle)
        card_layout.addSpacing(6)

        self._level_hint = QLabel(self._hint_for(session.tqr_level))
        self._level_hint.setStyleSheet(_STYLE_HINT_LABEL)
        card_layout.addWidget(self._level_hint)
        card_layout.addSpacing(28)

        # ── Send button ────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._send_btn = QPushButton("  🔐  Send Securely")
        self._send_btn.setStyleSheet(_STYLE_SEND_BTN)
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setFixedHeight(46)
        self._send_btn.clicked.connect(self._on_send_clicked)
        btn_row.addWidget(self._send_btn)
        card_layout.addLayout(btn_row)

        content_layout.addWidget(card)
        content_layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(_STYLE_FIELD_LABEL)
        return label

    # --- Level Toggle ---

    def _on_level_changed(self, level: int) -> None:
        session.tqr_level = level
        self._level_hint.setText(self._hint_for(level))

    @staticmethod
    def _hint_for(level: int) -> str:
        hints = {
            TQR_LEVEL_OTP:   "One-time quantum key — strongest possible protection, requires Quantum Network.",
            TQR_LEVEL_AES:   "Quantum-seeded AES-256 — strong, fast, requires Quantum Network.",
            TQR_LEVEL_MLKEM: "Post-quantum ML-KEM — works without Quantum Network.",
        }
        return hints.get(level, "")

    # --- Send Flow ---

    def _on_send_clicked(self) -> None:
        sender = session.active_account
        if not sender:
            self._alert("Not signed in", "Sign in to an account in Settings before sending.")
            return

        recipient = self._to_field.text().strip()
        if not recipient:
            self._alert("Missing recipient", "Please enter a recipient email address.")
            return

        subject = self._subject_field.text().strip()
        if not subject:
            self._alert("Missing subject", "Please enter a subject for your message.")
            return

        body = self._body_field.toPlainText().strip()
        if not body:
            self._alert("Empty message", "Please write a message before sending.")
            return

        from transport.recipient_check import check_recipient, RecipientCheckError
        try:
            recipient_status = check_recipient(recipient)
            is_qumail = recipient_status.is_qumail
            sae_id = recipient_status.sae_id
        except RecipientCheckError:
            # KME unreachable or lookup failed — treat as non-QuMail to trigger Portal Fallback
            is_qumail = False
            sae_id = None

        effective_level = self._toggle.selected_level()
        portal_mode     = False

        if not is_qumail:
            confirmed = self._confirm_portal_fallback(recipient)
            if not confirmed:
                return
            effective_level = TQR_LEVEL_MLKEM
            portal_mode     = True
            self._toggle.set_level(TQR_LEVEL_MLKEM)
            self._level_hint.setText(self._hint_for(TQR_LEVEL_MLKEM))
        elif effective_level in (TQR_LEVEL_OTP, TQR_LEVEL_AES) and not sae_id:
            self._alert(
                "Recipient setup incomplete",
                "The recipient appears to use QuMail, but no Quantum Network ID was found. "
                "Please try again later.",
            )
            return

        if effective_level in (TQR_LEVEL_OTP, TQR_LEVEL_AES):
            if not session.kme_connected:
                self._alert(
                    "Quantum Network unavailable",
                    "The selected security level requires a Quantum Network connection, "
                    "which is currently offline.\n\n"
                    "Switch to Quantum-Safe level to send without the network, "
                    "or check your connection and try again.",
                )
                return

        payload = _SendPayload(
            sender=sender, recipient=recipient, subject=subject, body=body,
            tqr_level=effective_level, portal_mode=portal_mode,
            sae_id=sae_id or "",
        )
        self._run_pipeline(payload)

    def _confirm_portal_fallback(self, recipient: str) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Recipient not on QuMail")
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setText(f"<b>{recipient}</b> doesn't use QuMail.")
        dialog.setInformativeText(
            "Your message will be encrypted using quantum-safe encryption and "
            "delivered as a secure link. The recipient can open it in their browser "
            "— no QuMail installation required.\n\n"
            "The encryption level will be set to Quantum-Safe automatically."
        )
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        dialog.button(QMessageBox.StandardButton.Ok).setText("Send via Secure Link")
        dialog.button(QMessageBox.StandardButton.Cancel).setText("Cancel")
        return dialog.exec() == QMessageBox.StandardButton.Ok

    def _run_pipeline(self, payload: _SendPayload) -> None:
        self._send_btn.setEnabled(False)
        self._send_btn.setText("  ⏳  Sending…")

        self._thread = QThread()
        self._worker = _SendWorker(payload)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_send_success)
        self._worker.failed.connect(self._on_send_failure)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    # --- Outcome Handlers ---

    def _on_send_success(self, result: _SendResult) -> None:
        self._send_btn.setEnabled(True)
        self._send_btn.setText("  🔐  Send Securely")
        dialog = _SuccessDialog(result, parent=self)
        dialog.exec()
        self._to_field.clear()
        self._subject_field.clear()
        self._body_field.clear()

    def _on_send_failure(self, message: str) -> None:
        self._send_btn.setEnabled(True)
        self._send_btn.setText("  🔐  Send Securely")
        self._alert("Message not sent", message)

    def _alert(self, title: str, message: str) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(message)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()


# ---------------------------------------------------------------------------
# Success Dialog
# ---------------------------------------------------------------------------

class _SuccessDialog(QDialog):
    def __init__(self, result: _SendResult, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._result = result
        self.setWindowTitle("Message sent")
        self.setMinimumWidth(440)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(10)

        # Header with checkmark
        header = QLabel("✅  Message sent securely")
        header.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {_C['text_primary']};"
        )
        layout.addWidget(header)

        body = QLabel(
            "Your message was encrypted and delivered successfully. "
            "An encryption certificate has been saved for your records."
        )
        body.setWordWrap(True)
        body.setStyleSheet(f"font-size: 12px; color: {_C['text_secondary']};")
        layout.addWidget(body)

        # Portal URL if applicable
        if self._result.portal_url:
            layout.addSpacing(8)
            oob_label = QLabel(
                "🔐 Share the link below privately (e.g. SMS or WhatsApp). "
                "Sending it by email would defeat the encryption."
            )
            oob_label.setWordWrap(True)
            oob_label.setStyleSheet(
                f"font-size: 11px; color: {_C['text_secondary']}; "
                f"background: #2D2A00; border-radius: 6px; padding: 8px 10px;"
            )
            layout.addWidget(oob_label)

            url_row = QHBoxLayout()
            url_value = QLabel(
                f'<a href="{self._result.portal_url}" '
                f'style="color: {_C["accent_light"]}; text-decoration: none;">'
                f'{self._result.portal_url}</a>'
            )
            url_value.setOpenExternalLinks(True)
            url_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            url_value.setStyleSheet(
                f"font-family: 'Consolas', monospace; font-size: 10px; "
                f"color: {_C['accent_light']}; background: {_C['bg_card']}; "
                f"border-radius: 4px; padding: 5px 8px;"
            )
            url_row.addWidget(url_value, stretch=1)

            copy_btn = QPushButton("Copy")
            copy_btn.setStyleSheet(
                f"QPushButton {{ color: {_C['accent_light']}; background: {_C['accent_muted']}; "
                f"border: none; border-radius: 5px; padding: 5px 12px; font-size: 11px; "
                f"font-weight: 600; }} "
                f"QPushButton:hover {{ background: {_C['accent']}; color: #FFF; }}"
            )
            _url = self._result.portal_url
            copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(_url))
            url_row.addWidget(copy_btn)
            layout.addLayout(url_row)

        layout.addSpacing(14)

        btn_row = QDialogButtonBox()
        open_cert_btn = QPushButton("Open Certificate")
        open_cert_btn.setStyleSheet(
            f"QPushButton {{ font-size: 13px; font-weight: 600; color: #FFF; "
            f"background: {_C['accent']}; border: none; border-radius: 7px; padding: 8px 20px; }} "
            f"QPushButton:hover {{ background: {_C['accent_light']}; }}"
        )
        open_cert_btn.clicked.connect(self._open_cert)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            f"QPushButton {{ font-size: 13px; color: {_C['text_secondary']}; "
            f"background: {_C['bg_card']}; border: 1px solid {_C['border']}; "
            f"border-radius: 7px; padding: 8px 20px; }} "
            f"QPushButton:hover {{ color: {_C['text_primary']}; background: {_C['bg_hover']}; }}"
        )
        close_btn.clicked.connect(self.accept)

        btn_row.addButton(open_cert_btn, QDialogButtonBox.ButtonRole.ActionRole)
        btn_row.addButton(close_btn,    QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(btn_row)

    def _open_cert(self) -> None:
        path = self._result.pdf_path
        if not os.path.exists(path):
            return
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", path], check=False)
