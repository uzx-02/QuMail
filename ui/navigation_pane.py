"""
Left Navigation Pane Component (WS-05).

Provides the left sidebar of the three-pane desktop layout:
- QuMail branding & post-quantum status
- Prominent 'New Message' primary composition action
- System folder navigation (Inbox, Starred, Sent, Drafts, Outbox, Archive, Trash)
- Live unread badge count updates derived from WS-03 index APIs
- Active account display & identity switcher
- Unobtrusive synchronization state indicator (IDLE, Syncing, Reconnecting, Offline)
- Quick access to Settings and Vault Lock
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QListWidget,
    QListWidgetItem,
)

from ui.design_system import C, StatusPill


class FolderItemWidget(QWidget):
    """Custom widget for folder list item with icon, label, and unread badge."""

    def __init__(self, key: str, icon: str, label: str, count: int = 0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        self.icon_lbl = QLabel(icon)
        self.icon_lbl.setStyleSheet("font-size: 15px;")
        layout.addWidget(self.icon_lbl)

        self.text_lbl = QLabel(label)
        self.text_lbl.setStyleSheet(f"color: {C['text_primary']}; font-size: 13px; font-weight: 500;")
        layout.addWidget(self.text_lbl)

        layout.addStretch()

        self.badge = QLabel()
        self.badge.setStyleSheet(
            f"background-color: {C['accent']}; color: #FFFFFF; font-size: 11px; font-weight: 700; "
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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(230)
        self.setStyleSheet(
            f"NavigationPane {{ background-color: {C['bg_sidebar']}; border-right: 1px solid {C['border']}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(14)

        # 1. Branding Header
        brand_layout = QHBoxLayout()
        brand_layout.setSpacing(8)

        logo_lbl = QLabel("🛡️")
        logo_lbl.setStyleSheet("font-size: 20px;")
        brand_layout.addWidget(logo_lbl)

        brand_title = QLabel("QuMail")
        brand_title.setStyleSheet(f"color: {C['text_primary']}; font-size: 17px; font-weight: 800; letter-spacing: -0.3px;")
        brand_layout.addWidget(brand_title)

        pq_badge = QLabel("PQ-v1")
        pq_badge.setStyleSheet(
            f"color: {C['accent_light']}; background-color: {C['accent_muted']}; "
            f"font-size: 10px; font-weight: 700; padding: 2px 5px; border-radius: 4px;"
        )
        brand_layout.addWidget(pq_badge)
        brand_layout.addStretch()

        layout.addLayout(brand_layout)

        # 2. Primary New Message Button
        self.new_btn = QPushButton("✏️  New Message")
        self.new_btn.setFixedHeight(38)
        self.new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_btn.setStyleSheet(
            f"QPushButton {{ background-color: {C['accent']}; color: #FFFFFF; font-size: 13px; font-weight: 700; "
            f"border: none; border-radius: 7px; padding: 0 16px; text-align: center; }} "
            f"QPushButton:hover {{ background-color: {C['accent_glow']}; }} "
            f"QPushButton:pressed {{ background-color: {C['accent_muted']}; }}"
        )
        self.new_btn.clicked.connect(self.new_message_requested.emit)
        layout.addWidget(self.new_btn)

        # 3. Folders List
        self.folder_list = QListWidget()
        self.folder_list.setFrameShape(QFrame.Shape.NoFrame)
        self.folder_list.setStyleSheet(
            f"QListWidget {{ background: transparent; outline: none; border: none; }} "
            f"QListWidget::item {{ border-radius: 6px; padding: 2px 0; margin-bottom: 2px; }} "
            f"QListWidget::item:hover {{ background-color: {C['bg_hover']}; }} "
            f"QListWidget::item:selected {{ background-color: {C['accent_muted']}; border-left: 3px solid {C['accent']}; }}"
        )

        self._folder_widgets: dict[str, FolderItemWidget] = {}
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
        account_card = QFrame()
        account_card.setStyleSheet(
            f"QFrame {{ background-color: {C['bg_card']}; border: 1px solid {C['border']}; border-radius: 8px; padding: 8px; }}"
        )
        card_layout = QVBoxLayout(account_card)
        card_layout.setContentsMargins(6, 6, 6, 6)
        card_layout.setSpacing(6)

        # Account Info row
        acc_row = QHBoxLayout()
        self.avatar_lbl = QLabel("👤")
        self.avatar_lbl.setStyleSheet("font-size: 14px;")
        acc_row.addWidget(self.avatar_lbl)

        self.account_lbl = QLabel("No Account")
        self.account_lbl.setStyleSheet(f"color: {C['text_primary']}; font-size: 12px; font-weight: 600;")
        self.account_lbl.setWordWrap(False)
        acc_row.addWidget(self.account_lbl)
        acc_row.addStretch()
        card_layout.addLayout(acc_row)

        # Sync Status row
        sync_row = QHBoxLayout()
        self.sync_dot = QLabel("●")
        self.sync_dot.setStyleSheet(f"color: {C['online']}; font-size: 10px;")
        sync_row.addWidget(self.sync_dot)

        self.sync_status_lbl = QLabel("Idle")
        self.sync_status_lbl.setStyleSheet(f"color: {C['text_secondary']}; font-size: 11px;")
        sync_row.addWidget(self.sync_status_lbl)
        sync_row.addStretch()
        card_layout.addLayout(sync_row)

        layout.addWidget(account_card)

        # 5. Settings & Lock Action Bar
        action_bar = QHBoxLayout()
        action_bar.setSpacing(6)

        self.settings_btn = QPushButton("⚙️ Settings")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setStyleSheet(
            f"QPushButton {{ background-color: {C['bg_card']}; color: {C['text_secondary']}; "
            f"border: 1px solid {C['border']}; border-radius: 5px; padding: 5px 10px; font-size: 11px; }} "
            f"QPushButton:hover {{ background-color: {C['bg_hover']}; color: {C['text_primary']}; }}"
        )
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        action_bar.addWidget(self.settings_btn)

        self.lock_btn = QPushButton("🔒 Lock")
        self.lock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lock_btn.setStyleSheet(
            f"QPushButton {{ background-color: {C['bg_card']}; color: {C['text_secondary']}; "
            f"border: 1px solid {C['border']}; border-radius: 5px; padding: 5px 10px; font-size: 11px; }} "
            f"QPushButton:hover {{ background-color: {C['bg_hover']}; color: {C['text_primary']}; }}"
        )
        self.lock_btn.clicked.connect(self.lock_requested.emit)
        action_bar.addWidget(self.lock_btn)

        layout.addLayout(action_bar)

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

    def set_sync_state(self, state: str, detail: str = "") -> None:
        """Update synchronization indicator dot and text."""
        state_lower = state.lower()
        if "reconnect" in state_lower:
            color = C["warning"]
            label = "Reconnecting…"
        elif "idle" in state_lower or "connected" in state_lower:
            color = C["online"]
            label = "Idle"
        elif "sync" in state_lower or "connecting" in state_lower:
            color = C["accent_light"]
            label = "Synchronizing…"
        elif "offline" in state_lower or "stopped" in state_lower:
            color = C["offline"]
            label = "Offline"
        else:
            color = C["text_tertiary"]
            label = state.capitalize()

        self.sync_dot.setStyleSheet(f"color: {color}; font-size: 10px;")
        self.sync_status_lbl.setText(label)
        self.sync_status_lbl.setToolTip(detail or label)
