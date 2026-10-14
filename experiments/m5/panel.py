"""QuMail M5 — premium presentation frontend.

Smoke-test contract preserved:
  panel.to, panel.cc, panel.subject, panel.body,
  panel.status, panel.content, panel.archive,
  panel.start(...), panel.poll(), panel.select(index),
  panel.shared, panel.pending, panel.pool
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import time
from typing import Optional

from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QSize, pyqtProperty,
    QPoint, QRect,
)
from PyQt6.QtGui import (
    QColor, QFont, QFontMetrics, QIcon, QLinearGradient, QPainter,
    QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
    QComboBox, QGraphicsDropShadowEffect, QSpacerItem,
)

from .model import Draft, Budget, OpenedMessage


# ──────────────────────────────────────────────────────────────────────────────
# Design tokens
# ──────────────────────────────────────────────────────────────────────────────
_C = {
    "bg":            "#0B1220",
    "sidebar":       "#101B2B",
    "surface":       "#162337",
    "elevated":      "#1D3048",
    "border":        "#293B53",
    "accent":        "#756CF4",
    "accent_hover":  "#8B84F7",
    "accent_press":  "#5E57D1",
    "security":      "#40D6C4",
    "text":          "#F0F5FC",
    "text2":         "#9BADBF",
    "text_dim":      "#5A7090",
    "success":       "#3EC97A",
    "warning":       "#F5A623",
    "danger":        "#E05252",
    "unknown":       "#9BADBF",
    "draft":         "#5B8DD9",
    "prepared":      "#40D6C4",
}


# ──────────────────────────────────────────────────────────────────────────────
# Global application stylesheet
# ──────────────────────────────────────────────────────────────────────────────
APP_QSS = """
/* === Reset / Base === */
QWidget {
    background-color: #0B1220;
    color: #F0F5FC;
    font-family: "Segoe UI", "Arial", sans-serif;
    font-size: 13px;
    selection-background-color: #756CF4;
    selection-color: #F0F5FC;
}

/* === Input Fields === */
QLineEdit, QPlainTextEdit {
    background-color: #162337;
    border: 1px solid #293B53;
    border-radius: 6px;
    padding: 7px 10px;
    color: #F0F5FC;
    font-size: 13px;
}
QLineEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #756CF4;
    background-color: #1D3048;
}
QLineEdit:disabled, QPlainTextEdit:disabled {
    color: #5A7090;
    background-color: #101B2B;
    border-color: #1D3048;
}

/* === ComboBox === */
QComboBox {
    background-color: #162337;
    border: 1px solid #293B53;
    border-radius: 6px;
    padding: 7px 12px;
    color: #F0F5FC;
    min-width: 200px;
}
QComboBox:focus { border-color: #756CF4; }
QComboBox::drop-down {
    border: none;
    width: 24px;
    padding-right: 6px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #9BADBF;
    width: 0;
    height: 0;
}
QComboBox QAbstractItemView {
    background-color: #1D3048;
    border: 1px solid #293B53;
    border-radius: 6px;
    color: #F0F5FC;
    selection-background-color: #756CF4;
    padding: 4px;
}

/* === CheckBox === */
QCheckBox { color: #9BADBF; spacing: 8px; }
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #293B53;
    border-radius: 4px;
    background-color: #162337;
}
QCheckBox::indicator:checked {
    background-color: #756CF4;
    border-color: #756CF4;
}
QCheckBox::indicator:hover { border-color: #756CF4; }

/* === ScrollBar === */
QScrollBar:vertical {
    background: #101B2B;
    width: 8px;
    border-radius: 4px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #293B53;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #756CF4; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QScrollBar:horizontal {
    background: #101B2B;
    height: 8px;
    border-radius: 4px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #293B53;
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background: #756CF4; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* === Frame === */
QFrame[frameShape="4"], QFrame[frameShape="5"] {
    border: none;
    background-color: #293B53;
    max-height: 1px;
}

/* === ToolTip === */
QToolTip {
    background-color: #1D3048;
    border: 1px solid #293B53;
    color: #F0F5FC;
    padding: 5px 8px;
    border-radius: 5px;
}
"""


# ──────────────────────────────────────────────────────────────────────────────
# Small helpers
# ──────────────────────────────────────────────────────────────────────────────

def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet("background-color: #293B53; border: none; max-height: 1px;")
    return f


def _label(text: str, color: str = "#9BADBF", size: int = 12, bold: bool = False) -> QLabel:
    lbl = QLabel(text)
    style = f"color: {color}; font-size: {size}px;"
    if bold:
        style += " font-weight: 600;"
    lbl.setStyleSheet(style)
    return lbl


class _PrimaryButton(QPushButton):
    """Indigo primary action button."""
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply()

    def _apply(self):
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {_C['accent']};
                color: #F0F5FC;
                border: none;
                border-radius: 7px;
                padding: 0 18px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {_C['accent_hover']}; }}
            QPushButton:pressed {{ background-color: {_C['accent_press']}; }}
            QPushButton:disabled {{
                background-color: #1D3048;
                color: #5A7090;
            }}
        """)


class _SecondaryButton(QPushButton):
    """Outline secondary button."""
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {_C['text2']};
                border: 1px solid {_C['border']};
                border-radius: 7px;
                padding: 0 14px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {_C['elevated']};
                color: {_C['text']};
                border-color: {_C['accent']};
            }}
            QPushButton:pressed {{ background-color: {_C['surface']}; }}
            QPushButton:disabled {{
                color: #5A7090;
                border-color: #1D3048;
            }}
        """)


class _DangerButton(QPushButton):
    """Red danger-style button (retry/recover)."""
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {_C['danger']};
                border: 1px solid {_C['danger']};
                border-radius: 7px;
                padding: 0 14px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: rgba(224,82,82,0.12);
            }}
            QPushButton:pressed {{ background-color: rgba(224,82,82,0.22); }}
            QPushButton:disabled {{
                color: #5A7090;
                border-color: #1D3048;
            }}
        """)


class _Card(QWidget):
    """Elevated surface card."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            _Card, QWidget#card {{
                background-color: {_C['surface']};
                border: 1px solid {_C['border']};
                border-radius: 10px;
            }}
        """)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(18, 16, 18, 16)
        self._layout.setSpacing(10)

    def layout(self):  # type: ignore[override]
        return self._layout


