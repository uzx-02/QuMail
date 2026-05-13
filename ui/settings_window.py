# ui/settings_window.py — Account and runtime preferences panel.
# Single responsibility: manage account OAuth2 connect/disconnect, select default
# TQR level for the session, and update the KME endpoint used by kme_client.
# Does not send email, read inbox messages, or perform encryption.
# Do not import from mime/, portal/, or certificates/.

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient
from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QFrame,
    QScrollArea,
    QStackedWidget,
)

from core.config import KME_BASE_URL, TQR_LEVEL_AES, TQR_LEVEL_MLKEM, TQR_LEVEL_OTP
from core.session import session
from kme.kme_client import KMEConnectionError, kme_client
from transport.oauth2_gmail import GmailAuthError, get_access_token as gmail_access_token
from transport.oauth2_gmail import revoke_token as revoke_gmail_token
from transport.oauth2_yahoo import YahooAuthError, get_access_token as yahoo_access_token
from transport.oauth2_yahoo import revoke_token as revoke_yahoo_token
from PyQt6.QtCore import QThread, pyqtSignal


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
    "warning":       "#F59E0B",
}


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

_STYLE_TAB_BTN = f"""
    QPushButton {{
        color: {_C['text_secondary']};
        background: transparent;
        border: none;
        border-bottom: 2px solid transparent;
        font-size: 13px;
        font-weight: 500;
        padding: 10px 20px;
        border-radius: 0;
    }}
    QPushButton:hover {{
        color: {_C['text_primary']};
    }}
    QPushButton[active="true"] {{
        color: {_C['accent_light']};
        border-bottom: 2px solid {_C['accent']};
        font-weight: 700;
    }}
"""
_STYLE_LABEL = f"color: {_C['text_secondary']}; font-size: 12px;"
_STYLE_VALUE_LABEL = f"color: {_C['text_primary']}; font-size: 13px; font-weight: 600;"
_STYLE_HINT = f"color: {_C['text_tertiary']}; font-size: 11px;"
_STYLE_INPUT = f"""
    QLineEdit, QComboBox {{
        color: {_C['text_primary']};
        background-color: {_C['bg_hover']};
        border: 1px solid {_C['border']};
        border-radius: 7px;
        padding: 8px 12px;
        font-size: 13px;
    }}
    QLineEdit:focus, QComboBox:focus {{
        border-color: {_C['accent']};
    }}
    QComboBox::drop-down {{
        border: none;
    }}
    QComboBox::down-arrow {{
        image: none;
        width: 0; height: 0;
    }}
"""
_STYLE_PRIMARY_BTN = f"""
    QPushButton {{
        color: #FFFFFF;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {_C['accent']}, stop:1 {_C['accent_glow']});
        border: none;
        border-radius: 7px;
        font-size: 12px;
        font-weight: 600;
        padding: 8px 18px;
    }}
    QPushButton:hover {{ background: {_C['accent_light']}; }}
    QPushButton:disabled {{ background: {_C['bg_hover']}; color: {_C['text_tertiary']}; }}
"""
_STYLE_SECONDARY_BTN = f"""
    QPushButton {{
        color: {_C['text_secondary']};
        background: {_C['bg_card']};
        border: 1px solid {_C['border']};
        border-radius: 7px;
        font-size: 12px;
        padding: 8px 18px;
    }}
    QPushButton:hover {{
        color: {_C['text_primary']};
        background: {_C['bg_hover']};
    }}
"""
_STYLE_DANGER_BTN = f"""
    QPushButton {{
        color: {_C['offline']};
        background: transparent;
        border: 1px solid {_C['offline']};
        border-radius: 7px;
        font-size: 12px;
        padding: 8px 18px;
    }}
    QPushButton:hover {{
        background: #2D1217;
        color: #FCA5A5;
    }}
"""
_STYLE_CARD = f"""
    QWidget#settings_card {{
        background-color: {_C['bg_card']};
        border: 1px solid {_C['border']};
        border-radius: 10px;
    }}
"""
_STYLE_LEVEL_CARD = f"""
    QWidget#level_card {{
        background-color: {_C['bg_hover']};
        border: 1px solid {_C['border']};
        border-radius: 8px;
    }}
    QWidget#level_card[selected="true"] {{
        border-color: {_C['accent']};
        background-color: {_C['accent_muted']};
    }}
"""


