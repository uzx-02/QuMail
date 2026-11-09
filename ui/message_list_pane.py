"""
Middle Message List Pane Component (WS-05).

Provides the middle message-list pane of the three-pane desktop layout:
- Instant local search filtering across sender, subject, and snippet preview
- Filter tabs: All vs Unread Only
- Rich message card items with:
  * Sender display name and address
  * Subject (bold typography when unread)
  * Short sanitized body/header preview snippet
  * Clean formatted date/time
  * Visual unread accent indicator
  * Attachment clip badge (when attachments present)
  * Security indicator badge (Verified, Encrypted, Alert, External)
- Non-blocking pagination ('Older' button)
- Empty state indicator when folder is clear
"""

from __future__ import annotations

from email.utils import parsedate_to_datetime
import time
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.mailbox_index import IndexedMessage, sanitize_snippet
from core.security_indicators import BadgeLevel, SecurityIndicator
from ui.design_system import C, EmptyState
from ui.security_badge_widget import SecurityPill


def format_message_date(date_str: str, date_ts: float = 0.0) -> str:
    """Format an RFC date into a clean, human-friendly desktop timestamp."""
    try:
        if date_ts > 0:
            ts = date_ts
        elif date_str:
            dt = parsedate_to_datetime(date_str)
            ts = dt.timestamp()
        else:
            return ""

        now = time.time()
        diff = now - ts

        # Today: show time e.g. 10:45 AM
        import datetime
        msg_date = datetime.datetime.fromtimestamp(ts)
        today = datetime.datetime.now().date()

        if msg_date.date() == today:
            return msg_date.strftime("%I:%M %p").lstrip("0")
        elif msg_date.date() == today - datetime.timedelta(days=1):
            return "Yesterday"
        elif diff < 7 * 86400:
            return msg_date.strftime("%a")  # e.g. "Mon"
        elif msg_date.year == today.year:
            return msg_date.strftime("%b %d")  # e.g. "Nov 09"
        else:
            return msg_date.strftime("%m/%d/%Y")
    except Exception:
        return date_str[:12] if date_str else ""