class _StatusBadge(QLabel):
    """Coloured pill badge for operation state."""
    _COLORS = {
        "accepted":   (_C["success"],  "rgba(62,201,122,0.15)"),
        "prepared":   (_C["security"], "rgba(64,214,196,0.15)"),
        "draft":      (_C["draft"],    "rgba(91,141,217,0.15)"),
        "failed":     (_C["danger"],   "rgba(224,82,82,0.15)"),
        "unknown":    (_C["warning"],  "rgba(245,166,35,0.15)"),
        "submitting": (_C["warning"],  "rgba(245,166,35,0.15)"),
        "working":    (_C["accent"],   "rgba(117,108,244,0.15)"),
        "locked":     (_C["text_dim"], "rgba(90,112,144,0.15)"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(26)
        self.set_state("locked", "Locked")

    def set_state(self, key: str, display: str):
        fg, bg = self._COLORS.get(key.lower(), (_C["text2"], "rgba(155,173,191,0.15)"))
        self.setText(display)
        self.setStyleSheet(f"""
            QLabel {{
                color: {fg};
                background-color: {bg};
                border: 1px solid {fg};
                border-radius: 5px;
                padding: 0 10px;
                font-size: 12px;
                font-weight: 600;
            }}
        """)


class _ShieldLogo(QWidget):
    """Minimal shield/envelope vector logo drawn with QPainter."""
    def __init__(self, size: int = 44, parent=None):
        super().__init__(parent)
        self._sz = size
        self.setFixedSize(size, size)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        sz = self._sz
        # Shield outline
        path = QPainterPath()
        path.moveTo(sz * 0.5, sz * 0.05)
        path.lineTo(sz * 0.92, sz * 0.22)
        path.lineTo(sz * 0.92, sz * 0.58)
        path.quadTo(sz * 0.92, sz * 0.88, sz * 0.5, sz * 0.97)
        path.quadTo(sz * 0.08, sz * 0.88, sz * 0.08, sz * 0.58)
        path.lineTo(sz * 0.08, sz * 0.22)
        path.closeSubpath()
        grad = QLinearGradient(0, 0, 0, sz)
        grad.setColorAt(0, QColor(_C["accent"]))
        grad.setColorAt(1, QColor(_C["security"]))
        p.fillPath(path, grad)
        # Envelope body inside shield
        env_x, env_y = int(sz * 0.24), int(sz * 0.36)
        env_w, env_h = int(sz * 0.52), int(sz * 0.36)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#0B1220"))
        p.drawRoundedRect(env_x, env_y, env_w, env_h, 3, 3)
        pen = QPen(QColor("#F0F5FC"), 1.4)
        p.setPen(pen)
        p.drawLine(env_x, env_y, int(sz * 0.5), int(sz * 0.5))
        p.drawLine(int(sz * 0.5), int(sz * 0.5), env_x + env_w, env_y)
        p.end()


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar navigation button
# ──────────────────────────────────────────────────────────────────────────────
class _NavButton(QPushButton):
    def __init__(self, icon_char: str, label: str, parent=None):
        super().__init__(parent)
        self._icon_char = icon_char
        self._label = label
        self.setCheckable(True)
        self.setFixedHeight(48)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh()

    def _refresh(self):
        active = self.isChecked()
        fg = _C["text"] if active else _C["text2"]
        bg = f"background-color: rgba(117,108,244,0.15); border-left: 3px solid {_C['accent']};" if active else "background-color: transparent; border-left: 3px solid transparent;"
        self.setStyleSheet(f"""
            QPushButton {{
                {bg}
                color: {fg};
                text-align: left;
                padding-left: 18px;
                font-size: 13px;
                border-top: none;
                border-right: none;
                border-bottom: none;
                border-radius: 0;
            }}
            QPushButton:hover {{
                background-color: rgba(117,108,244,0.1);
                color: {_C['text']};
            }}
        """)
        self.setText(f"  {self._icon_char}   {self._label}")

    def setChecked(self, v):  # noqa: N802
        super().setChecked(v)
        self._refresh()


# ──────────────────────────────────────────────────────────────────────────────
# Field-row helper
# ──────────────────────────────────────────────────────────────────────────────
def _field_row(label_text: str, widget: QWidget) -> QWidget:
    row = QWidget()
    row.setStyleSheet("background: transparent;")
    v = QVBoxLayout(row)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(4)
    lbl = _label(label_text, size=11, color=_C["text2"])
    lbl.setStyleSheet(f"color: {_C['text2']}; font-size: 11px; font-weight: 600; letter-spacing: 0.5px; background: transparent;")
    v.addWidget(lbl)
    v.addWidget(widget)
    return row


# ──────────────────────────────────────────────────────────────────────────────
# Compose page
# ──────────────────────────────────────────────────────────────────────────────
class _ComposePage(QWidget):
    def __init__(self, panel: "ComposePanel"):
        super().__init__()
        self._p = panel
        self.setStyleSheet("background: transparent;")
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(0)

        # Header
        header = QHBoxLayout()
        title = _label("Compose Secure Message", _C["text"], size=18, bold=True)
        title.setStyleSheet(f"color: {_C['text']}; font-size: 18px; font-weight: 700; background: transparent;")
        header.addWidget(title)
        header.addStretch()
        demo_badge = QLabel("LOCAL RESEARCH DEMO")
        demo_badge.setStyleSheet(f"""
            QLabel {{
                color: {_C['text_dim']};
                background-color: rgba(41,59,83,0.6);
                border: 1px solid {_C['border']};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
            }}
        """)
        header.addWidget(demo_badge)
        root.addLayout(header)
        root.addSpacing(4)
        sub = _label("End-to-end encrypted via OpenPGP/PQ — disposable fixture identities only", color=_C["text2"], size=12)
        sub.setStyleSheet(f"color: {_C['text2']}; font-size: 12px; background: transparent;")
        root.addWidget(sub)
        root.addSpacing(20)

        # ── Form card ──
        form_card = QWidget()
        form_card.setStyleSheet(f"""
            QWidget {{
                background-color: {_C['surface']};
                border: 1px solid {_C['border']};
                border-radius: 12px;
            }}
        """)
        form_v = QVBoxLayout(form_card)
        form_v.setContentsMargins(22, 20, 22, 20)
        form_v.setSpacing(14)

        # Sender row
        sender_row = QHBoxLayout()
        sender_row.setSpacing(12)
        sender_label = QLabel("From")
        sender_label.setFixedWidth(60)
        sender_label.setStyleSheet(f"color: {_C['text2']}; font-size: 12px; font-weight: 600; background: transparent;")
        sender_row.addWidget(sender_label)
        # Use the panel's accounts combobox directly
        panel.accounts.setStyleSheet(f"""
            QComboBox {{
                background-color: {_C['elevated']};
                border: 1px solid {_C['border']};
                border-radius: 7px;
                padding: 7px 12px;
                color: {_C['text']};
                font-size: 13px;
            }}
            QComboBox:focus {{ border-color: {_C['accent']}; }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox QAbstractItemView {{
                background-color: {_C['elevated']};
                border: 1px solid {_C['border']};
                color: {_C['text']};
                selection-background-color: {_C['accent']};
            }}
        """)
        sender_row.addWidget(panel.accounts)
        form_v.addLayout(sender_row)
        form_v.addWidget(_divider())

        # To / Cc
        for field_label, widget in [("To", panel.to), ("Cc", panel.cc)]:
            r = QHBoxLayout()
            r.setSpacing(12)
            lbl = QLabel(field_label)
            lbl.setFixedWidth(60)
            lbl.setStyleSheet(f"color: {_C['text2']}; font-size: 12px; font-weight: 600; background: transparent;")
            r.addWidget(lbl)
            widget.setPlaceholderText("address@example.invalid, address2@example.invalid" if field_label == "To" else "Optional")
            widget.setStyleSheet(f"""
                QLineEdit {{
                    background-color: transparent;
                    border: none;
                    color: {_C['text']};
                    font-size: 13px;
                    padding: 5px 0;
                }}
                QLineEdit:focus {{ border-bottom: 1px solid {_C['accent']}; }}
            """)
            r.addWidget(widget)
            form_v.addLayout(r)
            form_v.addWidget(_divider())

        # Subject
        subj_row = QHBoxLayout()
        subj_row.setSpacing(12)
        subj_lbl = QLabel("Subject")
        subj_lbl.setFixedWidth(60)
        subj_lbl.setStyleSheet(f"color: {_C['text2']}; font-size: 12px; font-weight: 600; background: transparent;")
        subj_row.addWidget(subj_lbl)
        panel.subject.setPlaceholderText("Protected subject line (encrypted)")
        panel.subject.setStyleSheet(f"""
            QLineEdit {{
                background-color: transparent;
                border: none;
                color: {_C['text']};
                font-size: 14px;
                font-weight: 600;
                padding: 5px 0;
            }}
            QLineEdit:focus {{ border-bottom: 1px solid {_C['accent']}; }}
        """)
        subj_row.addWidget(panel.subject)
        form_v.addLayout(subj_row)
        form_v.addWidget(_divider())

        # Body
        panel.body.setPlaceholderText("Write your confidential message here…\n\nThis content will be encrypted end-to-end before any storage or transmission.")
        panel.body.setMinimumHeight(180)
        panel.body.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: transparent;
                border: none;
                color: {_C['text']};
                font-size: 13px;
                padding: 8px 0;
                line-height: 1.5;
            }}
        """)
        form_v.addWidget(panel.body)

        # Archive checkbox
        panel.archive.setText("  Include sender archival copy (sender can decrypt)")
        panel.archive.setStyleSheet(f"""
            QCheckBox {{
                color: {_C['text2']};
                font-size: 12px;
                background: transparent;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 15px; height: 15px;
                border: 1px solid {_C['border']};
                border-radius: 3px;
                background-color: {_C['elevated']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {_C['accent']};
                border-color: {_C['accent']};
            }}
        """)
        form_v.addWidget(panel.archive)
        root.addWidget(form_card)
        root.addSpacing(16)

        # ── Action bar ──
        actions = QHBoxLayout()
        actions.setSpacing(10)

        self._btn_draft = _SecondaryButton("☁  Save Draft")
        self._btn_draft.setToolTip("Encrypt and persist draft to durable outbox storage")
        self._btn_draft.clicked.connect(lambda: panel.start("draft"))

        self._btn_prepare = _PrimaryButton("🔒  Prepare Secure Message")
        self._btn_prepare.setMinimumWidth(220)
        self._btn_prepare.setToolTip("Sign, encrypt, and durably commit the full PGP/MIME envelope")
        self._btn_prepare.clicked.connect(lambda: panel.start("prepare"))

        self._btn_cancel = _SecondaryButton("✕  Cancel")
        self._btn_cancel.setToolTip("Cancel pending worker and clear content")
        self._btn_cancel.clicked.connect(panel.cancel)

        unlock_btn = _SecondaryButton("⬟  Unlock")
        unlock_btn.setToolTip("Unlock / re-select the current fixture identity")
        unlock_btn.clicked.connect(lambda: panel.select(panel.accounts.currentIndex()))

        lock_btn = _SecondaryButton("⬛  Lock")
        lock_btn.setToolTip("Lock session; clears compose fields")
        lock_btn.clicked.connect(lambda: panel.session.install(locked=True))

        actions.addWidget(unlock_btn)
        actions.addWidget(lock_btn)
        actions.addStretch()
        actions.addWidget(self._btn_cancel)
        actions.addWidget(self._btn_draft)
        actions.addWidget(self._btn_prepare)
        root.addLayout(actions)
        root.addStretch()


# ──────────────────────────────────────────────────────────────────────────────
# Secure Outbox page
# ──────────────────────────────────────────────────────────────────────────────
class _OutboxPage(QWidget):
    def __init__(self, panel: "ComposePanel"):
        super().__init__()
        self._p = panel
        self.setStyleSheet("background: transparent;")
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(0)

        # Header
        title = _label("Secure Outbox", _C["text"], size=18, bold=True)
        title.setStyleSheet(f"color: {_C['text']}; font-size: 18px; font-weight: 700; background: transparent;")
        root.addWidget(title)
        root.addSpacing(4)
        sub = _label("Durable message state — controlled loopback TLS SMTP only — no recipient delivery claim", color=_C["text2"], size=12)
        sub.setStyleSheet(f"color: {_C['text2']}; font-size: 12px; background: transparent;")
        root.addWidget(sub)
        root.addSpacing(22)

        # Message info card
        info_card = QWidget()
        info_card.setStyleSheet(f"""
            QWidget {{
                background-color: {_C['surface']};
                border: 1px solid {_C['border']};
                border-radius: 12px;
            }}
        """)
        info_v = QVBoxLayout(info_card)
        info_v.setContentsMargins(22, 18, 22, 18)
        info_v.setSpacing(12)

        hdr = QHBoxLayout()
        hdr.addWidget(_label("CURRENT MESSAGE", color=_C["text2"], size=11))
        hdr.addStretch()
        self._state_badge = _StatusBadge()
        hdr.addWidget(self._state_badge)
        info_v.addLayout(hdr)
        info_v.addWidget(_divider())

        self._lbl_to = _label("—", color=_C["text"], size=13)
        self._lbl_to.setStyleSheet(f"color: {_C['text']}; font-size: 13px; background: transparent;")
        self._lbl_subj = _label("—", color=_C["text"], size=14, bold=True)
        self._lbl_subj.setStyleSheet(f"color: {_C['text']}; font-size: 14px; font-weight: 600; background: transparent;")
        self._lbl_id = _label("—", color=_C["text2"], size=11)
        self._lbl_id.setStyleSheet(f"color: {_C['text2']}; font-size: 11px; font-family: monospace; background: transparent;")
        self._lbl_reason = _label("Save a draft first", color=_C["text2"], size=12)
        self._lbl_reason.setStyleSheet(f"color: {_C['text2']}; font-size: 12px; background: transparent;")
        self._lbl_reason.setWordWrap(True)

        grid = [
            ("Recipients", self._lbl_to),
            ("Subject", self._lbl_subj),
            ("Operation ID", self._lbl_id),
            ("Status detail", self._lbl_reason),
        ]
        for g_label, g_widget in grid:
            r = QHBoxLayout()
            r.setSpacing(16)
            kl = QLabel(g_label)
            kl.setFixedWidth(110)
            kl.setStyleSheet(f"color: {_C['text2']}; font-size: 11px; font-weight: 600; background: transparent;")
            r.addWidget(kl)
            r.addWidget(g_widget)
            info_v.addLayout(r)

        root.addWidget(info_card)
        root.addSpacing(18)

        # Security note
        note = QWidget()
        note.setStyleSheet(f"""
            QWidget {{
                background-color: rgba(64,214,196,0.07);
                border: 1px solid rgba(64,214,196,0.25);
                border-radius: 8px;
            }}
        """)
        note_h = QHBoxLayout(note)
        note_h.setContentsMargins(16, 12, 16, 12)
        note_icon = _label("🔐", color=_C["security"], size=16)
        note_icon.setStyleSheet("background: transparent; font-size: 16px;")
        note_text = _label(
            "Server acceptance confirms DATA accepted by the controlled loopback fixture — "
            "not that the message was delivered to a recipient mailbox.",
            color="#6ECFC4", size=12
        )
        note_text.setStyleSheet("color: #6ECFC4; font-size: 12px; background: transparent;")
        note_text.setWordWrap(True)
        note_h.addWidget(note_icon)
        note_h.addSpacing(10)
        note_h.addWidget(note_text)
        root.addWidget(note)
        root.addSpacing(18)

        # Action bar
        actions = QHBoxLayout()
        actions.setSpacing(10)

        self._btn_inspect = _SecondaryButton("🔍  Inspect State")
        self._btn_inspect.clicked.connect(lambda: panel.start("inspect"))
        self._btn_inspect.setToolTip("Inspect durable outbox state without submission")

        self._btn_submit = _PrimaryButton("📤  Submit via Local TLS")
        self._btn_submit.clicked.connect(lambda: panel.start("submit"))
        self._btn_submit.setToolTip("Submit prepared envelope through controlled loopback SMTP/TLS")

        self._btn_recover = _SecondaryButton("🔄  Recover")
        self._btn_recover.clicked.connect(lambda: panel.start("recover"))
        self._btn_recover.setToolTip("Recover interrupted submissions to Unknown state")

        self._btn_retry = _DangerButton("⚠  Retry")
        self._btn_retry.clicked.connect(panel.retry_action)
        self._btn_retry.setToolTip("Retry after explicit duplicate-risk acknowledgment")

        self._btn_export = _SecondaryButton("💾  Export Receipt")
        self._btn_export.clicked.connect(panel.export)
        self._btn_export.setToolTip("Export delivery status receipt to file")

        actions.addWidget(self._btn_inspect)
        actions.addWidget(self._btn_recover)
        actions.addWidget(self._btn_retry)
        actions.addStretch()
        actions.addWidget(self._btn_export)
        actions.addWidget(self._btn_submit)
        root.addLayout(actions)
        root.addStretch()

    def update_from_status(self, text: str, panel: "ComposePanel"):
        """Update outbox display from the status string."""
        lower = text.lower()
        if "accepted" in lower:
            self._state_badge.set_state("accepted", "Accepted")
        elif "prepared" in lower:
            self._state_badge.set_state("prepared", "Prepared")
        elif "draft" in lower:
            self._state_badge.set_state("draft", "Draft Saved")
        elif "failed" in lower or "rejected" in lower:
            self._state_badge.set_state("failed", "Failed")
        elif "unknown" in lower:
            self._state_badge.set_state("unknown", "Unknown")
        elif "working" in lower or "submitting" in lower:
            self._state_badge.set_state("working", "Working…")
        elif "locked" in lower or "cancelled" in lower:
            self._state_badge.set_state("locked", "Locked")
        else:
            self._state_badge.set_state("draft", text[:40] if text else "—")

        # Populate recipient / subject / op-id from current panel state
        ctx = None
        try:
            snap = panel.session.snapshot
            if snap.active:
                ctx = snap.active.context
                op = panel.operations.get(ctx.account.value) if ctx else None
                if op:
                    self._lbl_id.setText(str(op.value)[:36] + "…" if len(str(op.value)) > 36 else str(op.value))
        except Exception:
            pass
        to_text = panel.to.text()
        subj_text = panel.subject.text()
        if to_text:
            self._lbl_to.setText(to_text)
        if subj_text:
            self._lbl_subj.setText(subj_text)
        parts = text.split(" · ")
        self._lbl_reason.setText(parts[1] if len(parts) > 1 else text)


# ──────────────────────────────────────────────────────────────────────────────
# Open Message / Verified Viewer page
# ──────────────────────────────────────────────────────────────────────────────
class _ViewerPage(QWidget):
    def __init__(self, panel: "ComposePanel"):
        super().__init__()
        self._p = panel
        self.setStyleSheet("background: transparent;")
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(0)

        title = _label("Verified Message Viewer", _C["text"], size=18, bold=True)
        title.setStyleSheet(f"color: {_C['text']}; font-size: 18px; font-weight: 700; background: transparent;")
        root.addWidget(title)
        root.addSpacing(4)
        sub = _label("Decrypts and verifies the persisted ciphertext copy — not IMAP receive", color=_C["text2"], size=12)
        sub.setStyleSheet(f"color: {_C['text2']}; font-size: 12px; background: transparent;")
        root.addWidget(sub)
        root.addSpacing(22)

        # Identity / action row
        id_card = QWidget()
        id_card.setStyleSheet(f"""
            QWidget {{
                background-color: {_C['surface']};
                border: 1px solid {_C['border']};
                border-radius: 12px;
            }}
        """)
        id_h = QHBoxLayout(id_card)
        id_h.setContentsMargins(20, 14, 20, 14)
        id_h.setSpacing(14)

        id_h.addWidget(_label("Viewing as:", color=_C["text2"], size=12))
        self._lbl_active = _label("— select account —", color=_C["text"], size=13, bold=True)
        self._lbl_active.setStyleSheet(f"color: {_C['text']}; font-size: 13px; font-weight: 600; background: transparent;")
        id_h.addWidget(self._lbl_active)
        id_h.addStretch()

        self._btn_open = _PrimaryButton("🔓  Decrypt & Verify")
        self._btn_open.clicked.connect(lambda: panel.start("open"))
        self._btn_open.setToolTip("Decrypt and cryptographically verify the prepared message copy")
        id_h.addWidget(self._btn_open)
        root.addWidget(id_card)
        root.addSpacing(14)

        # Verification result banner (hidden until open)
        self._verify_banner = QWidget()
        self._verify_banner.setStyleSheet(f"""
            QWidget {{
                background-color: rgba(62,201,122,0.09);
                border: 1px solid rgba(62,201,122,0.3);
                border-radius: 8px;
            }}
        """)
        banner_h = QHBoxLayout(self._verify_banner)
        banner_h.setContentsMargins(16, 12, 16, 12)
        self._verify_icon = _label("✓", color=_C["success"], size=18, bold=True)
        self._verify_icon.setStyleSheet("background: transparent; font-size: 18px; font-weight: 700; color: #3EC97A;")
        self._verify_text = _label("Signature valid", color="#76E0A8", size=12)
        self._verify_text.setStyleSheet("color: #76E0A8; font-size: 12px; background: transparent;")
        self._verify_text.setWordWrap(True)
        banner_h.addWidget(self._verify_icon)
        banner_h.addSpacing(10)
        banner_h.addWidget(self._verify_text)
        self._verify_banner.hide()
        root.addWidget(self._verify_banner)
        root.addSpacing(4)

        # Message display card
        msg_card = QWidget()
        msg_card.setStyleSheet(f"""
            QWidget {{
                background-color: {_C['surface']};
                border: 1px solid {_C['border']};
                border-radius: 12px;
            }}
        """)
        msg_v = QVBoxLayout(msg_card)
        msg_v.setContentsMargins(22, 18, 22, 18)
        msg_v.setSpacing(10)

        hdr_row = QHBoxLayout()
        hdr_row.addWidget(_label("DECRYPTED CONTENT", color=_C["text2"], size=11))
        hdr_row.addStretch()
        self._replay_badge = _StatusBadge()
        self._replay_badge.hide()
        hdr_row.addWidget(self._replay_badge)
        msg_v.addLayout(hdr_row)
        msg_v.addWidget(_divider())

        # Use the panel's content widget directly
        panel.content.setReadOnly(True)
        panel.content.setMinimumHeight(200)
        panel.content.setPlaceholderText(
            "No verified content yet.\n\n"
            "Select a fixture identity above, then click 'Decrypt & Verify'.\n"
            "Content is never displayed before successful backend cryptographic processing."
        )
        panel.content.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {_C['elevated']};
                border: 1px solid {_C['border']};
                border-radius: 8px;
                color: {_C['text']};
                font-size: 13px;
                padding: 12px;
                font-family: "Segoe UI", "Arial", sans-serif;
            }}
        """)
        msg_v.addWidget(panel.content)
        root.addWidget(msg_card)
        root.addStretch()

    def show_verified(self, msg: OpenedMessage):
        """Populate viewer with a successfully opened message."""
        trust_map = {
            "independently_verified": ("✓  Signature Valid — Identity Independently Verified", _C["success"], "rgba(62,201,122,0.09)", "rgba(62,201,122,0.3)"),
            "local_enrolled_identity": ("✓  Signature Valid — Local Enrolled Identity", _C["success"], "rgba(62,201,122,0.09)", "rgba(62,201,122,0.3)"),
            "in-person": ("✓  Signature Valid — In-Person Verified Contact", _C["security"], "rgba(64,214,196,0.09)", "rgba(64,214,196,0.3)"),
        }
        desc, color, bg, border = trust_map.get(
            msg.identity_trust,
            (f"⚠  Signature Valid — Trust: {msg.identity_trust}", _C["warning"], "rgba(245,166,35,0.09)", "rgba(245,166,35,0.3)")
        )
        replay_info = {
            "fresh": "", "duplicate_delivery": "  ·  Duplicate copy detected",
            "protected_identity_conflict": "  ·  ⚠ Identity conflict"
        }.get(msg.replay.value, "")

        self._verify_text.setText(f"{desc}{replay_info}")
        self._verify_banner.setStyleSheet(f"""
            QWidget {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
        """)
        self._verify_icon.setStyleSheet(f"background: transparent; font-size: 18px; font-weight: 700; color: {color};")
        self._verify_text.setStyleSheet(f"color: {color}; font-size: 12px; background: transparent;")
        self._verify_banner.show()

        if msg.replay.value != "fresh":
            key = "unknown" if "conflict" in msg.replay.value else "warning"
            label = "Conflict" if "conflict" in msg.replay.value else "Duplicate"
            self._replay_badge.set_state(key, label)
            self._replay_badge.show()
        else:
            self._replay_badge.hide()

        archive_note = "  [Sender archive copy]" if msg.archive else ""
        self._lbl_active.setText(f"{msg.sender}{archive_note}")

    def show_failed(self, reason: str):
        self._verify_banner.setStyleSheet(f"""
            QWidget {{
                background-color: rgba(224,82,82,0.09);
                border: 1px solid rgba(224,82,82,0.3);
                border-radius: 8px;
            }}
        """)
        self._verify_icon.setStyleSheet("background: transparent; font-size: 18px; font-weight: 700; color: #E05252;")
        self._verify_icon.setText("✕")
        self._verify_text.setStyleSheet("color: #E87676; font-size: 12px; background: transparent;")
        self._verify_text.setText(f"Verification failed — {reason}")
        self._verify_banner.show()
        self._replay_badge.hide()

    def clear(self):
        self._verify_banner.hide()
        self._replay_badge.hide()
        self._verify_icon.setText("✓")


