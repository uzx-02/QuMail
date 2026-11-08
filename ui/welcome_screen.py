"""
Welcome / first-run screen for QuMail.

Shown when the application is launched without a vault or when no account is
enrolled. Guides the user to open Settings to create a vault and connect their
Google account. This screen is presentation-only: it does not create a vault,
access credentials, or perform any OAuth or network operations.
"""

from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)
from ui.design_system import C, GLOBAL_STYLESHEET


# ---------------------------------------------------------------------------
# Brand shield (Q logo) — same paint logic as main_window._BrandWidget
# ---------------------------------------------------------------------------

class _ShieldLogo(QWidget):
    """Painted QuMail 'Q' shield — no pixmap required."""

    def __init__(self, size: int = 72, parent: QWidget | None = None) -> None:
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
        f.setPointSize(int(s * 0.36))
        f.setBold(True)
        p.setFont(f)
        p.drawText(0, 0, s, s, Qt.AlignmentFlag.AlignCenter, "Q")


# ---------------------------------------------------------------------------
# Welcome screen
# ---------------------------------------------------------------------------

class WelcomeScreen(QWidget):
    """
    First-run / no-account welcome screen.

    Signals:
        (none) — the screen instructs the user to open Settings via the
        provided button, which calls open_settings_callback.
    """

    def __init__(self, open_settings_callback, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._open_settings = open_settings_callback
        self.setStyleSheet(GLOBAL_STYLESHEET)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Centred card container
        card = QWidget()
        card.setMaximumWidth(560)
        card.setStyleSheet(
            f"background-color: {C['bg_card']}; "
            f"border: 1px solid {C['border']}; "
            f"border-radius: 16px;"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(48, 48, 48, 48)
        card_layout.setSpacing(0)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # Shield logo
        logo = _ShieldLogo(size=72)
        logo_row = QHBoxLayout()
        logo_row.addStretch()
        logo_row.addWidget(logo)
        logo_row.addStretch()
        card_layout.addLayout(logo_row)
        card_layout.addSpacing(24)

        # App name
        name_lbl = QLabel("QuMail")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet(
            f"color: {C['text_primary']}; font-size: 28px; font-weight: 700; background: transparent; border: none;"
        )
        card_layout.addWidget(name_lbl)
        card_layout.addSpacing(8)

        # Tagline
        tag_lbl = QLabel("Secure · Encrypted · Private")
        tag_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tag_lbl.setStyleSheet(
            f"color: {C['accent_light']}; font-size: 13px; font-weight: 500; background: transparent; border: none;"
        )
        card_layout.addWidget(tag_lbl)
        card_layout.addSpacing(32)

        # Security feature chips
        for text in [
            "\U0001f512  End-to-end encrypted using OpenPGP",
            "\U0001f9e0  Post-quantum key protection",
            "\U0001f4dc  Cryptographic delivery receipts",
        ]:
            chip = QLabel(text)
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setStyleSheet(
                f"color: {C['text_secondary']}; font-size: 12px; "
                f"background: {C['bg_hover']}; border-radius: 8px; "
                f"padding: 8px 16px; margin: 3px; border: none;"
            )
            card_layout.addWidget(chip)

        card_layout.addSpacing(32)

        # CTA heading
        cta_lbl = QLabel("Get started")
        cta_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cta_lbl.setStyleSheet(
            f"color: {C['text_primary']}; font-size: 16px; font-weight: 600; background: transparent; border: none;"
        )
        card_layout.addWidget(cta_lbl)
        card_layout.addSpacing(8)

        sub_lbl = QLabel(
            "Open Settings to connect your Google account and create your secure vault."
        )
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl.setWordWrap(True)
        sub_lbl.setStyleSheet(
            f"color: {C['text_secondary']}; font-size: 12px; background: transparent; border: none;"
        )
        card_layout.addWidget(sub_lbl)
        card_layout.addSpacing(24)

        # Settings button
        btn = QPushButton("\u2699\ufe0f  Open Settings")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(48)
        btn.setStyleSheet(
            f"QPushButton {{ color: #FFFFFF; background: {C['accent']}; "
            f"border: none; border-radius: 10px; "
            f"font-size: 14px; font-weight: 700; padding: 0 32px; }} "
            f"QPushButton:hover {{ background: {C['accent_light']}; }}"
        )
        btn.clicked.connect(self._open_settings)
        card_layout.addWidget(btn)
        card_layout.addSpacing(20)

        # Development notice
        dev_note = QLabel(
            "Development build \u2014 Google test-mode authorization only. "
            "Independent security review pending."
        )
        dev_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dev_note.setWordWrap(True)
        dev_note.setStyleSheet(
            f"color: {C['text_tertiary']}; font-size: 10px; background: transparent; border: none;"
        )
        card_layout.addWidget(dev_note)

        # Wrap in a centering row
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(card)
        row.addStretch()
        outer.addStretch()
        outer.addLayout(row)
        outer.addStretch()
