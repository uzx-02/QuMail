"""
Security Badge & Trust Presentation Component.

Provides consistent, consumer-friendly security indicator widgets for:
- Message list items (compact pill / badge)
- Reading pane message headers (expanded card with explanation and advice)
- Compose window (live recipient trust verification indicator)

Consumes the established SecurityIndicator contract from core/security_indicators.py.
Zero cryptographic friction: displays plain-language corporate trust state,
never exposing raw hexadecimal keys or algorithm parameters to non-technical users.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
    QFrame,
)

from core.security_indicators import BadgeLevel, IndicatorCode, SecurityIndicator
from ui.design_system import C


BADGE_COLORS: dict[BadgeLevel, dict[str, str]] = {
    BadgeLevel.SECURE: {
        "fg": "#22C55E",
        "bg": "#052E16",
        "border": "#166534",
        "icon": "🔒",
        "label": "Verified and secure",
    },
    BadgeLevel.CAUTION: {
        "fg": "#F59E0B",
        "bg": "#2D1B00",
        "border": "#78350F",
        "icon": "⚠️",
        "label": "Encrypted, identity unverified",
    },
    BadgeLevel.ALERT: {
        "fg": "#EF4444",
        "bg": "#450A0A",
        "border": "#991B1B",
        "icon": "❌",
        "label": "Security verification failed",
    },
    BadgeLevel.NEUTRAL: {
        "fg": "#8B949E",
        "bg": "#161B22",
        "border": "#30363D",
        "icon": "ℹ️",
        "label": "Standard email",
    },
}


class SecurityPill(QFrame):
    """
    Compact pill badge used in message list rows and compact headers.
    """

    def __init__(self, indicator: SecurityIndicator | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(6, 2, 6, 2)
        self._layout.setSpacing(4)

        self._icon_lbl = QLabel()
        self._text_lbl = QLabel()
        self._text_lbl.setStyleSheet("font-size: 11px; font-weight: 600;")

        self._layout.addWidget(self._icon_lbl)
        self._layout.addWidget(self._text_lbl)

        if indicator:
            self.set_indicator(indicator)
        else:
            self.set_indicator(SecurityIndicator.verification_unavailable())

    def set_indicator(self, indicator: SecurityIndicator) -> None:
        self.indicator = indicator
        colors = BADGE_COLORS.get(indicator.badge_level, BADGE_COLORS[BadgeLevel.NEUTRAL])

        # Short summary label for compact pill
        if indicator.badge_level == BadgeLevel.SECURE:
            label_text = "Verified Secure"
        elif indicator.badge_level == BadgeLevel.CAUTION:
            label_text = "Encrypted"
        elif indicator.badge_level == BadgeLevel.ALERT:
            label_text = "Security Alert"
        elif indicator.code == IndicatorCode.EXTERNAL_CORRESPONDENT:
            label_text = "External"
        else:
            label_text = "Standard"

        self._icon_lbl.setText(colors["icon"])
        self._text_lbl.setText(label_text)
        self._text_lbl.setStyleSheet(f"color: {colors['fg']}; font-size: 11px; font-weight: 600;")
        self.setStyleSheet(
            f"QFrame {{ background-color: {colors['bg']}; border: 1px solid {colors['border']}; border-radius: 10px; }}"
        )
        self.setToolTip(f"{indicator.headline}\n{indicator.description}\n\nAdvice: {indicator.action_advice}")


class SecurityBanner(QFrame):
    """
    Expanded security header card used at the top of the reading pane.
    Presents the headline, full description, and actionable guidance clearly.
    """

    def __init__(self, indicator: SecurityIndicator | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # Top row: Icon + Headline + Level Badge
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.icon_label = QLabel()
        self.icon_label.setStyleSheet("font-size: 16px;")
        top_row.addWidget(self.icon_label)

        self.headline_label = QLabel()
        self.headline_label.setStyleSheet("font-size: 13px; font-weight: 700;")
        top_row.addWidget(self.headline_label)

        top_row.addStretch()

        self.level_badge = QLabel()
        self.level_badge.setStyleSheet("font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 3px;")
        top_row.addWidget(self.level_badge)

        layout.addLayout(top_row)

        # Description text
        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("font-size: 12px; line-height: 1.4;")
        layout.addWidget(self.desc_label)

        # Action advice text
        self.advice_label = QLabel()
        self.advice_label.setWordWrap(True)
        self.advice_label.setStyleSheet("font-size: 11px; font-style: italic; opacity: 0.9;")
        layout.addWidget(self.advice_label)

        if indicator:
            self.set_indicator(indicator)
        else:
            self.set_indicator(SecurityIndicator.verification_unavailable())

    def set_indicator(self, indicator: SecurityIndicator) -> None:
        self.indicator = indicator
        colors = BADGE_COLORS.get(indicator.badge_level, BADGE_COLORS[BadgeLevel.NEUTRAL])

        self.icon_label.setText(colors["icon"])
        self.headline_label.setText(indicator.headline)
        self.headline_label.setStyleSheet(f"color: {colors['fg']}; font-size: 13px; font-weight: 700;")

        self.level_badge.setText(indicator.badge_level.value.upper())
        self.level_badge.setStyleSheet(
            f"color: {colors['fg']}; background-color: {colors['bg']}; border: 1px solid {colors['border']}; "
            f"font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 4px;"
        )

        self.desc_label.setText(indicator.description)
        self.desc_label.setStyleSheet(f"color: {C['text_primary']}; font-size: 12px;")

        self.advice_label.setText(f"Advice: {indicator.action_advice}")
        self.advice_label.setStyleSheet(f"color: {C['text_secondary']}; font-size: 11px; font-style: italic;")

        self.setStyleSheet(
            f"SecurityBanner {{ background-color: {colors['bg']}; border: 1px solid {colors['border']}; border-radius: 8px; }}"
        )