# ──────────────────────────────────────────────────────────────────────────────
# Session / Activity page
# ──────────────────────────────────────────────────────────────────────────────
class _SessionPage(QWidget):
    def __init__(self, panel: "ComposePanel"):
        super().__init__()
        self._p = panel
        self.setStyleSheet("background: transparent;")
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(0)

        title = _label("Session & Activity", _C["text"], size=18, bold=True)
        title.setStyleSheet(f"color: {_C['text']}; font-size: 18px; font-weight: 700; background: transparent;")
        root.addWidget(title)
        root.addSpacing(4)
        sub = _label("Fixture account state and live operation feedback", color=_C["text2"], size=12)
        sub.setStyleSheet(f"color: {_C['text2']}; font-size: 12px; background: transparent;")
        root.addWidget(sub)
        root.addSpacing(22)

        # Session card
        sess_card = QWidget()
        sess_card.setStyleSheet(f"""
            QWidget {{
                background-color: {_C['surface']};
                border: 1px solid {_C['border']};
                border-radius: 12px;
            }}
        """)
        sv = QVBoxLayout(sess_card)
        sv.setContentsMargins(22, 18, 22, 18)
        sv.setSpacing(12)

        hdr = QHBoxLayout()
        hdr.addWidget(_label("FIXTURE SESSION", color=_C["text2"], size=11))
        hdr.addStretch()
        self._lock_badge = _StatusBadge()
        hdr.addWidget(self._lock_badge)
        sv.addLayout(hdr)
        sv.addWidget(_divider())

        self._lbl_account = _label("—", color=_C["text"], size=13)
        self._lbl_account.setStyleSheet(f"color: {_C['text']}; font-size: 13px; background: transparent;")
        self._lbl_lifecycle = _label("—", color=_C["text2"], size=12)
        self._lbl_lifecycle.setStyleSheet(f"color: {_C['text2']}; font-size: 12px; background: transparent;")

        for row_label, row_widget in [
            ("Active account", self._lbl_account),
            ("Lifecycle state", self._lbl_lifecycle),
        ]:
            r = QHBoxLayout()
            r.setSpacing(16)
            kl = QLabel(row_label)
            kl.setFixedWidth(130)
            kl.setStyleSheet(f"color: {_C['text2']}; font-size: 11px; font-weight: 600; background: transparent;")
            r.addWidget(kl)
            r.addWidget(row_widget)
            sv.addLayout(r)

        sv.addSpacing(6)
        sv.addWidget(_divider())
        sv.addSpacing(4)

        # Last operation
        sv.addWidget(_label("LAST OPERATION FEEDBACK", color=_C["text2"], size=11))
        sv.addSpacing(4)
        self._lbl_last_op = _label("—", color=_C["text"], size=13)
        self._lbl_last_op.setWordWrap(True)
        self._lbl_last_op.setStyleSheet(f"color: {_C['text']}; font-size: 13px; background: transparent;")
        sv.addWidget(self._lbl_last_op)
        root.addWidget(sess_card)
        root.addSpacing(22)

        # Limits card
        limits_card = QWidget()
        limits_card.setStyleSheet(f"""
            QWidget {{
                background-color: {_C['surface']};
                border: 1px solid {_C['border']};
                border-radius: 12px;
            }}
        """)
        lv = QVBoxLayout(limits_card)
        lv.setContentsMargins(22, 18, 22, 18)
        lv.setSpacing(8)
        lv.addWidget(_label("M5 EXPERIMENTAL LIMITS", color=_C["text2"], size=11))
        lv.addWidget(_divider())
        limits = [
            ("Body", "8 KiB UTF-8"),
            ("Recipients", "3 To/Cc (+ optional sender archive)"),
            ("Attachments", "4 files, 16 KiB aggregate"),
            ("Outer envelope", "256 KiB PGP/MIME"),
            ("Operation deadline", "30 seconds"),
            ("Outbox operations", "16 per account"),
            ("Replay log", "256 identities"),
        ]
        for lim_k, lim_v in limits:
            r = QHBoxLayout()
            r.setSpacing(16)
            kl = QLabel(lim_k)
            kl.setFixedWidth(160)
            kl.setStyleSheet(f"color: {_C['text2']}; font-size: 12px; background: transparent;")
            vl = QLabel(lim_v)
            vl.setStyleSheet(f"color: {_C['text']}; font-size: 12px; background: transparent;")
            r.addWidget(kl)
            r.addWidget(vl)
            lv.addLayout(r)

        lv.addSpacing(8)
        marker_lbl = _label("Profile: QM-OPENPGP-PQ-1-EXPERIMENT-M5", color=_C["text_dim"], size=11)
        marker_lbl.setStyleSheet(f"color: {_C['text_dim']}; font-size: 11px; font-family: monospace; background: transparent;")
        lv.addWidget(marker_lbl)
        root.addWidget(limits_card)
        root.addStretch()

    def update_session(self, snapshot, last_op: str):
        active = snapshot.active
        locked = snapshot.locked
        if active:
            self._lbl_account.setText(active.address)
            self._lbl_lifecycle.setText(getattr(active, "lifecycle", "enrolled"))
        else:
            self._lbl_account.setText("—")
            self._lbl_lifecycle.setText("—")
        if locked:
            self._lock_badge.set_state("locked", "Locked")
        else:
            self._lock_badge.set_state("prepared", "Unlocked")
        if last_op:
            self._lbl_last_op.setText(last_op)


