# ui/key_status_widget.py — Reusable status bar widget for KME and session state.
# Single responsibility: display live KME connectivity, active security level,
# and the logged-in account, with periodic background polling and manual refresh.
# Does not send email, perform encryption, or modify session state.
# Embedded by main_window.py — not a standalone window.

from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QRect, QEasingCurve
from PyQt6.QtGui import QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from core.config import TQR_LEVEL_AES, TQR_LEVEL_MLKEM, TQR_LEVEL_OTP
from core.session import session
from kme.kme_client import kme_client


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_POLL_INTERVAL_MS = 5 * 60 * 1000   # 5 minutes

_TQR_LABELS: dict[int, str] = {
    TQR_LEVEL_OTP:   "Maximum Security",
    TQR_LEVEL_AES:   "High Security",
    TQR_LEVEL_MLKEM: "Quantum-Safe",
}

_TQR_ICONS: dict[int, str] = {
    TQR_LEVEL_OTP:   "🔒",
    TQR_LEVEL_AES:   "🛡️",
    TQR_LEVEL_MLKEM: "⚛️",
}

_C = {
    "bg_sidebar":    "#161B22",
    "text_primary":  "#E6EDF3",
    "text_secondary":"#8B949E",
    "text_tertiary": "#484F58",
    "border":        "#21262D",
    "accent":        "#6366F1",
    "accent_light":  "#818CF8",
    "accent_muted":  "#1E2238",
    "online":        "#22C55E",
    "offline":       "#EF4444",
}


# ---------------------------------------------------------------------------
# Animated Pulse Dot
# ---------------------------------------------------------------------------

class _PulseDot(QWidget):
    """
    A coloured indicator dot with an animated outer pulse ring when online.
    The pulse ring contracts and fades on repaint triggered by QTimer.
    """

    _DOT_SIZE   = 10
    _RING_MAX   = 20
    _WIDGET_SIZE = 24   # includes ring space

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._online = False
        self._ring_radius = 0.0     # animated: 0 → 1
        self._ring_alpha  = 0       # 0..255
        setattr(self, "_growing", True)
        self.setFixedSize(self._WIDGET_SIZE, self._WIDGET_SIZE)

        # Drive the pulse animation
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(40)    # ~25 fps
        self._pulse_timer.timeout.connect(self._tick_pulse)

    def set_online(self, online: bool) -> None:
        self._online = online
        if online:
            self._pulse_timer.start()
        else:
            self._pulse_timer.stop()
            self._ring_radius = 0.0
            self._ring_alpha  = 0
        self.update()

    def _tick_pulse(self) -> None:
        """Advance the pulse ring animation one frame."""
        growing = getattr(self, "_growing", True)
        if growing:
            self._ring_radius = min(1.0, self._ring_radius + 0.06)
            self._ring_alpha  = max(0, int(200 * (1.0 - self._ring_radius)))
            if self._ring_radius >= 1.0:
                setattr(self, "_growing", False)
        else:
            self._ring_radius = 0.0
            self._ring_alpha  = 0
            setattr(self, "_growing", True)
        self.update()

    def paintEvent(self, event) -> None:   # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        center = self._WIDGET_SIZE / 2
        colour = QColor(_C["online"] if self._online else _C["offline"])

        # Outer pulse ring (online only)
        if self._online and self._ring_radius > 0:
            ring_r = self._DOT_SIZE / 2 + self._ring_radius * (self._RING_MAX / 2 - self._DOT_SIZE / 2)
            ring_colour = QColor(_C["online"])
            ring_colour.setAlpha(self._ring_alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ring_colour)
            p.drawEllipse(
                int(center - ring_r), int(center - ring_r),
                int(ring_r * 2), int(ring_r * 2),
            )

        # Core dot
        dot_r = self._DOT_SIZE / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(colour)
        p.drawEllipse(
            int(center - dot_r), int(center - dot_r),
            self._DOT_SIZE, self._DOT_SIZE,
        )


# ---------------------------------------------------------------------------
# Pill badge helper
# ---------------------------------------------------------------------------

def _pill_label(text: str, fg: str, bg: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {fg}; background-color: {bg}; border-radius: 5px; "
        f"padding: 2px 8px; font-size: 11px; font-weight: 600;"
    )
    return lbl


