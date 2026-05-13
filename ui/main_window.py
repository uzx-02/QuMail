# ui/main_window.py — Application shell and top-level navigation host.
# Single responsibility: construct the main window frame, host the navigation
# sidebar, manage the central stacked view, embed KeyStatusWidget, and own
# the light/dark theme toggle. No business logic lives here.
# Do not import from crypto/, transport/, kme/, or certificates/ directly.

from PyQt6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, QRect, pyqtProperty
from PyQt6.QtGui import QFont, QIcon, QColor, QPainter, QPainterPath, QLinearGradient
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QScrollArea,
)

from core.config import APP_NAME, APP_VERSION
from core.session import session
from ui.key_status_widget import KeyStatusWidget


# ---------------------------------------------------------------------------
# Design Tokens
# ---------------------------------------------------------------------------

_C = {
    # Surface layers
    "bg_base":       "#0D1117",
    "bg_sidebar":    "#161B22",
    "bg_card":       "#1C2231",
    "bg_hover":      "#21293A",

    # Accent
    "accent":        "#6366F1",      # Indigo-500
    "accent_light":  "#818CF8",      # Indigo-400
    "accent_glow":   "#4F46E5",      # Indigo-600 (deeper)
    "accent_muted":  "#1E2238",      # subtle accent bg for selections

    # Text
    "text_primary":  "#E6EDF3",
    "text_secondary":"#8B949E",
    "text_tertiary": "#484F58",

    # Border / divider
    "border":        "#21262D",
    "border_accent": "#6366F1",

    # Status
    "online":        "#22C55E",
    "offline":       "#EF4444",
    "warning":       "#F59E0B",

    # Security level colours
    "lvl1_fg":       "#D1FAE5",   "lvl1_bg":  "#064E3B",
    "lvl2_fg":       "#DBEAFE",   "lvl2_bg":  "#1E3A5F",
    "lvl3_fg":       "#EDE9FE",   "lvl3_bg":  "#2E1065",
}


# ---------------------------------------------------------------------------
# Global Stylesheet
# ---------------------------------------------------------------------------

_GLOBAL_STYLESHEET = f"""
/* ── Base ─────────────────────────────────────────────────── */
QMainWindow, QWidget {{
    background-color: {_C['bg_base']};
    color: {_C['text_primary']};
    font-family: 'Segoe UI', 'Inter', 'Helvetica Neue', sans-serif;
    font-size: 13px;
}}
QScrollBar:vertical {{
    background: {_C['bg_sidebar']};
    width: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {_C['text_tertiary']};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: {_C['bg_sidebar']};
    height: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:horizontal {{
    background: {_C['text_tertiary']};
    border-radius: 3px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── Sidebar ───────────────────────────────────────────────── */
QWidget#sidebar {{
    background-color: {_C['bg_sidebar']};
    border-right: 1px solid {_C['border']};
}}

/* ── Content area ─────────────────────────────────────────── */
QWidget#content_area {{
    background-color: {_C['bg_base']};
}}

/* ── Status bar ───────────────────────────────────────────── */
QWidget#status_bar_container {{
    background-color: {_C['bg_sidebar']};
    border-top: 1px solid {_C['border']};
}}

/* ── Nav buttons ──────────────────────────────────────────── */
QPushButton#nav_btn {{
    text-align: left;
    padding: 9px 16px 9px 16px;
    border: none;
    border-radius: 8px;
    color: {_C['text_secondary']};
    background: transparent;
    font-size: 13px;
}}
QPushButton#nav_btn:hover {{
    background-color: {_C['bg_hover']};
    color: {_C['text_primary']};
}}
QPushButton#nav_btn[active="true"] {{
    background-color: {_C['accent_muted']};
    color: {_C['accent_light']};
    font-weight: 600;
}}

/* ── Compose FAB ──────────────────────────────────────────── */
QPushButton#compose_fab {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {_C['accent']}, stop:1 {_C['accent_glow']});
    color: #FFFFFF;
    border: none;
    border-radius: 10px;
    font-size: 13px;
    font-weight: 600;
    padding: 11px 18px;
    text-align: left;
}}
QPushButton#compose_fab:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {_C['accent_light']}, stop:1 {_C['accent']});
}}
QPushButton#compose_fab:pressed {{
    background-color: {_C['accent_glow']};
}}

/* ── Theme toggle ─────────────────────────────────────────── */
QPushButton#theme_toggle {{
    color: {_C['text_tertiary']};
    background: transparent;
    border: 1px solid {_C['border']};
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 11px;
}}
QPushButton#theme_toggle:hover {{
    color: {_C['text_secondary']};
    border-color: {_C['text_tertiary']};
}}

/* ── Tooltip ──────────────────────────────────────────────── */
QToolTip {{
    background-color: {_C['bg_card']};
    color: {_C['text_primary']};
    border: 1px solid {_C['border']};
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}}
"""


# ---------------------------------------------------------------------------
# Nav item definitions  (label, icon-glyph, view-index, tooltip)
# ---------------------------------------------------------------------------