# ---------------------------------------------------------------------------
# Account Avatar (larger, for settings)
# ---------------------------------------------------------------------------

class _SettingsAvatar(QWidget):
    _SIZE = 56

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(self._SIZE, self._SIZE)
        self._initial = "?"

    def set_email(self, email: str | None) -> None:
        self._initial = (email or "?")[0].upper()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        grad = QLinearGradient(0.0, 0.0, float(self._SIZE), float(self._SIZE))
        grad.setColorAt(0, QColor("#6366F1"))
        grad.setColorAt(1, QColor("#2563EB"))
        path = QPainterPath()
        path.addEllipse(0, 0, self._SIZE, self._SIZE)
        p.fillPath(path, grad)
        p.setPen(QColor("#FFFFFF"))
        f = p.font()
        f.setPointSize(20)
        f.setBold(True)
        p.setFont(f)
        p.drawText(0, 0, self._SIZE, self._SIZE, Qt.AlignmentFlag.AlignCenter, self._initial)


# ---------------------------------------------------------------------------
# Tab Content Pages
# ---------------------------------------------------------------------------

def _card_widget(parent: QWidget | None = None) -> QWidget:
    w = QWidget(parent)
    w.setObjectName("settings_card")
    w.setStyleSheet(_STYLE_CARD)
    return w


class _AuthWorker(QThread):
    finished_auth = pyqtSignal(str, str)  # token, email
    failed_auth = pyqtSignal(str)         # error message

    def __init__(self, provider: str, email: str, parent=None):
        super().__init__(parent)
        self.provider = provider
        self.email = email

    def run(self):
        try:
            token = gmail_access_token() if self.provider == "gmail" else yahoo_access_token()
            self.finished_auth.emit(token, self.email)
        except Exception as exc:
            self.failed_auth.emit(str(exc))