# ---------------------------------------------------------------------------
# Public Widget
# ---------------------------------------------------------------------------

class KeyStatusWidget(QWidget):
    """
    Status bar showing:
      • Animated pulse dot + "QKD Connected / Offline" pill
      • Active security level pill  
      • Signed-in account email
      • Refresh button on the right

    Polls the KME on construction and every 5 minutes via QTimer.
    The Refresh button triggers an immediate poll.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._start_timer()
        session.account_changed.connect(self._on_account_changed)
        self.refresh()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(10)

        # Pulse dot
        self._dot = _PulseDot(self)
        layout.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)

        # Network pill
        self._network_pill = QLabel("")
        self._network_pill.setStyleSheet(
            f"color: {_C['text_secondary']}; font-size: 11px;"
        )
        layout.addWidget(self._network_pill, 0, Qt.AlignmentFlag.AlignVCenter)

        # Subtle separator
        sep1 = QLabel("│")
        sep1.setStyleSheet(f"color: {_C['border']}; font-size: 14px;")
        layout.addWidget(sep1, 0, Qt.AlignmentFlag.AlignVCenter)

        # Security level pill
        self._level_pill = QLabel("")
        self._level_pill.setStyleSheet(
            f"color: {_C['text_secondary']}; font-size: 11px; "
            f"background: transparent; border-radius: 4px; padding: 1px 6px;"
        )
        layout.addWidget(self._level_pill, 0, Qt.AlignmentFlag.AlignVCenter)

        sep2 = QLabel("│")
        sep2.setStyleSheet(f"color: {_C['border']}; font-size: 14px;")
        layout.addWidget(sep2, 0, Qt.AlignmentFlag.AlignVCenter)

        # Account email
        self._account_label = QLabel("Not signed in")
        self._account_label.setStyleSheet(
            f"color: {_C['text_tertiary']}; font-size: 11px;"
        )
        layout.addWidget(self._account_label, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addStretch()

        # Refresh button
        self._refresh_btn = QPushButton("↺ Refresh")
        self._refresh_btn.setStyleSheet(
            f"QPushButton {{ color: {_C['accent_light']}; background: transparent; "
            f"border: none; font-size: 11px; padding: 2px 8px; }} "
            f"QPushButton:hover {{ color: #FFFFFF; }}"
        )
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(self._refresh_btn, 0, Qt.AlignmentFlag.AlignVCenter)

    def _start_timer(self) -> None:
        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    def _on_account_changed(self, email: str) -> None:
        """
        Slot connected to session.account_changed signal.
        Updates the account label immediately on login, logout, or account switch
        without triggering a full KME poll — KME liveness is unrelated to account state.
        """
        self._account_label.setText(email or "Not signed in")

    def refresh(self) -> None:
        """Poll the KME and repaint all child widgets from live session state."""
        online = kme_client.is_online()
        session.kme_connected = online
        self._update_display(online)

    def _update_display(self, online: bool) -> None:
        # Dot
        self._dot.set_online(online)

        # Network pill
        if online:
            self._network_pill.setText("QKD  Online")
            self._network_pill.setStyleSheet(
                f"color: {_C['online']}; font-size: 11px; font-weight: 600; "
                f"background: #052E16; border-radius: 4px; padding: 2px 8px;"
            )
        else:
            self._network_pill.setText("QKD  Offline")
            self._network_pill.setStyleSheet(
                f"color: {_C['offline']}; font-size: 11px; font-weight: 600; "
                f"background: #2D0E0E; border-radius: 4px; padding: 2px 8px;"
            )

        # Level pill
        icon  = _TQR_ICONS.get(session.tqr_level, "🔐")
        label = _TQR_LABELS.get(session.tqr_level, f"Level {session.tqr_level}")
        self._level_pill.setText(f"{icon}  {label}")
        self._level_pill.setStyleSheet(
            f"color: {_C['accent_light']}; font-size: 11px; "
            f"background: {_C['accent_muted']}; border-radius: 4px; padding: 2px 8px;"
        )

        # Account
        self._account_label.setText(session.active_account or "Not signed in")
