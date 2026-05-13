# ui/inbox_view.py — Inbox list and message reader view.
# Single responsibility: fetch and display the inbox message list, and render
# the decrypted content of a selected message in the reading pane.
# All IMAP and decryption work runs on background threads.
# Does not perform encryption, send mail, or modify session state.
# Do not import from portal/ or certificates/ here.

from dataclasses import dataclass

from PyQt6.QtCore import Qt, QThread, QObject, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QFrame,
    QLineEdit,
)

from core.session import session


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_FETCH_COUNT = 50


# ---------------------------------------------------------------------------
# Design tokens (mirrors main_window.py)
# ---------------------------------------------------------------------------

_C = {
    "bg_base":       "#0D1117",
    "bg_sidebar":    "#161B22",
    "bg_card":       "#1C2231",
    "bg_hover":      "#21293A",
    "accent":        "#6366F1",
    "accent_light":  "#818CF8",
    "accent_muted":  "#1E2238",
    "text_primary":  "#E6EDF3",
    "text_secondary":"#8B949E",
    "text_tertiary": "#484F58",
    "border":        "#21262D",
    "online":        "#22C55E",
    "offline":       "#EF4444",
    "lvl1_fg":    "#D1FAE5",  "lvl1_bg":  "#064E3B",
    "lvl2_fg":    "#DBEAFE",  "lvl2_bg":  "#1E3A5F",
    "lvl3_fg":    "#EDE9FE",  "lvl3_bg":  "#2E1065",
}


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

_STYLE_SEARCH_BAR = f"""
    QLineEdit {{
        background-color: {_C['bg_card']};
        border: 1px solid {_C['border']};
        border-radius: 8px;
        color: {_C['text_primary']};
        font-size: 12px;
        padding: 7px 14px 7px 36px;
    }}
    QLineEdit:focus {{
        border-color: {_C['accent']};
    }}
"""

_STYLE_REFRESH_BTN = f"""
    QPushButton {{
        font-size: 12px;
        font-weight: 600;
        color: {_C['accent_light']};
        background: {_C['accent_muted']};
        border: 1px solid {_C['accent']};
        border-radius: 7px;
        padding: 6px 16px;
    }}
    QPushButton:hover {{
        background: {_C['accent']};
        color: #FFFFFF;
    }}
    QPushButton:disabled {{
        color: {_C['text_tertiary']};
        border-color: {_C['border']};
        background: transparent;
    }}
"""

_STYLE_MESSAGE_LIST = f"""
    QListWidget {{
        background-color: {_C['bg_sidebar']};
        border: none;
        outline: none;
        font-size: 13px;
    }}
    QListWidget::item {{
        padding: 0px;
        border-bottom: 1px solid {_C['border']};
        color: {_C['text_primary']};
        background: transparent;
    }}
    QListWidget::item:selected {{
        background-color: {_C['accent_muted']};
        border-left: 3px solid {_C['accent']};
    }}
    QListWidget::item:hover:!selected {{
        background-color: {_C['bg_hover']};
    }}
"""

_STYLE_READER_PANEL = f"""
    QWidget#reader_panel {{
        background-color: {_C['bg_base']};
    }}
"""
_STYLE_READER_META  = f"color: {_C['text_secondary']}; font-size: 11px;"
_STYLE_READER_FROM  = f"color: {_C['text_secondary']}; font-size: 12px;"
_STYLE_READER_SUB   = f"color: {_C['text_primary']}; font-size: 17px; font-weight: 700;"
_STYLE_READER_BODY  = f"color: {_C['text_primary']}; font-size: 13px; line-height: 1.6;"
_STYLE_NOTICE_LABEL = f"color: {_C['text_secondary']}; font-size: 13px; font-style: italic;"
_STYLE_EMPTY_HINT   = f"color: {_C['text_tertiary']}; font-size: 13px;"

_STYLE_SECURITY_BADGE = """
    QLabel {{
        font-size: 11px;
        font-weight: 600;
        color: {fg};
        background-color: {bg};
        border-radius: 4px;
        padding: 3px 8px;
    }}
"""

_STYLE_REPLY_BTN = f"""
    QPushButton {{
        color: {_C['accent_light']};
        background: {_C['accent_muted']};
        border: 1px solid {_C['accent']};
        border-radius: 7px;
        font-size: 12px;
        font-weight: 600;
        padding: 7px 18px;
    }}
    QPushButton:hover {{
        background: {_C['accent']};
        color: #FFFFFF;
    }}
"""

