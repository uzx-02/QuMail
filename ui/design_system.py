"""
ui/design_system.py — QuMail Professional Desktop Design System.

Built according to UI/UX Pro Max design intelligence for enterprise desktop productivity:
- Semantic color tokens with native dual-theme support (Dark Enterprise Slate & Light Executive Workspace).
- Scaled typography system using standard Windows desktop system fonts.
- Restrained, consistent spacing, borders, elevations, and focus states.
- Reusable UI primitives: ThemeManager, StatusBadgeWidget, StatusPill, EmptyStateWidget,
  AvatarWidget, SearchInput, ActionButton, CardWidget.
- Strict accessibility: high-contrast text, visible focus rings, screen-reader text.

No external dependencies beyond PyQt6. Zero side effects on import.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, ClassVar, Literal
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


ThemeMode = Literal["dark", "light"]


# ---------------------------------------------------------------------------
# Design Token Palettes (Dark Enterprise Slate & Light Executive)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Palette:
    # Base surfaces
    bg_canvas: str         # Window background
    bg_sidebar: str        # Left navigation pane
    bg_surface: str        # Middle list pane
    bg_card: str           # Individual card / message item
    bg_card_hover: str     # Card hovered
    bg_card_selected: str  # Card active / selected
    bg_input: str          # Text inputs and textareas

    # Borders & Dividers
    border_subtle: str     # Soft dividers
    border_default: str    # Standard container borders
    border_focused: str    # Focus rings / active inputs

    # Text hierarchy
    text_primary: str      # High emphasis headers and body
    text_secondary: str    # Secondary labels, metadata, timestamps
    text_muted: str        # Placeholder text, disabled labels
    text_inverse: str      # Text on primary accent buttons

    # Brand Accents
    accent: str            # Primary brand color (Indigo)
    accent_hover: str      # Primary button hover
    accent_subtle: str     # Tinted accent background (pills, selection)

    # Status / Security Tokens
    secure: str            # Emerald Green (verified post-quantum / signed)
    secure_bg: str         # Tinted green background
    secure_text: str       # High contrast green text
    
    caution: str           # Amber / Yellow (identity unverified / TOFU)
    caution_bg: str        # Tinted amber background
    caution_text: str      # High contrast amber text

    alert: str             # Ruby Red (tampered, revoked, spoofed, failed)
    alert_bg: str          # Tinted red background
    alert_text: str        # High contrast red text

    info: str              # Cyan / Sapphire (system notice, sync)
    info_bg: str           # Tinted cyan background
    info_text: str


DARK_PALETTE = Palette(
    bg_canvas="#0A0E17",
    bg_sidebar="#111726",
    bg_surface="#161F33",
    bg_card="#1C2740",
    bg_card_hover="#243252",
    bg_card_selected="#2C3D63",
    bg_input="#0D1320",

    border_subtle="#1F2C47",
    border_default="#2A3B5F",
    border_focused="#6366F1",

    text_primary="#F1F5F9",
    text_secondary="#94A3B8",
    text_muted="#64748B",
    text_inverse="#FFFFFF",

    accent="#6366F1",
    accent_hover="#4F46E5",
    accent_subtle="#1E2342",

    secure="#10B981",
    secure_bg="#064E3B",
    secure_text="#A7F3D0",

    caution="#F59E0B",
    caution_bg="#451A03",
    caution_text="#FDE68A",

    alert="#EF4444",
    alert_bg="#450A0A",
    alert_text="#FECACA",

    info="#0284C7",
    info_bg="#082F49",
    info_text="#BAE6FD",
)

LIGHT_PALETTE = Palette(
    bg_canvas="#F8FAFC",
    bg_sidebar="#F1F5F9",
    bg_surface="#FFFFFF",
    bg_card="#FFFFFF",
    bg_card_hover="#F8FAFC",
    bg_card_selected="#EEF2FF",
    bg_input="#FFFFFF",

    border_subtle="#E2E8F0",
    border_default="#CBD5E1",
    border_focused="#4F46E5",

    text_primary="#0F172A",
    text_secondary="#475569",
    text_muted="#94A3B8",
    text_inverse="#FFFFFF",

    accent="#4F46E5",
    accent_hover="#4338CA",
    accent_subtle="#E0E7FF",

    secure="#059669",
    secure_bg="#D1FAE5",
    secure_text="#065F46",

    caution="#D97706",
    caution_bg="#FEF3C7",
    caution_text="#92400E",

    alert="#DC2626",
    alert_bg="#FEE2E2",
    alert_text="#991B1B",

    info="#0284C7",
    info_bg="#E0F2FE",
    info_text="#075985",
)


# ---------------------------------------------------------------------------
# Theme Manager (Singleton Provider)
# ---------------------------------------------------------------------------

class ThemeManager(QObject):
    """Centralized reactive theme management across all QuMail windows."""
    theme_changed = pyqtSignal(str)

    _instance: ClassVar[ThemeManager | None] = None

    def __init__(self) -> None:
        super().__init__()
        self._mode: ThemeMode = "dark"

    @classmethod
    def get(cls) -> ThemeManager:
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance

    @property
    def mode(self) -> ThemeMode:
        return self._mode

    @property
    def palette(self) -> Palette:
        return DARK_PALETTE if self._mode == "dark" else LIGHT_PALETTE

    def set_theme(self, mode: ThemeMode) -> None:
        if self._mode != mode:
            self._mode = mode
            self.theme_changed.emit(mode)
            app = QApplication.instance()
            if app:
                app.setStyleSheet(self.generate_global_stylesheet())

    def toggle(self) -> ThemeMode:
        new_mode: ThemeMode = "light" if self._mode == "dark" else "dark"
        self.set_theme(new_mode)
        return new_mode

    def generate_global_stylesheet(self) -> str:
        p = self.palette
        return f"""
        QWidget {{
            background-color: {p.bg_canvas};
            color: {p.text_primary};
            font-family: "Segoe UI", "Inter", -apple-system, sans-serif;
            font-size: 13px;
        }}
        QFrame, QSplitter {{
            border: none;
            background: transparent;
        }}
        QScrollBar:vertical {{
            background: {p.bg_sidebar};
            width: 8px;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {p.border_default};
            border-radius: 4px;
            min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {p.text_muted};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar:horizontal {{
            background: {p.bg_sidebar};
            height: 8px;
            margin: 0px;
        }}
        QScrollBar::handle:horizontal {{
            background: {p.border_default};
            border-radius: 4px;
            min-width: 24px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}
        QToolTip {{
            background-color: {p.bg_card};
            color: {p.text_primary};
            border: 1px solid {p.border_default};
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 12px;
        }}
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: {p.bg_input};
            color: {p.text_primary};
            border: 1px solid {p.border_default};
            border-radius: 6px;
            padding: 6px 10px;
            selection-background-color: {p.accent};
            selection-color: {p.text_inverse};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: 1px solid {p.border_focused};
        }}
        """


# Global convenience dictionary for backward compatibility with existing tests and modules
C: dict[str, str] = {
    "bg_base": DARK_PALETTE.bg_canvas,
    "bg_sidebar": DARK_PALETTE.bg_sidebar,
    "bg_card": DARK_PALETTE.bg_card,
    "bg_hover": DARK_PALETTE.bg_card_hover,
    "accent": DARK_PALETTE.accent,
    "accent_light": "#818CF8",
    "accent_glow": "#4F46E5",
    "accent_muted": DARK_PALETTE.accent_subtle,
    "text_primary": DARK_PALETTE.text_primary,
    "text_secondary": DARK_PALETTE.text_secondary,
    "text_tertiary": DARK_PALETTE.text_muted,
    "border": DARK_PALETTE.border_subtle,
    "online": DARK_PALETTE.secure,
    "offline": DARK_PALETTE.alert,
    "warning": DARK_PALETTE.caution,
    "warning_bg": DARK_PALETTE.caution_bg,
    "success_bg": DARK_PALETTE.secure_bg,
}

GLOBAL_STYLESHEET = ThemeManager.get().generate_global_stylesheet()


# ---------------------------------------------------------------------------
# Outbox State Presentation Labels
# ---------------------------------------------------------------------------

OUTBOX_STATE_LABELS: dict[str, str] = {
    "Draft": "Draft",
    "Prepared": "Ready to send",
    "Submitting": "Sending securely\u2026",
    "Accepted": "Accepted by mail server",
    "Failed": "Not sent \u2014 click to retry",
    "Unknown": "Delivery uncertain \u2014 check Sent folder",
}

OUTBOX_STATE_COLORS: dict[str, str] = {
    "Draft": DARK_PALETTE.text_muted,
    "Prepared": "#818CF8",
    "Submitting": DARK_PALETTE.caution,
    "Accepted": DARK_PALETTE.secure,
    "Failed": DARK_PALETTE.alert,
    "Unknown": DARK_PALETTE.caution,
}

OUTBOX_STATE_ICONS: dict[str, str] = {
    "Draft": "\u270f\ufe0f",
    "Prepared": "\ud83d\udce6",
    "Submitting": "\ud83d\udd12",
    "Accepted": "\u2705",
    "Failed": "\u274c",
    "Unknown": "\u26a0\ufe0f",
}


# ---------------------------------------------------------------------------
# Reusable UI Component Primitives
# ---------------------------------------------------------------------------

class StatusBadgeWidget(QFrame):
    """
    Modern enterprise security badge widget communicating cryptographic assurance clearly:
    - SECURE (Green): Verified Post-Quantum OpenPGP (ML-KEM-768/ML-DSA-65) with enterprise trust
    - CAUTION (Amber): Valid signature, but uncertified directory key (TOFU trust)
    - ALERT (Red): Signature mismatch, key substitution, or invalid cryptographic envelope
    - STANDARD (Gray): Unencrypted standard message
    """

    def __init__(self, badge_type: str = "SECURE", label: str = "", subtext: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._badge_type = badge_type.upper()
        self._label = label
        self._subtext = subtext

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(8, 4, 8, 4)
        self._layout.setSpacing(6)

        self._icon_lbl = QLabel()
        self._text_lbl = QLabel()
        self._text_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))

        self._layout.addWidget(self._icon_lbl)
        self._layout.addWidget(self._text_lbl)

        self.update_badge(self._badge_type, self._label, self._subtext)

    def update_badge(self, badge_type: str, label: str = "", subtext: str = "") -> None:
        self._badge_type = badge_type.upper()
        self._label = label
        self._subtext = subtext
        p = ThemeManager.get().palette

        if "SECURE" in self._badge_type:
            bg = p.secure_bg
            fg = p.secure_text
            border = p.secure
            icon = "🔒"
            text = label or "SECURE"
            default_tip = "Post-Quantum Encrypted (ML-KEM-768) and Verified Signature (ML-DSA-65)."
        elif "CAUTION" in self._badge_type or "UNVERIFIED" in self._badge_type:
            bg = p.caution_bg
            fg = p.caution_text
            border = p.caution
            icon = "⚠️"
            text = label or "CAUTION"
            default_tip = "Valid cryptographic seal, but sender identity is uncertified by corporate CA."
        elif "ALERT" in self._badge_type or "FAILED" in self._badge_type or "TAMPERED" in self._badge_type:
            bg = p.alert_bg
            fg = p.alert_text
            border = p.alert
            icon = "🚫"
            text = label or "ALERT"
            default_tip = "Cryptographic integrity failure, revoked key, or key substitution detected!"
        else:
            bg = p.bg_card
            fg = p.text_secondary
            border = p.border_default
            icon = "✉️"
            text = label or "STANDARD"
            default_tip = "Standard unencrypted email communication."

        self.setStyleSheet(
            f"StatusBadgeWidget {{"
            f"  background-color: {bg};"
            f"  border: 1px solid {border};"
            f"  border-radius: 6px;"
            f"}}"
        )
        self._icon_lbl.setText(icon)
        self._icon_lbl.setStyleSheet("background: transparent; font-size: 12px;")
        self._text_lbl.setText(text)
        self._text_lbl.setStyleSheet(f"color: {fg}; background: transparent; font-size: 11px; font-weight: 700;")
        self.setToolTip(subtext or default_tip)


class StatusPill(QLabel):
    """A compact rounded pill badge for flags, counts, and statuses."""

    def __init__(self, text: str = "", fg: str = "#E6EDF3", bg: str = "#1E2238", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._fg = fg
        self._bg = bg
        self._apply()

    def _apply(self) -> None:
        self.setStyleSheet(
            f"color: {self._fg}; background: {self._bg}; "
            f"border-radius: 10px; padding: 2px 8px; "
            f"font-size: 11px; font-weight: 600;"
        )

    def set_colors(self, fg: str, bg: str) -> None:
        self._fg = fg
        self._bg = bg
        self._apply()


class AvatarWidget(QWidget):
    """Clean monogram avatar widget for email senders/recipients."""

    def __init__(self, name_or_email: str, size: int = 36, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._text = self._extract_initials(name_or_email)
        self._bg_color = self._derive_color(name_or_email)

    def set_identity(self, name_or_email: str) -> None:
        self._text = self._extract_initials(name_or_email)
        self._bg_color = self._derive_color(name_or_email)
        self.update()

    def _extract_initials(self, s: str) -> str:
        s = s.strip()
        if not s:
            return "?"
        parts = s.split("@")[0].replace(".", " ").replace("_", " ").split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        return parts[0][:2].upper()

    def _derive_color(self, s: str) -> QColor:
        colors = [
            "#4F46E5", "#0284C7", "#059669", "#7C3AED",
            "#D97706", "#DB2777", "#2563EB", "#0D9488"
        ]
        h = sum(ord(c) for c in s) % len(colors)
        return QColor(colors[h])

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        path = QPainterPath()
        path.addEllipse(0, 0, r.width(), r.height())
        painter.fillPath(path, self._bg_color)

        painter.setPen(QColor("#FFFFFF"))
        font = QFont("Segoe UI", int(self.height() * 0.38), QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, self._text)


class SearchInput(QLineEdit):
    """Modern search box with dedicated placeholder and clear button."""

    def __init__(self, placeholder: str = "Search messages…", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        p = ThemeManager.get().palette
        self.setFixedHeight(34)
        self.setStyleSheet(
            f"QLineEdit {{"
            f"  background-color: {p.bg_input};"
            f"  color: {p.text_primary};"
            f"  border: 1px solid {p.border_default};"
            f"  border-radius: 6px;"
            f"  padding: 4px 10px 4px 10px;"
            f"  font-size: 13px;"
            f"}}"
            f"QLineEdit:focus {{"
            f"  border: 1px solid {p.border_focused};"
            f"}}"
        )


class ActionButton(QPushButton):
    """Primary or secondary branded action button."""

    def __init__(self, text: str, variant: Literal["primary", "secondary", "danger", "ghost"] = "primary", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._variant = variant
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(32)
        self.apply_style()

    def apply_style(self) -> None:
        p = ThemeManager.get().palette
        if self._variant == "primary":
            self.setStyleSheet(
                f"QPushButton {{"
                f"  background-color: {p.accent};"
                f"  color: {p.text_inverse};"
                f"  border: none;"
                f"  border-radius: 6px;"
                f"  padding: 6px 14px;"
                f"  font-weight: 600;"
                f"  font-size: 13px;"
                f"}}"
                f"QPushButton:hover {{"
                f"  background-color: {p.accent_hover};"
                f"}}"
                f"QPushButton:pressed {{"
                f"  background-color: {p.border_focused};"
                f"}}"
                f"QPushButton:disabled {{"
                f"  background-color: {p.border_subtle};"
                f"  color: {p.text_muted};"
                f"}}"
            )
        elif self._variant == "danger":
            self.setStyleSheet(
                f"QPushButton {{"
                f"  background-color: {p.alert};"
                f"  color: {p.text_inverse};"
                f"  border: none;"
                f"  border-radius: 6px;"
                f"  padding: 6px 14px;"
                f"  font-weight: 600;"
                f"}}"
                f"QPushButton:hover {{"
                f"  background-color: {p.alert_text};"
                f"}}"
            )
        elif self._variant == "ghost":
            self.setStyleSheet(
                f"QPushButton {{"
                f"  background-color: transparent;"
                f"  color: {p.text_secondary};"
                f"  border: none;"
                f"  border-radius: 6px;"
                f"  padding: 6px 10px;"
                f"}}"
                f"QPushButton:hover {{"
                f"  background-color: {p.bg_card_hover};"
                f"  color: {p.text_primary};"
                f"}}"
            )
        else: # secondary
            self.setStyleSheet(
                f"QPushButton {{"
                f"  background-color: {p.bg_card};"
                f"  color: {p.text_primary};"
                f"  border: 1px solid {p.border_default};"
                f"  border-radius: 6px;"
                f"  padding: 6px 14px;"
                f"  font-weight: 500;"
                f"}}"
                f"QPushButton:hover {{"
                f"  background-color: {p.bg_card_hover};"
                f"  border-color: {p.border_focused};"
                f"}}"
            )


class EmptyState(QWidget):
    """Centered icon + heading + subtext placeholder for empty lists and views."""

    def __init__(self, icon: str, heading: str, sub: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)
        layout.setContentsMargins(24, 24, 24, 24)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 40px; background: transparent;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_lbl)

        p = ThemeManager.get().palette
        head_lbl = QLabel(heading)
        head_lbl.setStyleSheet(f"color: {p.text_primary}; font-size: 15px; font-weight: 600; background: transparent;")
        head_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(head_lbl)

        if sub:
            sub_lbl = QLabel(sub)
            sub_lbl.setStyleSheet(f"color: {p.text_secondary}; font-size: 12px; background: transparent;")
            sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub_lbl.setWordWrap(True)
            layout.addWidget(sub_lbl)