class _AccountTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._auth_thread: _AuthWorker | None = None
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        # ── Account card ──────────────────────────────────────
        card = _card_widget()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 20, 24, 20)
        cl.setSpacing(16)

        # Avatar + account info row
        top_row = QHBoxLayout()
        top_row.setSpacing(16)
        self._avatar = _SettingsAvatar()
        top_row.addWidget(self._avatar)

        info_col = QVBoxLayout()
        info_col.setSpacing(4)
        self._email_display = QLabel("Not signed in")
        self._email_display.setStyleSheet(_STYLE_VALUE_LABEL)
        self._provider_display = QLabel("")
        self._provider_display.setStyleSheet(_STYLE_HINT)
        info_col.addWidget(self._email_display)
        info_col.addWidget(self._provider_display)
        top_row.addLayout(info_col, stretch=1)
        cl.addLayout(top_row)

        # Divider
        div = QWidget()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background: {_C['border']};")
        cl.addWidget(div)

        # Input fields
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        email_lbl = QLabel("Email Address")
        email_lbl.setStyleSheet(_STYLE_LABEL)
        self._email_input = QLineEdit()
        self._email_input.setPlaceholderText("you@gmail.com")
        self._email_input.setStyleSheet(_STYLE_INPUT)

        provider_lbl = QLabel("Provider")
        provider_lbl.setStyleSheet(_STYLE_LABEL)
        self._provider_combo = QComboBox()
        self._provider_combo.addItems(["gmail", "yahoo"])
        self._provider_combo.setStyleSheet(_STYLE_INPUT)

        grid.addWidget(email_lbl, 0, 0)
        grid.addWidget(self._email_input, 0, 1)
        grid.addWidget(provider_lbl, 1, 0)
        grid.addWidget(self._provider_combo, 1, 1)
        cl.addLayout(grid)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._connect_btn = QPushButton("Connect Account")
        self._connect_btn.setStyleSheet(_STYLE_PRIMARY_BTN)
        self._connect_btn.clicked.connect(self._connect_account)

        self._reauth_btn = QPushButton("Re-authenticate")
        self._reauth_btn.setStyleSheet(_STYLE_SECONDARY_BTN)
        self._reauth_btn.clicked.connect(self._reauth_account)

        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setStyleSheet(_STYLE_DANGER_BTN)
        self._disconnect_btn.clicked.connect(self._disconnect_account)

        btn_row.addWidget(self._connect_btn)
        btn_row.addWidget(self._reauth_btn)
        btn_row.addWidget(self._disconnect_btn)
        btn_row.addStretch()
        cl.addLayout(btn_row)

        self._account_status = QLabel("")
        self._account_status.setStyleSheet(_STYLE_HINT)
        self._account_status.setWordWrap(True)
        cl.addWidget(self._account_status)

        outer.addWidget(card)
        outer.addStretch()

    # --- State ---

    def hydrate(self) -> None:
        email = session.active_account
        self._avatar.set_email(email)
        self._email_display.setText(email or "Not signed in")
        self._provider_display.setText(f"Provider: {session.provider}" if session.provider else "")
        if email:
            self._email_input.setText(email)
        if session.provider:
            idx = self._provider_combo.findText(session.provider)
            if idx >= 0:
                self._provider_combo.setCurrentIndex(idx)
        self._refresh_status()

    def _refresh_status(self) -> None:
        if session.active_account:
            self._account_status.setText(f"✓  Connected as {session.active_account}")
            self._account_status.setStyleSheet(f"color: {_C['online']}; font-size: 11px;")
        else:
            self._account_status.setText("No account connected.")
            self._account_status.setStyleSheet(_STYLE_HINT)

    # --- Actions ---

    def _connect_account(self) -> None:
        email = self._email_input.text().strip()
        provider = self._provider_combo.currentText().strip()
        if not email or "@" not in email:
            self._warn("Invalid email", "Please enter a valid email address.")
            return

        domain = email.split("@", 1)[1].lower()
        if provider == "gmail" and domain not in {"gmail.com", "googlemail.com"}:
            self._warn("Provider mismatch", "Use a Gmail address with Gmail provider.")
            return
        if provider == "yahoo" and "yahoo" not in domain and domain not in {"ymail.com", "rocketmail.com"}:
            self._warn("Provider mismatch", "Use a Yahoo address with Yahoo provider.")
            return

        self._start_auth(provider, email, is_reauth=False)

    def _start_auth(self, provider: str, email: str, is_reauth: bool) -> None:
        if self._auth_thread and self._auth_thread.isRunning():
            return
        self._connect_btn.setEnabled(False)
        self._connect_btn.setText("⏳ Waiting for browser...")
        if is_reauth:
            self._reauth_btn.setEnabled(False)
            self._reauth_btn.setText("⏳ Waiting...")

        self._auth_thread = _AuthWorker(provider, email, self)
        self._auth_thread.finished_auth.connect(lambda t, e: self._on_auth_success(t, e, provider, is_reauth))
        self._auth_thread.failed_auth.connect(lambda msg: self._on_auth_error(msg, is_reauth))
        self._auth_thread.start()

    def _on_auth_success(self, token: str, email: str, provider: str, is_reauth: bool) -> None:
        self._reset_buttons()
        try:
            session.active_account = email
            session.provider = provider
            session.oauth_token = {"access_token": token}
            
            # Note: kme_client.register_sae makes a synchronous HTTP request. 
            # In a fully non-blocking app this would also be threaded, but it responds in <50ms.
            if not is_reauth:
                session.kme_sae_id = kme_client.register_sae(email)
                session.kme_connected = True
            
            self.hydrate()
            if is_reauth:
                QMessageBox.information(self, "Re-authenticated",
                    f"Fresh token obtained for {email}.\n"
                    "Go to Inbox to see your messages.")
            else:
                QMessageBox.information(self, "Connected",
                    "Account connected successfully. You can now send and receive messages.")
        except KMEConnectionError as exc:
            self.hydrate()
            self._warn("Quantum Network unavailable",
                f"Account authenticated, but SAE registration failed:\n{exc}")

    def _on_auth_error(self, message: str, is_reauth: bool) -> None:
        self._reset_buttons()
        self._warn("Authentication failed", message)

    def _reset_buttons(self) -> None:
        self._connect_btn.setEnabled(True)
        self._connect_btn.setText("Connect Account")
        if hasattr(self, '_reauth_btn'):
            self._reauth_btn.setEnabled(True)
            self._reauth_btn.setText("Re-authenticate")

    def _disconnect_account(self) -> None:
        provider = session.provider
        try:
            if provider == "gmail":
                revoke_gmail_token()
            elif provider == "yahoo":
                revoke_yahoo_token()
        except (GmailAuthError, YahooAuthError) as exc:
            self._warn("Disconnect failed", str(exc))
            return
        session.active_account = None
        session.provider = None
        session.oauth_token = None
        session.kme_sae_id = None
        self.hydrate()
        QMessageBox.information(self, "Disconnected", "Account disconnected.")

    def _reauth_account(self) -> None:
        provider = session.provider or self._provider_combo.currentText().strip()
        email    = session.active_account or self._email_input.text().strip()
        if not email:
            self._warn("No account", "Connect an account first, then use Re-authenticate.")
            return
        try:
            import os
            from core.config import GMAIL_TOKEN_PATH
            if provider == "gmail" and os.path.exists(GMAIL_TOKEN_PATH):
                os.remove(GMAIL_TOKEN_PATH)
            elif provider == "yahoo":
                yahoo_token_path = "secrets/yahoo_token.json"
                if os.path.exists(yahoo_token_path):
                    os.remove(yahoo_token_path)
        except Exception:
            pass  # File un-removable, will be overwritten by flow
        
        self._start_auth(provider, email, is_reauth=True)

    def _warn(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)