_STYLE_HEADER_AREA = f"""
    QWidget#header_area {{
        background-color: {_C['bg_sidebar']};
        border-bottom: 1px solid {_C['border']};
    }}
"""

_STYLE_LIST_PANEL = f"""
    QWidget#list_panel {{
        background-color: {_C['bg_sidebar']};
    }}
"""


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class _DisplayMessage:
    uid:            str
    subject:        str
    sender:         str
    date:           str
    is_qumail:      bool
    decrypted_body: str | None
    tqr_level:      int | None
    error_notice:   str | None


# ---------------------------------------------------------------------------
# Avatar circle (in message list items)
# ---------------------------------------------------------------------------

class _InitialAvatar(QWidget):
    """Small circle with sender initial — painted, no pixmap required."""

    _COLORS = [
        ("#6366F1", "#1E2238"), ("#22C55E", "#052E16"), ("#F59E0B", "#2D1B00"),
        ("#3B82F6", "#1E3A5F"), ("#EC4899", "#500724"), ("#8B5CF6", "#2E1065"),
    ]
    _SIZE = 38

    def __init__(self, initial: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._initial = initial.upper() if initial else "?"
        idx = (ord(initial.upper()) if initial else 0) % len(self._COLORS)
        self._fg, self._bg = self._COLORS[idx]
        self.setFixedSize(self._SIZE, self._SIZE)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addEllipse(1, 1, self._SIZE - 2, self._SIZE - 2)
        p.fillPath(path, QColor(self._bg))

        pen_color = QColor(self._fg)
        pen_color.setAlpha(180)
        p.setPen(pen_color)
        p.drawPath(path)

        p.setPen(QColor(self._fg))
        f = p.font()
        f.setPointSize(14)
        f.setBold(True)
        p.setFont(f)
        p.drawText(0, 0, self._SIZE, self._SIZE, Qt.AlignmentFlag.AlignCenter, self._initial)


# ---------------------------------------------------------------------------
# Message list item widget
# ---------------------------------------------------------------------------

class _MessageItemWidget(QWidget):
    """Custom widget rendered inside each QListWidgetItem for rich display."""

    def __init__(self, sender: str, subject: str, date: str,
                 is_qumail: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(72)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        # Avatar
        initial = (sender or "?")[0]
        avatar = _InitialAvatar(initial)
        layout.addWidget(avatar, 0, Qt.AlignmentFlag.AlignVCenter)

        # Text block
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.setContentsMargins(0, 0, 0, 0)

        sender_lbl = QLabel(sender or "Unknown")
        sender_lbl.setStyleSheet(
            f"color: {_C['text_primary']}; font-size: 13px; font-weight: 600;"
        )
        sender_lbl.setMaximumWidth(200)

        subj_lbl = QLabel(subject or "(no subject)")
        subj_lbl.setStyleSheet(
            f"color: {_C['text_secondary']}; font-size: 12px;"
        )
        subj_lbl.setMaximumWidth(200)

        text_col.addWidget(sender_lbl)
        text_col.addWidget(subj_lbl)
        layout.addLayout(text_col, stretch=1)

        # Right column: date + badge
        right_col = QVBoxLayout()
        right_col.setSpacing(4)
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        date_lbl = QLabel(date or "")
        date_lbl.setStyleSheet(
            f"color: {_C['text_tertiary']}; font-size: 10px;"
        )
        date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(date_lbl)

        if is_qumail:
            badge = QLabel("🔐")
            badge.setStyleSheet(f"color: {_C['accent_light']}; font-size: 11px;")
            badge.setAlignment(Qt.AlignmentFlag.AlignRight)
            right_col.addWidget(badge)

        layout.addLayout(right_col)


# ---------------------------------------------------------------------------
# Background Workers (unchanged logic, new module organisation)
# ---------------------------------------------------------------------------

class _FetchInboxWorker(QObject):
    finished = pyqtSignal(object)
    failed   = pyqtSignal(str)

    def __init__(self, account_email: str) -> None:
        super().__init__()
        self._account = account_email

    def run(self) -> None:
        try:
            from transport.imap_receiver import fetch_inbox
            messages = fetch_inbox(self._account, _MAX_FETCH_COUNT)
            self.finished.emit(messages)
        except Exception as exc:
            self.failed.emit(f"Could not load your inbox: {exc}")


class _FetchMessageWorker(QObject):
    finished = pyqtSignal(object)
    failed   = pyqtSignal(str)

    def __init__(self, account_email: str, uid: str, subject: str,
                 sender: str, date: str) -> None:
        super().__init__()
        self._account = account_email
        self._uid     = uid
        self._subject = subject
        self._sender  = sender
        self._date    = date

    def run(self) -> None:
        try:
            result = self._fetch_and_decode()
            self.finished.emit(result)
        except Exception as exc:
            # Distinguish between transport failures (server unreachable, IMAP
            # error — we have no message metadata to show inline) and unexpected
            # errors (programming fault — show inline rather than a dialog).
            exc_name = type(exc).__name__
            is_transport_failure = any(
                marker in exc_name
                for marker in ("IMAP", "Transport", "Connection", "Socket", "Timeout")
            ) or "fetch" in str(exc).lower()

            if is_transport_failure:
                self.failed.emit(
                    f"Could not fetch this message from the server. "
                    f"Check your connection and try again."
                )
            else:
                self.finished.emit(_DisplayMessage(
                    uid=self._uid, subject=self._subject, sender=self._sender,
                    date=self._date, is_qumail=True, decrypted_body=None,
                    tqr_level=None,
                    error_notice=(
                        "This message could not be loaded due to an unexpected error. "
                        f"({type(exc).__name__})"
                    ),
                ))

    def _fetch_and_decode(self) -> _DisplayMessage:
        from transport.imap_receiver import fetch_message
        from mime.decapsulator import decapsulate, NotQuMailMessageError, DecapsulationError

        inbox_msg = fetch_message(self._account, self._uid)

        try:
            ciphertext, metadata = decapsulate(inbox_msg.message)
        except NotQuMailMessageError:
            return _DisplayMessage(
                uid=self._uid, subject=self._subject, sender=self._sender,
                date=self._date, is_qumail=False, decrypted_body=None,
                tqr_level=None, error_notice=None,
            )
        except DecapsulationError as exc:
            # Message is a QuMail email but its MIME structure is malformed or
            # from a legacy format that could not be parsed. Show specific notice
            # inline rather than a generic error dialog.
            return _DisplayMessage(
                uid=self._uid, subject=self._subject, sender=self._sender,
                date=self._date, is_qumail=True, decrypted_body=None,
                tqr_level=None,
                error_notice=(
                    "This message has an unreadable structure. It may have been sent "
                    "by an older version of QuMail or was corrupted in transit."
                ),
            )

        tqr_level: int | None = metadata.get("tqr_level")
        decrypted_body: str | None = None
        error_notice: str | None   = None

        try:
            from crypto.tqr import decrypt
            key_id: str | None = metadata.get("key_id")
            private_key = _load_send_key(key_id) if key_id else None
            plaintext_bytes = decrypt(ciphertext, metadata, private_key=private_key)
            decrypted_body  = plaintext_bytes.decode("utf-8", errors="replace")
        except Exception as exc:
            error_notice = _decrypt_error_notice(exc, tqr_level)

        return _DisplayMessage(
            uid=self._uid, subject=self._subject, sender=self._sender,
            date=self._date, is_qumail=True, decrypted_body=decrypted_body,
            tqr_level=tqr_level, error_notice=error_notice,
        )


def _load_send_key(cert_id: str) -> bytes | None:
    import os
    try:
        from cryptography.fernet import Fernet
        from core.config import SEND_KEYS_DIR
        _MASTER_KEY_PATH = "secrets/oauth_master.key"
        key_path = os.path.join(SEND_KEYS_DIR, f"{cert_id}.key")
        if not os.path.exists(key_path):
            return None
        with open(_MASTER_KEY_PATH, "rb") as f:
            fernet = Fernet(f.read())
        with open(key_path, "rb") as f:
            encrypted = f.read()
        return fernet.decrypt(encrypted)
    except Exception:
        return None


def _decrypt_error_notice(exc: Exception, tqr_level: int | None) -> str:
    from core.config import TQR_LEVEL_MLKEM
    if tqr_level == TQR_LEVEL_MLKEM:
        exc_name = type(exc).__name__
        if exc_name == "TQRMissingPrivateKeyError":
            return (
                "This message was encrypted with quantum-safe encryption (ML-KEM). "
                "The decryption key for this message was not found on this device."
            )
        return "This message was encrypted with quantum-safe encryption. Decryption failed."
    if not session.kme_connected:
        return (
            "This message requires a Quantum Network connection to decrypt, "
            "but the network is currently offline. Reconnect and try again."
        )
    return "This message could not be decrypted. It may have been corrupted or sent with a different key."


# ---------------------------------------------------------------------------
# Inbox View
# ---------------------------------------------------------------------------

class InboxView(QWidget):
    """
    Three-pane inbox: header toolbar → list panel ↔ reading pane.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fetch_thread:   QThread | None = None
        self._message_thread: QThread | None = None
        self._build_ui()
        
        session.account_changed.connect(self._on_account_changed)
        
        if session.active_account:
            self._load_inbox()
            
    def _on_account_changed(self, email: str) -> None:
        self._message_list.clear()
        self._count_label.setText("")
        self._reader_loading.setVisible(False)
        self._reader_content.setVisible(False)
        self._reader_placeholder.setVisible(True)
        if email:
            self._load_inbox()
        else:
            self._list_status.setText("Sign in to an account in Settings to view your inbox.")

    # --- UI Construction ---

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_header())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {_C['border']}; }}")

        splitter.addWidget(self._build_list_panel())
        splitter.addWidget(self._build_reader_panel())
        splitter.setSizes([340, 900])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        outer.addWidget(splitter, stretch=1)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("header_area")
        header.setStyleSheet(_STYLE_HEADER_AREA)
        header.setFixedHeight(56)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(12)

        # Title
        title = QLabel("Inbox")
        title.setStyleSheet(
            f"color: {_C['text_primary']}; font-size: 18px; font-weight: 700;"
        )
        layout.addWidget(title)

        # Search bar — disabled in v1, functional search coming in v2
        search = QLineEdit()
        search.setPlaceholderText("🔍  Search coming in v2")
        search.setStyleSheet(_STYLE_SEARCH_BAR)
        search.setFixedWidth(260)
        search.setEnabled(False)
        layout.addWidget(search)

        layout.addStretch()

        # Message count label
        self._count_label = QLabel("")
        self._count_label.setStyleSheet(
            f"color: {_C['text_tertiary']}; font-size: 11px;"
        )
        layout.addWidget(self._count_label)

        # Refresh button
        self._refresh_btn = QPushButton("↺  Refresh")
        self._refresh_btn.setStyleSheet(_STYLE_REFRESH_BTN)
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.setFixedHeight(32)
        self._refresh_btn.clicked.connect(self._load_inbox)
        layout.addWidget(self._refresh_btn)

        return header

    def _build_list_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("list_panel")
        panel.setStyleSheet(_STYLE_LIST_PANEL)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._message_list = QListWidget()
        self._message_list.setStyleSheet(_STYLE_MESSAGE_LIST)
        self._message_list.setSpacing(0)
        self._message_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._message_list.currentItemChanged.connect(self._on_message_selected)
        layout.addWidget(self._message_list, stretch=1)

        # Loading / empty state
        self._list_status = QLabel("")
        self._list_status.setStyleSheet(_STYLE_EMPTY_HINT)
        self._list_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._list_status.setContentsMargins(12, 8, 12, 8)
        layout.addWidget(self._list_status)

        return panel

    def _build_reader_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("reader_panel")
        panel.setStyleSheet(_STYLE_READER_PANEL)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Empty placeholder
        self._reader_placeholder = self._build_empty_placeholder()
        layout.addWidget(self._reader_placeholder, alignment=Qt.AlignmentFlag.AlignCenter)

        # Actual content (hidden initially)
        self._reader_content = self._build_reader_content_area()
        self._reader_content.setVisible(False)
        layout.addWidget(self._reader_content, stretch=1)

        # Loading indicator
        self._reader_loading = self._build_loading_indicator()
        self._reader_loading.setVisible(False)
        layout.addWidget(self._reader_loading, alignment=Qt.AlignmentFlag.AlignCenter)

        return panel

    def _build_empty_placeholder(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.setSpacing(8)

        icon = QLabel("📭")
        icon.setStyleSheet("font-size: 48px;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(icon)

        hint = QLabel("Select a message to read it")
        hint.setStyleSheet(
            f"color: {_C['text_secondary']}; font-size: 14px; font-weight: 500;"
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(hint)

        sub = QLabel("Your messages are end-to-end encrypted")
        sub.setStyleSheet(
            f"color: {_C['text_tertiary']}; font-size: 12px;"
        )
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(sub)
        return w

    def _build_loading_indicator(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spin = QLabel("⏳  Decrypting message…")
        spin.setStyleSheet(
            f"color: {_C['accent_light']}; font-size: 13px;"
        )
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(spin)
        return w

    def _build_reader_content_area(self) -> QWidget:
        """Build the structured email reader pane."""
        outer = QWidget()
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Reader header ────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet(
            f"background-color: {_C['bg_sidebar']}; border-bottom: 1px solid {_C['border']};"
        )
        header.setFixedHeight(130)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(28, 16, 28, 16)
        header_layout.setSpacing(6)

        # Subject
        self._reader_subject = QLabel("")
        self._reader_subject.setStyleSheet(_STYLE_READER_SUB)
        self._reader_subject.setWordWrap(True)
        header_layout.addWidget(self._reader_subject)

        # Meta row: sender • date • badge • reply
        meta_row = QHBoxLayout()
        meta_row.setSpacing(10)

        # Sender chip
        self._sender_chip = QLabel("")
        self._sender_chip.setStyleSheet(
            f"color: {_C['text_primary']}; font-size: 12px; font-weight: 600;"
        )
        meta_row.addWidget(self._sender_chip)

        sep = QLabel("·")
        sep.setStyleSheet(f"color: {_C['text_tertiary']}; font-size: 12px;")
        meta_row.addWidget(sep)

        self._reader_date = QLabel("")
        self._reader_date.setStyleSheet(_STYLE_READER_META)
        meta_row.addWidget(self._reader_date)

        meta_row.addStretch()

        self._reader_badge = QLabel("")
        self._reader_badge.setVisible(False)
        meta_row.addWidget(self._reader_badge)

        header_layout.addLayout(meta_row)

        # Action row
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        reply_btn = QPushButton("↩  Reply")
        reply_btn.setStyleSheet(_STYLE_REPLY_BTN)
        reply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reply_btn.setFixedHeight(30)
        action_row.addWidget(reply_btn)
        action_row.addStretch()
        header_layout.addLayout(action_row)

        layout.addWidget(header)

        # ── Scrollable body ──────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {_C['bg_base']}; border: none; }}"
        )

        body_container = QWidget()
        body_container.setStyleSheet(f"background: {_C['bg_base']};")
        body_layout = QVBoxLayout(body_container)
        body_layout.setContentsMargins(28, 24, 28, 24)

        self._reader_body = QLabel("")
        self._reader_body.setStyleSheet(_STYLE_READER_BODY)
        self._reader_body.setWordWrap(True)
        self._reader_body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._reader_body.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        body_layout.addWidget(self._reader_body)
        body_layout.addStretch()
        scroll.setWidget(body_container)
        layout.addWidget(scroll, stretch=1)

        return outer

    # --- Inbox Loading ---

    def _load_inbox(self) -> None:
        account = session.active_account
        if not account:
            self._list_status.setText(
                "Sign in to an account in Settings to view your inbox."
            )
            return

        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("Loading…")
        self._message_list.clear()
        self._count_label.setText("")
        self._list_status.setText("Fetching messages…")

        self._inbox_worker = _FetchInboxWorker(account)
        self._fetch_thread = QThread()
        self._inbox_worker.moveToThread(self._fetch_thread)

        self._fetch_thread.started.connect(self._inbox_worker.run)
        self._inbox_worker.finished.connect(
            self._on_inbox_loaded, Qt.ConnectionType.QueuedConnection
        )
        self._inbox_worker.failed.connect(
            self._on_inbox_error, Qt.ConnectionType.QueuedConnection
        )
        self._inbox_worker.finished.connect(self._fetch_thread.quit)
        self._inbox_worker.failed.connect(self._fetch_thread.quit)
        self._fetch_thread.finished.connect(self._fetch_thread.deleteLater)
        self._fetch_thread.finished.connect(self._inbox_worker.deleteLater)

        self._fetch_thread.start()

    def _on_inbox_loaded(self, messages: list) -> None:
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("↺  Refresh")
        self._message_list.clear()

        if not messages:
            self._list_status.setText("Your inbox is empty.")
            self._count_label.setText("")
            return

        self._list_status.setText("")
        self._count_label.setText(f"{len(messages)} messages")

        for msg in messages:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, msg)
            item.setSizeHint(QSize(0, 72))

            widget = _MessageItemWidget(
                sender=msg.sender,
                subject=msg.subject,
                date=msg.date,
                is_qumail=True,   # We can check later on open; assume QuMail for badge hint
            )
            self._message_list.addItem(item)
            self._message_list.setItemWidget(item, widget)

    def _on_inbox_error(self, message: str) -> None:
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("↺  Refresh")
        self._list_status.setText("Could not load inbox.")
        QMessageBox.warning(self, "Inbox error", message)

    # --- Message Selection ---

    def _on_message_selected(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            return

        inbox_msg = current.data(Qt.ItemDataRole.UserRole)
        if inbox_msg is None:
            return

        account = session.active_account
        if not account:
            return

        self._reader_content.setVisible(False)
        self._reader_placeholder.setVisible(False)
        self._reader_loading.setVisible(True)

        self._msg_worker = _FetchMessageWorker(
            account_email=account,
            uid=inbox_msg.uid,
            subject=inbox_msg.subject,
            sender=inbox_msg.sender,
            date=inbox_msg.date,
        )
        self._message_thread = QThread()
        self._msg_worker.moveToThread(self._message_thread)

        self._message_thread.started.connect(self._msg_worker.run)
        self._msg_worker.finished.connect(
            self._on_message_loaded, Qt.ConnectionType.QueuedConnection
        )
        self._msg_worker.failed.connect(
            self._on_message_error, Qt.ConnectionType.QueuedConnection
        )
        self._msg_worker.finished.connect(self._message_thread.quit)
        self._msg_worker.failed.connect(self._message_thread.quit)
        self._message_thread.finished.connect(self._message_thread.deleteLater)
        self._message_thread.finished.connect(self._msg_worker.deleteLater)

        self._message_thread.start()

    def _on_message_loaded(self, display_msg: _DisplayMessage) -> None:
        self._reader_loading.setVisible(False)
        self._reader_placeholder.setVisible(False)
        self._reader_content.setVisible(True)

        self._reader_subject.setText(display_msg.subject)
        self._sender_chip.setText(f"From: {display_msg.sender}")
        self._reader_date.setText(display_msg.date)

        # Security badge
        if display_msg.is_qumail and display_msg.tqr_level is not None:
            badge_text, fg, bg = _badge_for_level(display_msg.tqr_level)
            self._reader_badge.setText(badge_text)
            self._reader_badge.setStyleSheet(
                _STYLE_SECURITY_BADGE.format(fg=fg, bg=bg)
            )
            self._reader_badge.setVisible(True)
        else:
            self._reader_badge.setVisible(False)

        # Body
        if not display_msg.is_qumail:
            self._reader_body.setStyleSheet(_STYLE_NOTICE_LABEL)
            self._reader_body.setText(
                "This message was not sent with QuMail and cannot be displayed here."
            )
        elif display_msg.error_notice:
            self._reader_body.setStyleSheet(_STYLE_NOTICE_LABEL)
            self._reader_body.setText(display_msg.error_notice)
        else:
            self._reader_body.setStyleSheet(_STYLE_READER_BODY)
            self._reader_body.setText(display_msg.decrypted_body or "")

    def _on_message_error(self, message: str) -> None:
        self._reader_loading.setVisible(False)
        self._reader_placeholder.setVisible(True)
        QMessageBox.warning(self, "Message error", message)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _badge_for_level(tqr_level: int) -> tuple[str, str, str]:
    from core.config import TQR_LEVEL_OTP, TQR_LEVEL_AES, TQR_LEVEL_MLKEM
    badges = {
        TQR_LEVEL_OTP:   ("🔒 Maximum Security", "#D1FAE5", "#064E3B"),
        TQR_LEVEL_AES:   ("🔒 High Security",    "#DBEAFE", "#1E3A5F"),
        TQR_LEVEL_MLKEM: ("🔒 Quantum-Safe",      "#EDE9FE", "#2E1065"),
    }
    return badges.get(tqr_level, (f"Level {tqr_level}", "#8B949E", "#21262D"))