# ──────────────────────────────────────────────────────────────────────────────
# Main window shell
# ──────────────────────────────────────────────────────────────────────────────
class _MainShell(QMainWindow):
    """Presentation-quality main window hosting the four pages."""

    def __init__(self, panel: "ComposePanel"):
        super().__init__()
        self._p = panel
        self.setWindowTitle("QuMail — Secure Messaging Workspace")
        self.setMinimumSize(1024, 680)
        self.resize(1280, 780)
        self.setStyleSheet(APP_QSS)

        central = QWidget()
        central.setObjectName("central")
        central.setStyleSheet("background-color: #0B1220;")
        self.setCentralWidget(central)
        main_h = QHBoxLayout(central)
        main_h.setContentsMargins(0, 0, 0, 0)
        main_h.setSpacing(0)

        # ── Sidebar ──
        sidebar = QWidget()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(f"background-color: {_C['sidebar']}; border-right: 1px solid {_C['border']};")
        sidebar_v = QVBoxLayout(sidebar)
        sidebar_v.setContentsMargins(0, 0, 0, 0)
        sidebar_v.setSpacing(0)

        # Logo / branding
        brand = QWidget()
        brand.setFixedHeight(72)
        brand.setStyleSheet(f"background-color: {_C['sidebar']};")
        brand_h = QHBoxLayout(brand)
        brand_h.setContentsMargins(16, 0, 16, 0)
        brand_h.setSpacing(12)
        logo = _ShieldLogo(36)
        brand_h.addWidget(logo)
        brand_text = QWidget()
        brand_text.setStyleSheet("background: transparent;")
        bt_v = QVBoxLayout(brand_text)
        bt_v.setContentsMargins(0, 0, 0, 0)
        bt_v.setSpacing(1)
        app_name = QLabel("QuMail")
        app_name.setStyleSheet(f"color: {_C['text']}; font-size: 16px; font-weight: 700; background: transparent;")
        tagline = QLabel("Secure Messaging Workspace")
        tagline.setStyleSheet(f"color: {_C['text2']}; font-size: 10px; background: transparent;")
        bt_v.addWidget(app_name)
        bt_v.addWidget(tagline)
        brand_h.addWidget(brand_text)
        brand_h.addStretch()
        sidebar_v.addWidget(brand)

        div = _divider()
        div.setStyleSheet(f"background-color: {_C['border']}; max-height: 1px; margin: 0 16px;")
        sidebar_v.addWidget(div)
        sidebar_v.addSpacing(12)

        # Nav label
        nav_section = QLabel("  WORKSPACE")
        nav_section.setStyleSheet(f"color: {_C['text_dim']}; font-size: 10px; font-weight: 700; letter-spacing: 1px; padding-left: 20px; background: transparent;")
        sidebar_v.addWidget(nav_section)
        sidebar_v.addSpacing(4)

        self._nav_buttons = []
        nav_items = [
            ("✉", "Compose"),
            ("⬡", "Secure Outbox"),
            ("🔓", "Open Message"),
            ("◈", "Session"),
        ]
        for idx, (icon, label) in enumerate(nav_items):
            btn = _NavButton(icon, label)
            btn.clicked.connect(lambda checked=False, i=idx: self._navigate(i))
            self._nav_buttons.append(btn)
            sidebar_v.addWidget(btn)

        sidebar_v.addStretch()

        # Bottom info
        info_area = QWidget()
        info_area.setStyleSheet("background: transparent;")
        info_v = QVBoxLayout(info_area)
        info_v.setContentsMargins(16, 12, 16, 16)
        info_v.setSpacing(6)

        demo_lbl = QLabel("LOCAL RESEARCH DEMO")
        demo_lbl.setStyleSheet(f"""
            QLabel {{
                color: {_C['text_dim']};
                background-color: rgba(41,59,83,0.5);
                border: 1px solid {_C['border']};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1px;
            }}
        """)
        demo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_v.addWidget(demo_lbl)

        self._sidebar_status = QLabel("Initialising…")
        self._sidebar_status.setStyleSheet(f"color: {_C['text_dim']}; font-size: 10px; background: transparent;")
        self._sidebar_status.setWordWrap(True)
        info_v.addWidget(self._sidebar_status)
        sidebar_v.addWidget(info_area)
        main_h.addWidget(sidebar)

        # ── Content area ──
        content_wrap = QWidget()
        content_wrap.setStyleSheet("background-color: #0B1220;")
        content_v = QVBoxLayout(content_wrap)
        content_v.setContentsMargins(0, 0, 0, 0)
        content_v.setSpacing(0)

        # Top status bar
        topbar = QWidget()
        topbar.setFixedHeight(46)
        topbar.setStyleSheet(f"background-color: {_C['sidebar']}; border-bottom: 1px solid {_C['border']};")
        top_h = QHBoxLayout(topbar)
        top_h.setContentsMargins(20, 0, 20, 0)
        top_h.setSpacing(12)

        self._topbar_title = QLabel("Compose")
        self._topbar_title.setStyleSheet(f"color: {_C['text']}; font-size: 13px; font-weight: 600; background: transparent;")
        top_h.addWidget(self._topbar_title)
        top_h.addStretch()

        # Security indicator
        sec_dot = QLabel("●")
        sec_dot.setStyleSheet(f"color: {_C['security']}; font-size: 10px; background: transparent;")
        top_h.addWidget(sec_dot)
        sec_lbl = QLabel("Loopback TLS · Synthetic Identities · No External Mail")
        sec_lbl.setStyleSheet(f"color: {_C['text2']}; font-size: 11px; background: transparent;")
        top_h.addWidget(sec_lbl)

        top_h.addSpacing(12)
        self._topbar_status = _StatusBadge()
        top_h.addWidget(self._topbar_status)
        content_v.addWidget(topbar)

        # Stack
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")

        self._page_compose = _ComposePage(panel)
        self._page_outbox = _OutboxPage(panel)
        self._page_viewer = _ViewerPage(panel)
        self._page_session = _SessionPage(panel)

        for page in (self._page_compose, self._page_outbox, self._page_viewer, self._page_session):
            self._stack.addWidget(page)

        scroll.setWidget(self._stack)
        content_v.addWidget(scroll)
        main_h.addWidget(content_wrap)

        self._navigate(0)

    def _navigate(self, index: int):
        titles = ["Compose Secure Message", "Secure Outbox", "Verified Message Viewer", "Session & Activity"]
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)
        self._stack.setCurrentIndex(index)
        self._topbar_title.setText(titles[index])

    def update_status(self, text: str, panel: "ComposePanel"):
        """Propagate backend status to all relevant UI components."""
        lower = text.lower()
        if "accepted" in lower:
            self._topbar_status.set_state("accepted", "Accepted")
        elif "prepared" in lower:
            self._topbar_status.set_state("prepared", "Prepared")
        elif "draft" in lower:
            self._topbar_status.set_state("draft", "Draft")
        elif "failed" in lower or "rejected" in lower:
            self._topbar_status.set_state("failed", "Failed")
        elif "unknown" in lower:
            self._topbar_status.set_state("unknown", "Unknown")
        elif "working" in lower:
            self._topbar_status.set_state("working", "Working")
        elif "locked" in lower or "cancelled" in lower:
            self._topbar_status.set_state("locked", "Locked")
        else:
            self._topbar_status.set_state("draft", "—")

        short = text[:60] + ("…" if len(text) > 60 else "")
        self._sidebar_status.setText(short)
        self._page_outbox.update_from_status(text, panel)
        try:
            snap = panel.session.snapshot
            self._page_session.update_session(snap, text)
            active = snap.active
            self._page_viewer._lbl_active.setText(active.address if active and not snap.locked else "— select account —")
        except Exception:
            pass

    def closeEvent(self, event):  # noqa: N802
        self._p.closeEvent(event)


