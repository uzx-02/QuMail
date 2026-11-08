"""
Shared design tokens, palette, and reusable widget primitives for QuMail.

All UI modules should import from here rather than duplicating token dicts.
This module has no side effects on import and no external dependencies beyond PyQt6.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient
from PyQt6.QtWidgets import QLabel, QWidget, QHBoxLayout, QVBoxLayout

# ---------------------------------------------------------------------------
# Canonical design tokens
# ---------------------------------------------------------------------------

C: dict[str, str] = {
    "bg_base":        "#0D1117",
    "bg_sidebar":     "#161B22",
    "bg_card":        "#1C2231",
    "bg_hover":       "#21293A",
    "accent":         "#6366F1",
    "accent_light":   "#818CF8",
    "accent_glow":    "#4F46E5",
    "accent_muted":   "#1E2238",
    "text_primary":   "#E6EDF3",
    "text_secondary": "#8B949E",
    "text_tertiary":  "#484F58",
    "border":         "#21262D",
    "online":         "#22C55E",
    "offline":        "#EF4444",
    "warning":        "#F59E0B",
    "warning_bg":     "#2D1B00",
    "success_bg":     "#052E16",
}

# ---------------------------------------------------------------------------
# Outbox state presentation labels (display-only; never change backend enums)
# ---------------------------------------------------------------------------
#
# Backend State enum values: Draft, Prepared, Submitting, Accepted, Failed, Unknown
# These labels are used only for display; the backend state machine is unchanged.

OUTBOX_STATE_LABELS: dict[str, str] = {
    "Draft":       "Draft",
    "Prepared":    "Ready to send",
    "Submitting":  "Sending securely\u2026",
    "Accepted":    "Accepted by mail server",
    "Failed":      "Not sent",
    "Unknown":     "Delivery uncertain \u2014 check Sent folder",
}

OUTBOX_STATE_COLORS: dict[str, str] = {
    "Draft":       C["text_tertiary"],
    "Prepared":    C["accent_light"],
    "Submitting":  C["warning"],
    "Accepted":    C["online"],
    "Failed":      C["offline"],
    "Unknown":     C["warning"],
}

OUTBOX_STATE_ICONS: dict[str, str] = {
    "Draft":       "\u270f\ufe0f",
    "Prepared":    "\ud83d\udce6",
    "Submitting":  "\ud83d\udd12",
    "Accepted":    "\u2705",
    "Failed":      "\u274c",
    "Unknown":     "\u26a0\ufe0f",
}

# ---------------------------------------------------------------------------
# Global stylesheet
# ---------------------------------------------------------------------------

GLOBAL_STYLESHEET = f"""
QWidget {{
    background-color: {C['bg_base']};
    color: {C['text_primary']};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}}
QScrollBar:vertical {{
    background: {C['bg_sidebar']};
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {C['border']};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {C['text_tertiary']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: {C['bg_sidebar']};
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: {C['border']};
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {C['text_tertiary']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QToolTip {{
    background-color: {C['bg_card']};
    color: {C['text_primary']};
    border: 1px solid {C['border']};
    border-radius: 5px;
    padding: 4px 8px;
    font-size: 11px;
}}
"""


# ---------------------------------------------------------------------------
# Reusable widgets
# ---------------------------------------------------------------------------

class StatusPill(QLabel):
    """A small coloured pill label for status badges."""

    def __init__(self, text: str = "", fg: str = "#E6EDF3",
                 bg: str = "#1E2238", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._fg = fg
        self._bg = bg
        self._apply()

    def _apply(self) -> None:
        self.setStyleSheet(
            f"color: {self._fg}; background: {self._bg}; "
            f"border-radius: 5px; padding: 2px 8px; "
            f"font-size: 11px; font-weight: 600;"
        )

    def set_colors(self, fg: str, bg: str) -> None:
        self._fg = fg
        self._bg = bg
        self._apply()


class EmptyState(QWidget):
    """Centered icon + heading + subtext placeholder for empty lists/panes."""

    def __init__(self, icon: str, heading: str, sub: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)
        layout.setContentsMargins(24, 24, 24, 24)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 48px;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_lbl)

        head_lbl = QLabel(heading)
        head_lbl.setStyleSheet(
            f"color: {C['text_secondary']}; font-size: 15px; font-weight: 600;"
        )
        head_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(head_lbl)

        if sub:
            sub_lbl = QLabel(sub)
            sub_lbl.setStyleSheet(
                f"color: {C['text_tertiary']}; font-size: 12px;"
            )
            sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub_lbl.setWordWrap(True)
            layout.addWidget(sub_lbl)