class MessageCardWidget(QWidget):
    """
    Rich message card rendered in the middle message list.
    """

    def __init__(
        self,
        sender: str,
        subject: str,
        snippet: str,
        date_str: str,
        seen: bool = False,
        has_attachments: bool = False,
        indicator: SecurityIndicator | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.seen = seen

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # Row 1: Unread Dot + Sender + Date
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        self.unread_dot = QLabel("●")
        self.unread_dot.setStyleSheet(
            f"color: {C['accent'] if not seen else 'transparent'}; font-size: 10px;"
        )
        row1.addWidget(self.unread_dot)

        self.sender_lbl = QLabel(sender or "Unknown Sender")
        weight = "700" if not seen else "500"
        self.sender_lbl.setStyleSheet(f"color: {C['text_primary']}; font-size: 13px; font-weight: {weight};")
        row1.addWidget(self.sender_lbl)

        row1.addStretch()

        self.date_lbl = QLabel(date_str)
        self.date_lbl.setStyleSheet(f"color: {C['text_secondary']}; font-size: 11px;")
        row1.addWidget(self.date_lbl)

        layout.addLayout(row1)

        # Row 2: Subject (Bold if unread)
        self.subject_lbl = QLabel(subject or "(No Subject)")
        sub_weight = "700" if not seen else "500"
        sub_color = C["text_primary"] if not seen else C["text_secondary"]
        self.subject_lbl.setStyleSheet(f"color: {sub_color}; font-size: 12px; font-weight: {sub_weight};")
        layout.addWidget(self.subject_lbl)

        # Row 3: Snippet Preview
        self.snippet_lbl = QLabel(snippet)
        self.snippet_lbl.setStyleSheet(f"color: {C['text_tertiary']}; font-size: 11px;")
        self.snippet_lbl.setWordWrap(False)
        layout.addWidget(self.snippet_lbl)

        # Row 4: Badges (Attachment indicator + Security Pill)
        row4 = QHBoxLayout()
        row4.setSpacing(6)

        if has_attachments:
            attach_lbl = QLabel("📎 Attachment")
            attach_lbl.setStyleSheet(
                f"color: {C['text_secondary']}; background-color: {C['bg_hover']}; "
                f"font-size: 10px; font-weight: 600; padding: 1px 5px; border-radius: 3px;"
            )
            row4.addWidget(attach_lbl)

        if indicator:
            self.pill = SecurityPill(indicator)
            row4.addWidget(self.pill)

        row4.addStretch()
        layout.addLayout(row4)

    def set_seen(self, seen: bool) -> None:
        self.seen = seen
        self.unread_dot.setStyleSheet(
            f"color: {C['accent'] if not seen else 'transparent'}; font-size: 10px;"
        )
        weight = "700" if not seen else "500"
        self.sender_lbl.setStyleSheet(f"color: {C['text_primary']}; font-size: 13px; font-weight: {weight};")
        sub_color = C["text_primary"] if not seen else C["text_secondary"]
        self.subject_lbl.setStyleSheet(f"color: {sub_color}; font-size: 12px; font-weight: {weight};")


class MessageListPane(QFrame):
    """
    Middle pane containing message search, filter toggles, message list, and pagination.
    """

    message_selected = pyqtSignal(object)       # Emits selected message item/key
    message_activated = pyqtSignal(object)      # Emits on double click
    refresh_requested = pyqtSignal()
    older_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(320)
        self.setStyleSheet(
            f"MessageListPane {{ background-color: {C['bg_base']}; border-right: 1px solid {C['border']}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 10)
        layout.setSpacing(10)

        # 1. Header Row (Folder Title, Total Count, Refresh Button)
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        self.folder_title = QLabel("Inbox")
        self.folder_title.setStyleSheet(f"color: {C['text_primary']}; font-size: 16px; font-weight: 800;")
        header_row.addWidget(self.folder_title)

        self.count_lbl = QLabel("")
        self.count_lbl.setStyleSheet(f"color: {C['text_secondary']}; font-size: 12px;")
        header_row.addWidget(self.count_lbl)

        header_row.addStretch()

        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setFixedSize(28, 28)
        self.refresh_btn.setToolTip("Refresh messages")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setStyleSheet(
            f"QPushButton {{ background-color: {C['bg_card']}; border: 1px solid {C['border']}; "
            f"border-radius: 5px; font-size: 13px; }} "
            f"QPushButton:hover {{ background-color: {C['bg_hover']}; }}"
        )
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        header_row.addWidget(self.refresh_btn)

        layout.addLayout(header_row)

        # 2. Search Box
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍  Search sender, subject, or preview…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setStyleSheet(
            f"QLineEdit {{ background-color: {C['bg_card']}; border: 1px solid {C['border']}; "
            f"border-radius: 6px; padding: 6px 10px; color: {C['text_primary']}; font-size: 12px; }} "
            f"QLineEdit:focus {{ border: 1px solid {C['accent']}; }}"
        )
        self.search_input.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_input)

        # 3. Filter Tabs (All / Unread)
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)

        self.all_tab = QPushButton("All")
        self.all_tab.setCheckable(True)
        self.all_tab.setChecked(True)
        self.all_tab.setCursor(Qt.CursorShape.PointingHandCursor)
        self.all_tab.setStyleSheet(
            f"QPushButton {{ background-color: {C['bg_card']}; color: {C['text_secondary']}; "
            f"border: 1px solid {C['border']}; border-radius: 5px; padding: 4px 12px; font-size: 11px; font-weight: 600; }} "
            f"QPushButton:checked {{ background-color: {C['accent_muted']}; color: {C['accent_light']}; border-color: {C['accent']}; }}"
        )

        self.unread_tab = QPushButton("Unread")
        self.unread_tab.setCheckable(True)
        self.unread_tab.setChecked(False)
        self.unread_tab.setCursor(Qt.CursorShape.PointingHandCursor)
        self.unread_tab.setStyleSheet(
            f"QPushButton {{ background-color: {C['bg_card']}; color: {C['text_secondary']}; "
            f"border: 1px solid {C['border']}; border-radius: 5px; padding: 4px 12px; font-size: 11px; font-weight: 600; }} "
            f"QPushButton:checked {{ background-color: {C['accent_muted']}; color: {C['accent_light']}; border-color: {C['accent']}; }}"
        )

        self.all_tab.clicked.connect(lambda: self._set_filter_tab(False))
        self.unread_tab.clicked.connect(lambda: self._set_filter_tab(True))

        filter_row.addWidget(self.all_tab)
        filter_row.addWidget(self.unread_tab)
        filter_row.addStretch()

        layout.addLayout(filter_row)

        # 4. Message List Widget
        self.list_widget = QListWidget()
        self.list_widget.setFrameShape(QFrame.Shape.NoFrame)
        self.list_widget.setStyleSheet(
            f"QListWidget {{ background: transparent; outline: none; border: none; }} "
            f"QListWidget::item {{ border-bottom: 1px solid {C['border']}; padding: 0; }} "
            f"QListWidget::item:hover {{ background-color: {C['bg_hover']}; }} "
            f"QListWidget::item:selected {{ background-color: {C['accent_muted']}; border-left: 3px solid {C['accent']}; }}"
        )
        self.list_widget.currentItemChanged.connect(self._on_item_selected)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_widget)

        # Empty State Placeholder (hidden by default)
        self.empty_state = EmptyState("📬", "No messages found", "Try clearing your search query or refresh.")
        self.empty_state.setVisible(False)
        layout.addWidget(self.empty_state)

        # 5. Footer Pagination Row
        footer_row = QHBoxLayout()
        self.older_btn = QPushButton("⏮️  Older messages")
        self.older_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.older_btn.setStyleSheet(
            f"QPushButton {{ background-color: {C['bg_card']}; color: {C['text_secondary']}; "
            f"border: 1px solid {C['border']}; border-radius: 5px; padding: 5px 12px; font-size: 11px; }} "
            f"QPushButton:hover {{ background-color: {C['bg_hover']}; color: {C['text_primary']}; }} "
            f"QPushButton:disabled {{ color: {C['text_tertiary']}; border-color: transparent; }}"
        )
        self.older_btn.clicked.connect(self.older_requested.emit)
        self.older_btn.setEnabled(False)
        footer_row.addWidget(self.older_btn)
        footer_row.addStretch()

        layout.addLayout(footer_row)

        # Internal state
        self._items_data: list[tuple[Any, dict[str, Any]]] = []
        self._filter_unread_only = False

    def _set_filter_tab(self, unread_only: bool) -> None:
        self._filter_unread_only = unread_only
        self.all_tab.setChecked(not unread_only)
        self.unread_tab.setChecked(unread_only)
        self._apply_filters()

    def _on_search_changed(self, text: str) -> None:
        self._apply_filters()

    def _on_item_selected(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        if current:
            data = current.data(Qt.ItemDataRole.UserRole)
            self.message_selected.emit(data)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)
            self.message_activated.emit(data)

    def set_folder_info(self, name: str, total_count: int = 0, unread_count: int = 0) -> None:
        """Update folder title and counts."""
        self.folder_title.setText(name)
        if total_count > 0:
            if unread_count > 0:
                self.count_lbl.setText(f"{total_count} messages · {unread_count} unread")
            else:
                self.count_lbl.setText(f"{total_count} messages")
        else:
            self.count_lbl.setText("")

    def set_messages(self, messages_data: list[tuple[Any, dict[str, Any]]]) -> None:
        """
        Populate the list with messages.
        Each item is (item_key, item_dict):
        item_dict contains: sender, subject, snippet, date_str, seen, has_attachments, indicator.
        """
        self._items_data = messages_data
        self._apply_filters()

    def _apply_filters(self) -> None:
        query = self.search_input.text().strip().lower()
        self.list_widget.blockSignals(True)
        self.list_widget.clear()

        visible_count = 0
        for item_key, data in self._items_data:
            sender = str(data.get("sender", ""))
            subject = str(data.get("subject", ""))
            snippet = str(data.get("snippet", ""))
            seen = bool(data.get("seen", False))
            date_str = str(data.get("date_str", ""))
            has_attachments = bool(data.get("has_attachments", False))
            indicator = data.get("indicator")

            # Check unread filter
            if self._filter_unread_only and seen:
                continue

            # Check search filter
            if query:
                combined = f"{sender} {subject} {snippet}".lower()
                if query not in combined:
                    continue

            # Add item
            item = QListWidgetItem(self.list_widget)
            item.setData(Qt.ItemDataRole.UserRole, item_key)
            card = MessageCardWidget(
                sender=sender,
                subject=subject,
                snippet=snippet,
                date_str=date_str,
                seen=seen,
                has_attachments=has_attachments,
                indicator=indicator,
            )
            item.setSizeHint(card.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, card)
            visible_count += 1

        self.list_widget.blockSignals(False)

        # Update empty state visibility
        if visible_count == 0:
            self.list_widget.setVisible(False)
            self.empty_state.setVisible(True)
        else:
            self.list_widget.setVisible(True)
            self.empty_state.setVisible(False)

    def select_row(self, row: int) -> None:
        """Select a row by index."""
        if 0 <= row < self.list_widget.count():
            self.list_widget.setCurrentRow(row)

    def get_selected_key(self) -> Any | None:
        """Return the user data key of the selected row."""
        item = self.list_widget.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None