# ──────────────────────────────────────────────────────────────────────────────
# ComposePanel — public API preserved for smoke-test compatibility
# ──────────────────────────────────────────────────────────────────────────────
class ComposePanel(QWidget):
    """Premium QuMail M5 frontend.

    Smoke-test public surface (DO NOT RENAME/REMOVE):
        .to, .cc, .subject, .body         — QLineEdit / QPlainTextEdit
        .status                            — QLabel  (.text() returns last status)
        .content                           — QPlainTextEdit (decrypted output)
        .archive                           — QCheckBox
        .accounts                          — QComboBox
        .shared                            — (bytes, bytes) | None
        .pending                           — tuple | None
        .pool                              — ThreadPoolExecutor
        .select(index)
        .start(action, **kwargs)
        .poll()
    """

    def __init__(self, session, access, compose, opener, submit, views):
        super().__init__()
        self.session = session
        self.access = access
        self.compose = compose
        self.opener = opener
        self.submit = submit
        self.views = views

        # Backend state
        self.lease = None
        self.operations: dict = {}
        self.envelopes: dict = {}
        self.shared = None
        self.pending = None
        self.pool = ThreadPoolExecutor(max_workers=1)

        # ── Smoke-test-visible widgets ──
        # These are wired into the main UI but must remain accessible as
        # direct attributes with their expected Qt types.
        self.accounts = QComboBox()
        for view in views:
            self.accounts.addItem(view.address, view)
        self.accounts.currentIndexChanged.connect(self.select)

        self.to = QLineEdit()
        self.cc = QLineEdit()
        self.subject = QLineEdit()
        self.body = QPlainTextEdit()
        self.archive = QCheckBox()
        self.archive.setChecked(True)
        self.status = QLabel("Locked")
        self.content = QPlainTextEdit()
        self.content.setReadOnly(True)

        # ── Main window shell ──
        self._shell: Optional[_MainShell] = None

        # Qt polling timer — runs even in smoke mode
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.poll)
        self._timer.start(20)

        session.changed.connect(self._on_session_changed)
        self.select(0)

    # ── Session signal handler ──
    def _on_session_changed(self, snapshot):
        self.lease = self.access.select(
            snapshot.active.context if snapshot.active and not snapshot.locked else None
        )
        self.content.clear()
        self.subject.clear()
        self.body.clear()
        self.to.clear()
        self.cc.clear()
        text = "Locked" if snapshot.locked else "Selected; new draft or inspect saved operation"
        self._update_status(text)

    def _update_status(self, text: str):
        self.status.setText(text)
        if self._shell:
            self._shell.update_status(text, self)

    # ── Smoke-test API ──
    def select(self, index: int):
        view = self.accounts.itemData(index)
        if view:
            self.session.install(self.views, view)

    def cancel(self):
        if self.lease:
            self.lease.cancelled.set()
        self.content.clear()
        if self._shell:
            self._shell._page_viewer.clear()
        self._update_status("Cancelled; select/unlock to continue")

    def start(self, action: str, **kwargs):
        if not self.lease or self.lease.cancelled.is_set():
            self._update_status("Locked/cancelled")
            return
        if self.pending:
            self._update_status("Worker busy")
            return

        lease = self.lease
        generation = self.session.snapshot.generation
        view = self.session.snapshot.active
        operation = self.operations.get(lease.context.account.value)

        if action not in ("draft", "open", "recover") and operation is None:
            self._update_status("Save a draft first")
            return
        if action == "open" and self.shared is None:
            self._update_status("Prepare a message first")
            return

        shared = self.shared
        draft = Draft(
            tuple(v.strip() for v in self.to.text().split(",") if v.strip()),
            tuple(v.strip() for v in self.cc.text().split(",") if v.strip()),
            self.subject.text(),
            self.body.toPlainText(),
            archive=self.archive.isChecked(),
        )
        budget = Budget(lease.cancelled, time.monotonic() + 30)

        def work():
            if action == "draft":
                return self.compose.draft(lease, draft, budget)
            if action == "prepare":
                envelope = self.compose.prepare(lease, operation, view.key, budget)
                vault = self.compose.vault
                public = bytes(vault.key(vault._read(lease.context), lease.context, view.key)["public"])
                budget.check()
                return envelope, public
            if action == "open":
                return self.opener.open(lease, view.key, shared[0], shared[1], budget)
            if action == "recover":
                return self.submit.recover(lease)
            return getattr(self.submit, action)(lease, operation, **kwargs)

        self.pending = (generation, lease, action, self.pool.submit(work))
        self._update_status("Working")

    def poll(self):
        if not self.pending or not self.pending[3].done():
            return
        generation, lease, action, future = self.pending
        self.pending = None

        if (generation != self.session.snapshot.generation
                or lease is not self.lease
                or lease.cancelled.is_set()):
            return

        try:
            value = future.result()
            if action == "draft":
                self.operations[lease.context.account.value] = value
                self._update_status("Draft persisted encrypted")
            elif action == "prepare":
                envelope, public = value
                self.envelopes[lease.context.account.value] = envelope
                self.shared = (envelope.serialized, public)
                self._update_status("Prepared; exact MIME persisted before SMTP")
            elif isinstance(value, OpenedMessage):
                status_text = (
                    f"Signature valid; identity {value.identity_trust}; "
                    f"{value.replay.value}; mismatches {len(value.mismatches)}; archive {value.archive}"
                )
                self._update_status(status_text)
                # Explicit plaintext test view only; no HTML or attachment execution.
                self.content.setPlainText(value.subject + "\n\n" + value.body)
                if self._shell:
                    self._shell._page_viewer.show_verified(value)
            elif hasattr(value, "state"):
                self._update_status(value.state.value + " · " + value.reason)
            else:
                self._update_status("Completed; inspect durable state")
        except Exception as error:
            code = getattr(error, "code", None)
            err_text = code.value if code else "Operation rejected; no diagnostics or private output"
            self._update_status(err_text)
            self.content.clear()
            if self._shell:
                self._shell._page_viewer.show_failed(err_text)

    def retry_action(self):
        """Called from OutboxPage retry button (uses QMessageBox)."""
        if (QMessageBox.question(
            self._shell or self,
            "Explicit retry",
            "The server may already have accepted the message.\n"
            "A retry may duplicate delivery. Continue?",
        ) == QMessageBox.StandardButton.Yes):
            self.start("retry", acknowledge_duplicate_risk=True)

    # Alias for smoke-test compatibility (demo.py calls panel.retry in no-op path)
    def retry(self):
        self.retry_action()

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self._shell or self, "New status-only receipt")
        if path:
            def persist(result):
                with open(path, "x", encoding="utf-8") as f:
                    f.write(result.state.value + "\n" + result.reason + "\n")
            self.start("export_receipt", persist=persist)

    def show(self):
        """Override show() to display the main shell instead of this bare widget."""
        if self._shell is None:
            self._shell = _MainShell(self)
        self._shell.show()

    def close(self):
        if self._shell:
            self._shell.close()
        super().close()

    def closeEvent(self, event):  # noqa: N802
        self.session.install(locked=True)
        self._timer.stop()
        self.pool.shutdown(wait=False, cancel_futures=True)
        event.accept()
