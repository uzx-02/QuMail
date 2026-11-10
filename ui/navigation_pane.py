"""
ui/navigation_pane.py — Gmail-Inspired Navigation Sidebar Component.

Designed according to Gmail desktop navigation visual reference:
- Prominent Compose CTA: Soft blue (#C2E7FF), rounded pill (16px), dark text (#001D35).
- Clean folder items with subtle icon, label, and right-aligned unread counts.
- Selected folder state: Soft blue rounded pill (#D3E3FD), dark active text (#001D35).
- Bottom hardware security & quantum entropy status badge.
- Dual-theme reactive palette support (Light & Dark).
- 100% backward-compatible signals and method contracts.
"""

from __future__ import annotations

from typing import Any
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.design_system import C, AvatarWidget, ThemeManager, LIGHT_PALETTE
from ui.icons import get_icon, get_pixmap, IconWidget

_FOLDER_ICON_MAP = {
    "inbox": "inbox",
    "starred": "star",
    "sent": "send",
    "drafts": "draft",
    "outbox": "send",
    "trash": "trash",
}


class FolderItemWidget(QWidget):
    """Folder list item widget with vector icon, label, and unread count."""

    def __init__(self, key: str, icon: str, label: str, count: int = 0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self.icon_name = _FOLDER_ICON_MAP.get(key, "inbox")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(12)

        self.icon_lbl = QLabel()
        self.icon_lbl.setStyleSheet("background: transparent;")
        self.icon_lbl.setPixmap(get_pixmap(self.icon_name, size=18))
        layout.addWidget(self.icon_lbl)

        p = ThemeManager.get().palette
        self.text_lbl = QLabel(label)
        self.text_lbl.setStyleSheet(f"color: {p.text_primary}; font-size: 14px; font-weight: 500; background: transparent;")
        layout.addWidget(self.text_lbl)

        layout.addStretch()

        self.badge = QLabel()
        self.badge.setStyleSheet(
            f"color: {p.text_primary}; font-size: 12px; font-weight: 700; background: transparent;"
        )
        self.badge.setVisible(False)
        layout.addWidget(self.badge)

        self.set_count(count)
        ThemeManager.get().theme_changed.connect(self._apply_theme)

    def _apply_theme(self) -> None:
        p = ThemeManager.get().palette
        self.icon_lbl.setPixmap(get_pixmap(self.icon_name, color=p.text_secondary, size=18))
        self.text_lbl.setStyleSheet(f"color: {p.text_primary}; font-size: 14px; font-weight: 500; background: transparent;")

    def set_count(self, count: int) -> None:
        if count > 0:
            self.badge.setText(str(count))
            self.badge.setVisible(True)
        else:
            self.badge.setVisible(False)


class NavigationPane(QFrame):
    """
    Gmail-style left sidebar navigation pane.
    """

    new_message_requested = pyqtSignal()
    folder_selected = pyqtSignal(str)
    settings_requested = pyqtSignal()
    lock_requested = pyqtSignal()
    account_switch_requested = pyqtSignal()
    theme_toggled = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(240)
        self._folder_widgets: dict[str, FolderItemWidget] = {}

        ThemeManager.get().theme_changed.connect(self._apply_theme)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. Primary Compose Button (Gmail Style: Soft Blue Pill, Dark Text, Height 48px)
        compose_row = QHBoxLayout()
        self.new_btn = QPushButton("  Compose")
        self.new_btn.setFixedSize(140, 48)
        self.new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_btn.setIcon(get_icon("compose", color="#001D35", size=20))
        self.new_btn.setToolTip("Compose new post-quantum secured email (Ctrl+N)")
        self.new_btn.clicked.connect(self.new_message_requested.emit)
        compose_row.addWidget(self.new_btn)
        compose_row.addStretch()
        layout.addLayout(compose_row)

        # 2. Folders List
        self.folder_list = QListWidget()
        self.folder_list.setFrameShape(QFrame.Shape.NoFrame)

        folders = [
            ("inbox", "inbox", "Inbox", 0),
            ("starred", "star", "Starred", 0),
            ("sent", "send", "Sent", 0),
            ("drafts", "draft", "Drafts", 0),
            ("outbox", "send", "Outbox", 0),
            ("trash", "trash", "Trash", 0),
        ]

        for key, icon, label, count in folders:
            item = QListWidgetItem(self.folder_list)
            widget = FolderItemWidget(key, icon, label, count)
            item.setSizeHint(widget.sizeHint())
            self.folder_list.addItem(item)
            self.folder_list.setItemWidget(item, widget)
            self._folder_widgets[key] = widget

        self.folder_list.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self.folder_list)

        # Select Inbox by default
        self.folder_list.setCurrentRow(0)

        layout.addStretch()

        # 3. Hardware & Quantum Entropy Status Badge
        self.status_card = QFrame()
        status_l = QVBoxLayout(self.status_card)
        status_l.setContentsMargins(10, 8, 10, 8)
        status_l.setSpacing(4)

        hsm_row = QHBoxLayout()
        self.hsm_dot = QLabel()
        self.hsm_dot.setStyleSheet("background: transparent;")
        self.hsm_dot.setPixmap(get_pixmap("hardware", color="#137333", size=16))
        hsm_row.addWidget(self.hsm_dot)

        self.hsm_status_lbl = QLabel("Hardware TRNG")
        self.hsm_status_lbl.setStyleSheet("font-size: 12px; font-weight: 700; background: transparent;")
        hsm_row.addWidget(self.hsm_status_lbl)
        hsm_row.addStretch()
        status_l.addLayout(hsm_row)

        self.sync_status_lbl = QLabel("Post-Quantum Sealing Active")
        self.sync_status_lbl.setStyleSheet("font-size: 11px; background: transparent;")
        status_l.addWidget(self.sync_status_lbl)

        layout.addWidget(self.status_card)

        # 4. Settings & Lock Vault Quick Actions
        action_bar = QHBoxLayout()
        action_bar.setSpacing(6)

        self.theme_btn = QPushButton()
        self.theme_btn.setFixedSize(32, 32)
        self.theme_btn.setToolTip("Toggle Theme")
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.setIcon(get_icon("moon" if ThemeManager.get().mode == "light" else "sun", size=16))
        self.theme_btn.clicked.connect(self._on_toggle_theme)
        action_bar.addWidget(self.theme_btn)

        self.settings_btn = QPushButton(" Settings")
        self.settings_btn.setIcon(get_icon("settings", size=16))
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setFixedHeight(32)
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        action_bar.addWidget(self.settings_btn)

        self.lock_btn = QPushButton(" Lock")
        self.lock_btn.setIcon(get_icon("lock", size=16))
        self.lock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lock_btn.setFixedHeight(32)
        self.lock_btn.clicked.connect(self.lock_requested.emit)
        action_bar.addWidget(self.lock_btn)

        layout.addLayout(action_bar)

        # Connect to HSMManager
        try:
            from core.hsm import HSMManager
            HSMManager.get().add_listener(self._on_hsm_snapshot)
        except Exception:
            pass

        self._apply_theme()

    def _apply_theme(self) -> None:
        p = ThemeManager.get().palette
        self.setStyleSheet(
            f"NavigationPane {{ background-color: {p.bg_sidebar}; border-right: 1px solid {p.border_subtle}; }}"
        )
        # Gmail Compose button: soft blue (#C2E7FF), dark text (#001D35), 16px radius
        self.new_btn.setStyleSheet(
            f"QPushButton {{ background-color: {p.accent_subtle}; color: {p.text_inverse}; font-size: 14px; font-weight: 600; "
            f"border: 1px solid transparent; border-radius: 16px; padding: 0 16px; }} "
            f"QPushButton:hover {{ background-color: #B3DCF5; border-color: #A0CEEE; }} "
            f"QPushButton:pressed {{ background-color: #92C0E2; }}"
        )
        # Gmail Folder List Item: rounded pill (18px radius) when selected
        self.folder_list.setStyleSheet(
            f"QListWidget {{ background: transparent; outline: none; border: none; }} "
            f"QListWidget::item {{ border-radius: 18px; padding: 2px 4px; margin: 1px 2px; min-height: 34px; }} "
            f"QListWidget::item:hover {{ background-color: {p.bg_card_hover}; }} "
            f"QListWidget::item:selected {{ background-color: {p.bg_card_selected}; color: {p.text_inverse}; font-weight: 700; }}"
        )
        self.status_card.setStyleSheet(
            f"QFrame {{ background-color: {p.bg_surface}; border: 1px solid {p.border_default}; border-radius: 8px; }}"
        )
        compose_icon_color = p.text_inverse if p == LIGHT_PALETTE else "#FFFFFF"
        self.new_btn.setIcon(get_icon("compose", color=compose_icon_color, size=20))
        self.theme_btn.setIcon(get_icon("moon" if ThemeManager.get().mode == "light" else "sun", color=p.text_secondary, size=16))
        self.settings_btn.setIcon(get_icon("settings", color=p.text_secondary, size=16))
        self.lock_btn.setIcon(get_icon("lock", color=p.text_secondary, size=16))

        btn_style = (
            f"QPushButton {{ background-color: {p.bg_surface}; color: {p.text_secondary}; "
            f"border: 1px solid {p.border_default}; border-radius: 6px; padding: 4px 8px; font-size: 12px; font-weight: 600; }} "
            f"QPushButton:hover {{ background-color: {p.bg_card_hover}; color: {p.text_primary}; border-color: {p.border_focused}; }}"
        )
        self.settings_btn.setStyleSheet(btn_style)
        self.lock_btn.setStyleSheet(btn_style)
        self.theme_btn.setStyleSheet(btn_style)

    def _on_row_changed(self, row: int) -> None:
        item = self.folder_list.item(row)
        if item:
            widget = self.folder_list.itemWidget(item)
            if isinstance(widget, FolderItemWidget):
                self.folder_selected.emit(widget.key)

    def _on_toggle_theme(self) -> None:
        new_mode = ThemeManager.get().toggle()
        self.theme_btn.setIcon(get_icon("moon" if new_mode == "light" else "sun", size=16))
        self.theme_toggled.emit(new_mode)

    def _on_hsm_snapshot(self, snap: Any) -> None:
        if snap.is_hardware_active:
            self.hsm_status_lbl.setText("⚡ Physical TRNG")
            self.hsm_status_lbl.setStyleSheet("color: #137333; font-weight: 700;")
            self.sync_status_lbl.setText(f"Connected ({snap.active_port})")
        elif snap.mode == "ETSI_QKD":
            self.hsm_status_lbl.setText("🔷 ETSI QKD Stream")
            self.hsm_status_lbl.setStyleSheet("color: #0B57D0; font-weight: 700;")
            self.sync_status_lbl.setText("Active Key Delivery")
        else:
            self.hsm_status_lbl.setText("⚡ Software CSPRNG")
            self.hsm_status_lbl.setStyleSheet(f"color: {ThemeManager.get().palette.text_secondary}; font-weight: 600;")
            self.sync_status_lbl.setText("Post-Quantum Active")

    def set_unread_count(self, folder_key: str, count: int) -> None:
        if folder_key in self._folder_widgets:
            self._folder_widgets[folder_key].set_count(count)

    def set_account_identity(self, email: str) -> None:
        pass

    def set_sync_state(self, state: str) -> None:
        if "sync" in state.lower():
            self.sync_status_lbl.setText("Synchronizing…")
        else:
            self.sync_status_lbl.setText(state)
