"""
ui/navigation_pane.py — Modernized Navigation Sidebar Component.

Built according to UI/UX Pro Max desktop productivity standards:
- Professional header with shield branding, QuMail version, and sync dot.
- Primary New Message composition CTA with keyboard shortcut hint (Ctrl+N).
- System folder navigation (Inbox, Starred, Sent, Drafts, Outbox, Archive, Trash)
  with live dynamic unread badges.
- Bottom Account Card with monogram avatar, signed-in address, and sync status.
- Direct quick-action controls: Theme Switcher (☀️/🌙), Settings (⚙️), and Vault Lock (🔒).
- Dual-theme reactive palette support (Dark & Light).
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

from ui.design_system import C, AvatarWidget, ThemeManager


class FolderItemWidget(QWidget):
    """Folder list item widget with icon, label, and unread count badge."""

    def __init__(self, key: str, icon: str, label: str, count: int = 0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)

        self.icon_lbl = QLabel(icon)
        self.icon_lbl.setStyleSheet("font-size: 15px; background: transparent;")
        layout.addWidget(self.icon_lbl)

        p = ThemeManager.get().palette
        self.text_lbl = QLabel(label)
        self.text_lbl.setStyleSheet(f"color: {p.text_primary}; font-size: 13px; font-weight: 500; background: transparent;")
        layout.addWidget(self.text_lbl)

        layout.addStretch()

        self.badge = QLabel()
        self.badge.setStyleSheet(
            f"background-color: {p.accent}; color: {p.text_inverse}; font-size: 11px; font-weight: 700; "
            f"padding: 1px 7px; border-radius: 9px;"
        )
        self.badge.setVisible(False)
        layout.addWidget(self.badge)

        self.set_count(count)

    def set_count(self, count: int) -> None:
        if count > 0:
            self.badge.setText(str(count))
            self.badge.setVisible(True)
        else:
            self.badge.setVisible(False)


class NavigationPane(QFrame):
    """
    Left sidebar navigation pane.
    Emits folder_selected(folder_key) when user clicks a folder.
    """

    new_message_requested = pyqtSignal()
    folder_selected = pyqtSignal(str)
    settings_requested = pyqtSignal()
    lock_requested = pyqtSignal()
    account_switch_requested = pyqtSignal()
    theme_toggled = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(230)
        self._folder_widgets: dict[str, FolderItemWidget] = {}

        ThemeManager.get().theme_changed.connect(self._apply_theme)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(12)

        # 1. Branding Header
        brand_layout = QHBoxLayout()
        brand_layout.setSpacing(8)

        logo_lbl = QLabel("🛡️")
        logo_lbl.setStyleSheet("font-size: 20px; background: transparent;")
        brand_layout.addWidget(logo_lbl)

        brand_title = QLabel("QuMail")
        brand_title.setStyleSheet("font-size: 17px; font-weight: 800; letter-spacing: -0.3px; background: transparent;")
        brand_layout.addWidget(brand_title)

        pq_badge = QLabel("PQ-v1")
        pq_badge.setStyleSheet(
            f"color: {ThemeManager.get().palette.accent}; background-color: {ThemeManager.get().palette.accent_subtle}; "
            f"font-size: 10px; font-weight: 700; padding: 2px 5px; border-radius: 4px;"
        )
        brand_layout.addWidget(pq_badge)
        brand_layout.addStretch()

        layout.addLayout(brand_layout)

        # 2. Primary New Message Button
        self.new_btn = QPushButton("New Message")
        self.new_btn.setFixedHeight(42)
        self.new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_btn.setToolTip("Compose new protected email (Ctrl+N)")
        self.new_btn.clicked.connect(self.new_message_requested.emit)
        layout.addWidget(self.new_btn)

        # 3. Folders List
        self.folder_list = QListWidget()
        self.folder_list.setFrameShape(QFrame.Shape.NoFrame)

        folders = [
            ("inbox", "📥", "Inbox", 0),
            ("starred", "⭐", "Starred", 0),
            ("sent", "📤", "Sent Mail", 0),
            ("drafts", "📝", "Drafts", 0),
            ("outbox", "📦", "Outbox", 0),
            ("archive", "🗄️", "Archive", 0),
            ("trash", "🗑️", "Trash", 0),
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

        # 4. Account & Sync Status Card (Bottom)
        self.account_card = QFrame()
        card_layout = QVBoxLayout(self.account_card)
        card_layout.setContentsMargins(8, 8, 8, 8)
        card_layout.setSpacing(6)

        # Account Info row
        acc_row = QHBoxLayout()
        self.avatar_widget = AvatarWidget("QuMail User", size=24)
        acc_row.addWidget(self.avatar_widget)

        self.account_lbl = QLabel("No Account")
        self.account_lbl.setStyleSheet("font-size: 12px; font-weight: 600; background: transparent;")
        acc_row.addWidget(self.account_lbl)
        acc_row.addStretch()
        card_layout.addLayout(acc_row)

        # Sync Status row
        sync_row = QHBoxLayout()
        self.sync_dot = QLabel("●")
        self.sync_dot.setStyleSheet("color: #22C55E; font-size: 10px; background: transparent;")
        sync_row.addWidget(self.sync_dot)

        self.sync_status_lbl = QLabel("Idle")
        self.sync_status_lbl.setStyleSheet("font-size: 11px; background: transparent;")
        sync_row.addWidget(self.sync_status_lbl)
        sync_row.addStretch()
        card_layout.addLayout(sync_row)

        # Hardware HSM / QKD Status row
        hsm_row = QHBoxLayout()
        self.hsm_dot = QLabel("⚡")
        self.hsm_dot.setStyleSheet("font-size: 11px; background: transparent;")
        hsm_row.addWidget(self.hsm_dot)

        self.hsm_status_lbl = QLabel("Software CSPRNG")
        self.hsm_status_lbl.setStyleSheet("font-size: 11px; background: transparent;")
        hsm_row.addWidget(self.hsm_status_lbl)
        hsm_row.addStretch()
        card_layout.addLayout(hsm_row)

        # Connect to HSMManager
        try:
            from core.hsm import HSMManager
            HSMManager.get().add_listener(self._on_hsm_snapshot)
        except Exception:
            pass

        layout.addWidget(self.account_card)

        # 5. Bottom Action Bar (Settings, Theme Toggle, Lock)
        action_bar = QHBoxLayout()
        action_bar.setSpacing(6)

        self.theme_btn = QPushButton("🌙")
        self.theme_btn.setFixedSize(30, 30)
        self.theme_btn.setToolTip("Toggle Dark / Light Theme")
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.clicked.connect(self._on_toggle_theme)
        action_bar.addWidget(self.theme_btn)

        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setFixedHeight(30)
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        action_bar.addWidget(self.settings_btn)

        self.lock_btn = QPushButton("Lock Vault")
        self.lock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lock_btn.setFixedHeight(30)
        self.lock_btn.clicked.connect(self.lock_requested.emit)
        action_bar.addWidget(self.lock_btn)

        layout.addLayout(action_bar)

        self._apply_theme()

    def _apply_theme(self) -> None:
        p = ThemeManager.get().palette
        self.setStyleSheet(
            f"NavigationPane {{ background-color: {p.bg_sidebar}; border-right: 1px solid {p.border_subtle}; }}"
        )
        self.new_btn.setStyleSheet(
            f"QPushButton {{ background-color: {p.accent}; color: {p.text_inverse}; font-size: 14px; font-weight: 700; "
            f"border: none; border-radius: 21px; padding: 0 20px; }} "
            f"QPushButton:hover {{ background-color: {p.accent_hover}; }} "
            f"QPushButton:pressed {{ background-color: {p.border_focused}; }}"
        )
        self.folder_list.setStyleSheet(
            f"QListWidget {{ background: transparent; outline: none; border: none; }} "
            f"QListWidget::item {{ border-radius: 16px; padding: 3px 6px; margin: 2px 4px; }} "
            f"QListWidget::item:hover {{ background-color: {p.bg_card_hover}; }} "
            f"QListWidget::item:selected {{ background-color: {p.accent_subtle}; }}"
        )
        self.account_card.setStyleSheet(
            f"QFrame {{ background-color: {p.bg_card}; border: 1px solid {p.border_default}; border-radius: 10px; }}"
        )
        btn_style = (
            f"QPushButton {{ background-color: {p.bg_card}; color: {p.text_secondary}; "
            f"border: 1px solid {p.border_default}; border-radius: 6px; padding: 5px 10px; font-size: 12px; font-weight: 600; }} "
            f"QPushButton:hover {{ background-color: {p.bg_card_hover}; color: {p.text_primary}; border-color: {p.border_focused}; }}"
        )
        self.settings_btn.setStyleSheet(btn_style)
        self.lock_btn.setStyleSheet(btn_style)
        self.theme_btn.setStyleSheet(btn_style)
        self.theme_btn.setText("☀️" if ThemeManager.get().mode == "dark" else "🌙")

        for w in self._folder_widgets.values():
            w.text_lbl.setStyleSheet(f"color: {p.text_primary}; font-size: 13px; font-weight: 600; background: transparent;")

    def _on_toggle_theme(self) -> None:
        new_mode = ThemeManager.get().toggle()
        self.theme_toggled.emit(new_mode)

    def _on_row_changed(self, row: int) -> None:
        item = self.folder_list.item(row)
        if item:
            widget = self.folder_list.itemWidget(item)
            if isinstance(widget, FolderItemWidget):
                self.folder_selected.emit(widget.key)

    def set_unread_count(self, folder: str, count: int) -> None:
        """Update unread badge count for a specific folder."""
        if folder in self._folder_widgets:
            self._folder_widgets[folder].set_count(count)

    def set_account_identity(self, email: str) -> None:
        """Update active account email in bottom card."""
        display_text = email if email else "No Account"
        if len(display_text) > 22:
            display_text = display_text[:19] + "…"
        self.account_lbl.setText(display_text)
        self.account_lbl.setToolTip(email)
        if email:
            self.avatar_widget.set_identity(email)

    def set_sync_state(self, state: str, detail: str = "") -> None:
        """Update synchronization indicator dot and text."""
        p = ThemeManager.get().palette
        state_lower = state.lower()
        if "reconnect" in state_lower:
            color = p.caution
            label = "Reconnecting…"
        elif "idle" in state_lower or "connected" in state_lower:
            color = p.secure
            label = "Idle"
        elif "sync" in state_lower or "connecting" in state_lower:
            color = p.accent
            label = "Synchronizing…"
        elif "offline" in state_lower or "stopped" in state_lower:
            color = p.alert
            label = "Offline"
        else:
            color = p.text_muted
            label = state.capitalize()

        self.sync_dot.setStyleSheet(f"color: {color}; font-size: 10px; background: transparent;")
        self.sync_status_lbl.setText(label)
        self.sync_status_lbl.setToolTip(detail or label)

    def _on_hsm_snapshot(self, snap: Any) -> None:
        """Callback from HSMManager background thread."""
        if hasattr(snap, "is_hardware_active") and snap.is_hardware_active:
            self.set_hsm_status(True, f"Hardware TRNG ({snap.active_port})")
        elif hasattr(snap, "mode") and snap.mode == "ETSI_QKD":
            self.set_hsm_status(True, "ETSI QKD Link")
        else:
            self.set_hsm_status(False, "Software CSPRNG")

    def set_hsm_status(self, is_active: bool, label: str) -> None:
        p = ThemeManager.get().palette
        if is_active:
            self.hsm_dot.setText("⚡")
            self.hsm_status_lbl.setText(label)
            self.hsm_status_lbl.setStyleSheet(f"color: {p.secure}; font-size: 11px; font-weight: 600; background: transparent;")
        else:
            self.hsm_dot.setText("⚪")
            self.hsm_status_lbl.setText("Software CSPRNG")
            self.hsm_status_lbl.setStyleSheet(f"color: {p.text_muted}; font-size: 11px; background: transparent;")