_NAV_ITEMS: list[tuple[str, str, int, str]] = [
    ("Inbox",    "⬛",  0, "View your encrypted inbox"),
    ("Compose",  "⬛",  1, "Compose a new secure message"),
    ("Settings", "⬛",  2, "Account and security settings"),
]

# Better Unicode icon set — works without external icon pack
_NAV_ICONS = ["  📥", "  ✏️", "  ⚙️"]


# ---------------------------------------------------------------------------
# Logo / Brand widget
# ---------------------------------------------------------------------------

class _BrandWidget(QWidget):
    """
    Sidebar brand block: a painted gradient shield glyph + wordmark + version.
    No external image files required.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(72)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Shield background pill
        sx, sy, sw, sh = 16, 18, 36, 36
        grad = QLinearGradient(float(sx), float(sy), float(sx + sw), float(sy + sh))
        grad.setColorAt(0, QColor("#6366F1"))
        grad.setColorAt(1, QColor("#4F46E5"))
        path = QPainterPath()
        path.addRoundedRect(sx, sy, sw, sh, 9, 9)
        painter.fillPath(path, grad)

        # Shield letter "Q"
        painter.setPen(QColor("#FFFFFF"))
        font = painter.font()
        font.setPointSize(17)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(sx, sy, sw, sh, Qt.AlignmentFlag.AlignCenter, "Q")

        # Wordmark
        painter.setPen(QColor(_C["text_primary"]))
        wf = painter.font()
        wf.setPointSize(14)
        wf.setBold(True)
        painter.setFont(wf)
        painter.drawText(60, 18, 140, 22, Qt.AlignmentFlag.AlignVCenter, APP_NAME)

        # Version tag
        painter.setPen(QColor(_C["text_tertiary"]))
        vf = painter.font()
        vf.setPointSize(9)
        vf.setBold(False)
        painter.setFont(vf)
        painter.drawText(61, 40, 140, 16, Qt.AlignmentFlag.AlignVCenter, f"v{APP_VERSION}")


# ---------------------------------------------------------------------------
# Avatar widget (initials circle)
# ---------------------------------------------------------------------------

class _AvatarWidget(QWidget):
    """Small circle showing the first initial of the signed-in account."""

    _SIZE = 34

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(self._SIZE, self._SIZE)
        self._initial = "?"
        self._online  = False

    def update_state(self, email: str | None, online: bool) -> None:
        self._initial = (email or "?")[0].upper()
        self._online  = online
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Circle background — gradient
        grad = QLinearGradient(0.0, 0.0, float(self._SIZE), float(self._SIZE))
        grad.setColorAt(0, QColor("#6366F1"))
        grad.setColorAt(1, QColor("#2563EB"))
        path = QPainterPath()
        path.addEllipse(0, 0, self._SIZE, self._SIZE)
        p.fillPath(path, grad)

        # Initial letter
        p.setPen(QColor("#FFFFFF"))
        f = p.font()
        f.setPointSize(13)
        f.setBold(True)
        p.setFont(f)
        p.drawText(0, 0, self._SIZE, self._SIZE, Qt.AlignmentFlag.AlignCenter, self._initial)

        # Small status dot
        dot_size = 8
        dot_x = self._SIZE - dot_size
        dot_y = self._SIZE - dot_size
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(_C["bg_sidebar"]))
        p.drawEllipse(dot_x - 1, dot_y - 1, dot_size + 2, dot_size + 2)
        p.setBrush(QColor(_C["online"] if self._online else _C["offline"]))
        p.drawEllipse(dot_x, dot_y, dot_size, dot_size)


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """
    Top-level application shell for QuMail.

    Layout:
      ┌─────────────────┬──────────────────────────────────────┐
      │  Sidebar (220)  │  Content area (stacked views)        │
      │  - Brand mark   │  [Inbox / Compose / Settings]        │
      │  - Avatar+acct  │                                      │
      │  - Nav buttons  │                                      │
      │  - Compose FAB  │                                      │
      │  - Theme toggle │                                      │
      ├─────────────────┴──────────────────────────────────────┤
      │  KeyStatusWidget (full width, 40px)                    │
      └────────────────────────────────────────────────────────┘
    """

    def __init__(self) -> None:
        super().__init__()
        self._nav_buttons: list[QPushButton] = []

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1100, 680)
        self.resize(1280, 760)

        self._build_ui()
        QApplication.instance().setStyleSheet(_GLOBAL_STYLESHEET)
        self._switch_view(0)

    # --- UI Construction ---

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("central_widget")
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        main_row = QHBoxLayout()
        main_row.setContentsMargins(0, 0, 0, 0)
        main_row.setSpacing(0)
        main_row.addWidget(self._build_sidebar())
        main_row.addWidget(self._build_content_area(), stretch=1)

        outer.addLayout(main_row, stretch=1)
        outer.addWidget(self._build_status_bar())

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 0, 12, 14)
        layout.setSpacing(0)

        # Brand
        brand = _BrandWidget(sidebar)
        layout.addWidget(brand)

        # Account chip
        account_row = QHBoxLayout()
        account_row.setContentsMargins(4, 4, 4, 12)
        account_row.setSpacing(10)
        self._avatar = _AvatarWidget()
        self._avatar.update_state(session.active_account, session.kme_connected)

        self._account_label = QLabel(session.active_account or "Not signed in")
        self._account_label.setStyleSheet(
            f"color: {_C['text_secondary']}; font-size: 11px;"
        )
        self._account_label.setWordWrap(False)
        self._account_label.setMaximumWidth(140)

        account_row.addWidget(self._avatar)
        account_row.addWidget(self._account_label, stretch=1)
        layout.addLayout(account_row)

        # Divider
        div = QWidget()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background-color: {_C['border']};")
        layout.addWidget(div)
        layout.addSpacing(8)

        # Compose FAB
        compose_fab = QPushButton("  ✏️  New Message")
        compose_fab.setObjectName("compose_fab")
        compose_fab.setCursor(Qt.CursorShape.PointingHandCursor)
        compose_fab.setFixedHeight(40)
        compose_fab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        compose_fab.clicked.connect(lambda: self._switch_view(1))
        layout.addWidget(compose_fab)
        layout.addSpacing(12)

        # Nav items
        icons = ["  📥", "  ✏️", "  ⚙️"]
        labels = ["Inbox", "Compose", "Settings"]
        tooltips = ["View encrypted inbox", "Compose secure message", "Account & settings"]
        for i, (icon, label, tip) in enumerate(zip(icons, labels, tooltips)):
            btn = QPushButton(f"{icon}   {label}")
            btn.setObjectName("nav_btn")
            btn.setCheckable(False)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setFixedHeight(38)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda checked, idx=i: self._switch_view(idx))
            self._nav_buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

        # Divider above bottom controls
        div2 = QWidget()
        div2.setFixedHeight(1)
        div2.setStyleSheet(f"background-color: {_C['border']};")
        layout.addWidget(div2)
        layout.addSpacing(10)

        self._theme_btn = QPushButton("☀️   Light Mode")
        self._theme_btn.setObjectName("theme_toggle")
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_btn.clicked.connect(self._toggle_theme)
        layout.addWidget(self._theme_btn)

        self._dark_mode = True   # We are dark by default
        return sidebar

    def _build_content_area(self) -> QWidget:
        container = QWidget()
        container.setObjectName("content_area")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        from ui.inbox_view import InboxView
        from ui.compose_window import ComposeWindow
        from ui.settings_window import SettingsWindow

        self._inbox_view    = InboxView()
        self._compose_view  = ComposeWindow()
        self._settings_view = SettingsWindow()

        self._stack.addWidget(self._inbox_view)    # 0
        self._stack.addWidget(self._compose_view)  # 1
        self._stack.addWidget(self._settings_view) # 2

        return container

    def _build_status_bar(self) -> QWidget:
        container = QWidget()
        container.setObjectName("status_bar_container")
        container.setFixedHeight(40)

        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._status_widget = KeyStatusWidget(container)
        layout.addWidget(self._status_widget)

        return container

    # --- Navigation ---

    def _switch_view(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.setProperty("active", "true" if i == index else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        # Refresh avatar whenever the view changes (account may have just connected)
        self._avatar.update_state(session.active_account, session.kme_connected)
        self._account_label.setText(session.active_account or "Not signed in")

    # --- Theming ---

    def _toggle_theme(self) -> None:
        self._dark_mode = not self._dark_mode
        self._apply_dark_overlay() if self._dark_mode else self._apply_light_overlay()

    def _apply_dark_overlay(self) -> None:
        """Restore the default dark enterprise theme (no-op since it is the global default)."""
        QApplication.instance().setStyleSheet(_GLOBAL_STYLESHEET)
        self._theme_btn.setText("☀️   Light Mode")

    def _apply_light_overlay(self) -> None:
        """Switch to a light theme by patching key colour tokens."""
        light = _GLOBAL_STYLESHEET.replace(
            _C["bg_base"], "#F4F6F9"
        ).replace(
            _C["bg_sidebar"], "#FFFFFF"
        ).replace(
            _C["bg_card"], "#FFFFFF"
        ).replace(
            _C["bg_hover"], "#F0F2F5"
        ).replace(
            _C["text_primary"], "#111827"
        ).replace(
            _C["text_secondary"], "#4B5563"
        ).replace(
            _C["text_tertiary"], "#9CA3AF"
        ).replace(
            _C["border"], "#E5E7EB"
        ).replace(
            _C["accent_muted"], "#EFF6FF"
        )
        QApplication.instance().setStyleSheet(light)
        self._theme_btn.setText("🌙   Dark Mode")

    # --- Public API ---

    def navigate_to_compose(self) -> None:
        self._switch_view(1)

    def refresh_status(self) -> None:
        self._status_widget.refresh()