class _SecurityTab(QWidget):

    _LEVEL_INFO = [
        (TQR_LEVEL_OTP,   "🔒", "Maximum Security",
         "One-Time Pad using quantum-delivered key.\nStrongest possible — requires active Quantum Network.",
         "#D1FAE5", "#064E3B"),
        (TQR_LEVEL_AES,   "🛡️", "High Security",
         "AES-256-GCM seeded with quantum-delivered key.\nStrong and fast — requires Quantum Network.",
         "#DBEAFE", "#1E3A5F"),
        (TQR_LEVEL_MLKEM, "⚛️", "Quantum-Safe",
         "ML-KEM post-quantum encryption.\nWorks without Quantum Network — future-proof.",
         "#EDE9FE", "#2E1065"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._level_cards: dict[int, QWidget] = {}
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        section_label = QLabel("Default Encryption Level")
        section_label.setStyleSheet(_STYLE_VALUE_LABEL)
        outer.addWidget(section_label)

        hint = QLabel("Choose the default security level for new messages. You can change it per-message in Compose.")
        hint.setStyleSheet(_STYLE_HINT)
        hint.setWordWrap(True)
        outer.addWidget(hint)
        outer.addSpacing(4)

        for level, icon, name, desc, fg, bg in self._LEVEL_INFO:
            card = QWidget()
            card.setObjectName("level_card")
            card.setStyleSheet(_STYLE_LEVEL_CARD)
            card.setFixedHeight(90)
            card.setCursor(Qt.CursorShape.PointingHandCursor)

            cl = QHBoxLayout(card)
            cl.setContentsMargins(18, 12, 18, 12)
            cl.setSpacing(14)

            icon_lbl = QLabel(icon)
            icon_lbl.setStyleSheet(f"font-size: 24px;")
            icon_lbl.setFixedWidth(32)
            cl.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

            text_col = QVBoxLayout()
            text_col.setSpacing(4)
            name_lbl = QLabel(name)
            name_lbl.setStyleSheet(
                f"color: {_C['text_primary']}; font-size: 13px; font-weight: 600;"
            )
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(_STYLE_HINT)
            desc_lbl.setWordWrap(True)
            text_col.addWidget(name_lbl)
            text_col.addWidget(desc_lbl)
            cl.addLayout(text_col, stretch=1)

            # Badge
            badge_lbl = QLabel(f"<span style='color:{fg}; background:{bg}; "
                               f"border-radius: 4px; padding: 2px 8px; font-size: 11px; "
                               f"font-weight: 600;'>Level {level}</span>")
            badge_lbl.setTextFormat(Qt.TextFormat.RichText)
            cl.addWidget(badge_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

            lv = level  # capture
            card.mousePressEvent = lambda e, lv=lv: self._select_level(lv)

            self._level_cards[level] = card
            outer.addWidget(card)

        outer.addStretch()

    def hydrate(self) -> None:
        self._select_level(session.tqr_level, emit=False)

    def _select_level(self, level: int, emit: bool = True) -> None:
        session.tqr_level = level
        for lv, card in self._level_cards.items():
            card.setProperty("selected", "true" if lv == level else "false")
            card.style().unpolish(card)
            card.style().polish(card)


class _NetworkTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        card = _card_widget()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 20, 24, 20)
        cl.setSpacing(14)

        # KME status indicator row
        status_row = QHBoxLayout()
        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet(
            f"color: {_C['online']}; font-size: 18px;"
        )
        self._status_text = QLabel("Checking…")
        self._status_text.setStyleSheet(_STYLE_VALUE_LABEL)
        status_row.addWidget(self._status_dot)
        status_row.addWidget(self._status_text)
        status_row.addStretch()
        cl.addLayout(status_row)

        desc = QLabel(
            "The Quantum Key Node (KME) provides quantum-distributed encryption keys for "
            "Level 1 and Level 2 security. In v1, a virtual node runs locally."
        )
        desc.setStyleSheet(_STYLE_HINT)
        desc.setWordWrap(True)
        cl.addWidget(desc)

        div = QWidget()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background: {_C['border']};")
        cl.addWidget(div)

        # Endpoint input
        endpoint_lbl = QLabel("KME Base URL")
        endpoint_lbl.setStyleSheet(_STYLE_LABEL)
        cl.addWidget(endpoint_lbl)

        self._kme_input = QLineEdit()
        self._kme_input.setStyleSheet(_STYLE_INPUT)
        self._kme_input.setPlaceholderText("http://127.0.0.1:5000")
        cl.addWidget(self._kme_input)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        save_btn = QPushButton("Save Endpoint")
        save_btn.setStyleSheet(_STYLE_SECONDARY_BTN)
        save_btn.clicked.connect(self._save_endpoint)
        test_btn = QPushButton("Test Connection")
        test_btn.setStyleSheet(_STYLE_PRIMARY_BTN)
        test_btn.clicked.connect(self._test_connection)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(test_btn)
        btn_row.addStretch()
        cl.addLayout(btn_row)

        self._kme_detail = QLabel("")
        self._kme_detail.setStyleSheet(_STYLE_HINT)
        self._kme_detail.setWordWrap(True)
        cl.addWidget(self._kme_detail)

        outer.addWidget(card)
        outer.addStretch()

    def hydrate(self) -> None:
        self._kme_input.setText(kme_client.base_url or KME_BASE_URL)
        self._update_status_display(session.kme_connected)

    def _update_status_display(self, online: bool) -> None:
        if online:
            self._status_dot.setStyleSheet(f"color: {_C['online']}; font-size: 18px;")
            self._status_text.setText("Quantum Network: Connected")
        else:
            self._status_dot.setStyleSheet(f"color: {_C['offline']}; font-size: 18px;")
            self._status_text.setText("Quantum Network: Offline")

    def _save_endpoint(self) -> None:
        value = self._kme_input.text().strip()
        if not value.startswith("http://") and not value.startswith("https://"):
            QMessageBox.warning(self, "Invalid endpoint",
                "KME endpoint must start with http:// or https://")
            return
        local_hosts = ("127.0.0.1", "localhost")
        if not any(h in value for h in local_hosts):
            QMessageBox.warning(self, "Endpoint blocked",
                "For v1 safety, only local KME endpoints are allowed (localhost or 127.0.0.1).")
            return
        kme_client.base_url = value
        self._kme_detail.setText("Endpoint saved. Test connection to verify.")

    def _test_connection(self) -> None:
        online = kme_client.is_online()
        session.kme_connected = online
        self._update_status_display(online)
        self._kme_detail.setText(
            "Connection successful — Quantum Network is live."
            if online else
            "Connection failed — check that the virtual node is running."
        )


# ---------------------------------------------------------------------------
# Settings Window
# ---------------------------------------------------------------------------

class SettingsWindow(QWidget):
    """Tab-based settings: Account | Security | Network."""

    _TAB_NAMES = ["Account", "Security", "Network"]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tab_buttons: list[QPushButton] = []
        self._build_ui()
        self._hydrate_state()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Page header
        header = QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet(
            f"background-color: {_C['bg_sidebar']}; border-bottom: 1px solid {_C['border']};"
        )
        hl = QHBoxLayout(header)
        hl.setContentsMargins(28, 0, 28, 0)
        title = QLabel("Settings")
        title.setStyleSheet(
            f"color: {_C['text_primary']}; font-size: 18px; font-weight: 700;"
        )
        hl.addWidget(title)
        hl.addStretch()
        outer.addWidget(header)

        # Tab bar
        tab_bar = QWidget()
        tab_bar.setFixedHeight(44)
        tab_bar.setStyleSheet(
            f"background-color: {_C['bg_sidebar']}; border-bottom: 1px solid {_C['border']};"
        )
        tb_layout = QHBoxLayout(tab_bar)
        tb_layout.setContentsMargins(16, 0, 16, 0)
        tb_layout.setSpacing(0)

        for i, name in enumerate(self._TAB_NAMES):
            btn = QPushButton(name)
            btn.setStyleSheet(_STYLE_TAB_BTN)
            btn.setCheckable(False)
            btn.clicked.connect(lambda checked, idx=i: self._switch_tab(idx))
            self._tab_buttons.append(btn)
            tb_layout.addWidget(btn)

        tb_layout.addStretch()
        outer.addWidget(tab_bar)

        # Scrollable content area with stacked pages
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {_C['bg_base']}; border: none; }}"
        )

        content_host = QWidget()
        content_host.setStyleSheet(f"background: {_C['bg_base']};")
        ch_layout = QVBoxLayout(content_host)
        ch_layout.setContentsMargins(0, 0, 0, 0)
        ch_layout.setSpacing(0)

        self._stack = QStackedWidget()

        self._account_tab  = _AccountTab()
        self._security_tab = _SecurityTab()
        self._network_tab  = _NetworkTab()

        # Wrap each tab in a padded container
        for tab in (self._account_tab, self._security_tab, self._network_tab):
            wrapper = QWidget()
            wrapper.setStyleSheet(f"background: {_C['bg_base']};")
            wl = QVBoxLayout(wrapper)
            wl.setContentsMargins(32, 24, 32, 24)
            wl.setSpacing(0)
            wl.addWidget(tab)
            self._stack.addWidget(wrapper)

        ch_layout.addWidget(self._stack)
        scroll.setWidget(content_host)
        outer.addWidget(scroll, stretch=1)

        self._switch_tab(0)

    def _switch_tab(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._tab_buttons):
            btn.setProperty("active", "true" if i == index else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _hydrate_state(self) -> None:
        self._account_tab.hydrate()
        self._security_tab.hydrate()
        self._network_tab.hydrate()
