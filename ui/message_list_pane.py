"""
ui/message_list_pane.py — Gmail-Inspired Message List Pane.

Designed according to Gmail desktop message list reference:
- Compact horizontal message rows:
  * Checkbox and star control
  * Sender column (bold if unread)
  * Inline Subject and snippet preview (snippet in muted grey #5F6368)
  * Attachment paperclip icon when applicable
  * Security indicator badge (Verified PQC, Caution, Standard)
  * Right-aligned date/time timestamp
  * Hover highlight (#F2F6FC) and selected state (#D3E3FD)
- Top Mailbox Toolbar:
  * Select-all control
  * Refresh, Mark Read, Mark Unread, Delete actions
  * Pagination label: 1–50 of ...
- Category Tabs: Primary (with blue underline), Updates
- Dual-theme reactive palette support (Light & Dark).
- 100% backward-compatible signals and method contracts.
"""

from __future__ import annotations

from email.utils import parsedate_to_datetime
import time
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
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
from ui.design_system import C, EmptyState, SearchInput, ThemeManager
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

        import datetime
        msg_date = datetime.datetime.fromtimestamp(ts)
        today = datetime.datetime.now().date()
        diff = time.time() - ts

        if msg_date.date() == today:
            return msg_date.strftime("%I:%M %p").lstrip("0")
        elif msg_date.date() == today - datetime.timedelta(days=1):
            return "Yesterday"
        elif diff < 7 * 86400:
            return msg_date.strftime("%a")
        elif msg_date.year == today.year:
            return msg_date.strftime("%b %d")
        else:
            return msg_date.strftime("%m/%d/%Y")
    except Exception:
        return date_str[:12] if date_str else ""


class MessageCardWidget(QWidget):
    """
    Gmail-style horizontal single-row message item.
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
        self.indicator = indicator
        self.has_attachments = has_attachments

        p = ThemeManager.get().palette

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        # 1. Checkbox
        self.checkbox = QCheckBox()
        self.checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.checkbox)

        # 2. Star
        self.star_lbl = QLabel("☆")
        self.star_lbl.setStyleSheet(f"color: {p.text_muted}; font-size: 15px; background: transparent;")
        layout.addWidget(self.star_lbl)

        # 3. Sender Name
        sender_weight = 700 if not seen else 400
        sender_color = p.text_primary if not seen else p.text_secondary
        self.sender_lbl = QLabel(sender)
        self.sender_lbl.setFixedWidth(160)
        self.sender_lbl.setStyleSheet(
            f"color: {sender_color}; font-size: 13px; font-weight: {sender_weight}; background: transparent;"
        )
        layout.addWidget(self.sender_lbl)

        # 4. Subject + Snippet inline (Subject in primary, Snippet in muted gray)
        clean_snippet = sanitize_snippet(snippet)
        sub_weight = 700 if not seen else 400

        self.subject_lbl = QLabel(subject or "(No Subject)")
        self.subject_lbl.setStyleSheet(
            f"color: {p.text_primary}; font-size: 13px; font-weight: {sub_weight}; background: transparent;"
        )
        layout.addWidget(self.subject_lbl)

        dash_lbl = QLabel("—")
        dash_lbl.setStyleSheet(f"color: {p.text_muted}; font-size: 13px; background: transparent;")
        layout.addWidget(dash_lbl)

        self.snippet_lbl = QLabel(clean_snippet)
        self.snippet_lbl.setStyleSheet(f"color: {p.text_secondary}; font-size: 13px; background: transparent;")
        layout.addWidget(self.snippet_lbl, stretch=1)

        # 5. Attachment Clip Badge
        if has_attachments:
            self.clip_lbl = QLabel("📎")
            self.clip_lbl.setStyleSheet(f"color: {p.text_secondary}; font-size: 13px; background: transparent;")
            layout.addWidget(self.clip_lbl)

        # 6. Security Indicator Pill
        if indicator:
            self.security_pill = SecurityPill(indicator)
            layout.addWidget(self.security_pill)

        # 7. Date (right aligned)
        date_weight = 700 if not seen else 400
        self.date_lbl = QLabel(format_message_date(date_str))
        self.date_lbl.setFixedWidth(75)
        self.date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.date_lbl.setStyleSheet(
            f"color: {p.text_secondary}; font-size: 12px; font-weight: {date_weight}; background: transparent;"
        )
        layout.addWidget(self.date_lbl)


class MessageListPane(QFrame):
    """
    Gmail-style middle message list pane with toolbar, category tabs, and horizontal rows.
    """

    message_selected = pyqtSignal(object)       # Emits item_key when message clicked
    message_activated = pyqtSignal(object)      # Emits item_key when double-clicked
    refresh_requested = pyqtSignal()
    older_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(380)
        self._items_data: list[tuple[Any, dict[str, Any]]] = []
        self._filter_mode: str = "all"

        ThemeManager.get().theme_changed.connect(self._apply_theme)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Top Mailbox Toolbar (Gmail style)
        self.toolbar = QFrame()
        tb_layout = QHBoxLayout(self.toolbar)
        tb_layout.setContentsMargins(14, 8, 14, 8)
        tb_layout.setSpacing(10)

        self.select_all_cb = QCheckBox()
        self.select_all_cb.setToolTip("Select all")
        tb_layout.addWidget(self.select_all_cb)

        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setFixedSize(28, 28)
        self.refresh_btn.setToolTip("Refresh (Ctrl+R)")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        tb_layout.addWidget(self.refresh_btn)

        self.mark_read_btn = QPushButton("✉️")
        self.mark_read_btn.setFixedSize(28, 28)
        self.mark_read_btn.setToolTip("Mark as read")
        self.mark_read_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        tb_layout.addWidget(self.mark_read_btn)

        self.delete_btn = QPushButton("🗑️")
        self.delete_btn.setFixedSize(28, 28)
        self.delete_btn.setToolTip("Delete")
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        tb_layout.addWidget(self.delete_btn)

        tb_layout.addStretch()

        # Pagination & info
        self.count_lbl = QLabel("")
        self.count_lbl.setStyleSheet("font-size: 12px; background: transparent;")
        tb_layout.addWidget(self.count_lbl)

        layout.addWidget(self.toolbar)

        # Hidden search input maintained for backward-compatibility with tests
        self.search_input = SearchInput(placeholder="Search messages…")
        self.search_input.setVisible(False)
        self.search_input.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_input)

        # 2. Category Tabs (Primary, Updates)
        self.cat_bar = QFrame()
        cat_layout = QHBoxLayout(self.cat_bar)
        cat_layout.setContentsMargins(14, 0, 14, 0)
        cat_layout.setSpacing(16)

        self.all_tab = QPushButton("📥  Primary")
        self.all_tab.setCheckable(True)
        self.all_tab.setChecked(True)
        self.all_tab.setCursor(Qt.CursorShape.PointingHandCursor)
        self.all_tab.clicked.connect(lambda: self._set_filter("all"))

        self.unread_tab = QPushButton("Unread")
        self.unread_tab.setCheckable(True)
        self.unread_tab.setChecked(False)
        self.unread_tab.setCursor(Qt.CursorShape.PointingHandCursor)
        self.unread_tab.clicked.connect(lambda: self._set_filter("unread"))

        self.secure_tab = QPushButton("🛡️ Quantum Secured")
        self.secure_tab.setCheckable(True)
        self.secure_tab.setChecked(False)
        self.secure_tab.setCursor(Qt.CursorShape.PointingHandCursor)
        self.secure_tab.clicked.connect(lambda: self._set_filter("secure"))

        self.attach_tab = QPushButton("📎 Files")
        self.attach_tab.setCheckable(True)
        self.attach_tab.setChecked(False)
        self.attach_tab.setCursor(Qt.CursorShape.PointingHandCursor)
        self.attach_tab.clicked.connect(lambda: self._set_filter("attachments"))

        cat_layout.addWidget(self.all_tab)
        cat_layout.addWidget(self.unread_tab)
        cat_layout.addWidget(self.secure_tab)
        cat_layout.addWidget(self.attach_tab)
        cat_layout.addStretch()

        layout.addWidget(self.cat_bar)

        # Divider below category tabs
        cat_divider = QFrame()
        cat_divider.setFrameShape(QFrame.Shape.HLine)
        cat_divider.setStyleSheet(f"background-color: {ThemeManager.get().palette.border_subtle}; max-height: 1px;")
        layout.addWidget(cat_divider)

        # 3. Message List Widget
        self.list_widget = QListWidget()
        self.list_widget.setFrameShape(QFrame.Shape.NoFrame)
        self.list_widget.currentItemChanged.connect(self._on_item_selected)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_widget)

        # Empty State Placeholder
        self.empty_state = EmptyState("📬", "Your inbox is clear", "No messages found in this category.")
        self.empty_state.setVisible(False)
        layout.addWidget(self.empty_state)

        # 4. Older Button
        self.older_btn = QPushButton("Older messages")
        self.older_btn.setVisible(False)
        self.older_btn.clicked.connect(self.older_requested.emit)
        layout.addWidget(self.older_btn)

        # Folder title alias
        self.folder_title = QLabel("Inbox")
        self.folder_title.setVisible(False)

        self._apply_theme()

    def _apply_theme(self) -> None:
        p = ThemeManager.get().palette
        self.setStyleSheet(
            f"MessageListPane {{ background-color: {p.bg_surface}; border-right: 1px solid {p.border_subtle}; }}"
        )
        self.toolbar.setStyleSheet(
            f"QFrame {{ background-color: {p.bg_surface}; border-bottom: 1px solid {p.border_subtle}; }}"
        )
        self.count_lbl.setStyleSheet(f"color: {p.text_secondary}; font-size: 12px; background: transparent;")

        tool_btn_style = (
            f"QPushButton {{ background-color: transparent; border: none; border-radius: 14px; color: {p.text_secondary}; font-size: 13px; }} "
            f"QPushButton:hover {{ background-color: {p.bg_card_hover}; color: {p.text_primary}; }}"
        )
        self.refresh_btn.setStyleSheet(tool_btn_style)
        self.mark_read_btn.setStyleSheet(tool_btn_style)
        self.delete_btn.setStyleSheet(tool_btn_style)

        # Gmail Category Tab styling: active tab has blue text (#0B57D0) and 2px solid bottom underline
        cat_btn_style = (
            f"QPushButton {{ background-color: transparent; color: {p.text_secondary}; border: none; "
            f"border-bottom: 2px solid transparent; padding: 10px 16px; font-size: 13px; font-weight: 600; border-radius: 0; }} "
            f"QPushButton:hover {{ color: {p.text_primary}; background-color: {p.bg_card_hover}; }} "
            f"QPushButton:checked {{ color: {p.accent}; border-bottom: 2px solid {p.accent}; font-weight: 700; }}"
        )
        self.all_tab.setStyleSheet(cat_btn_style)
        self.unread_tab.setStyleSheet(cat_btn_style)
        self.secure_tab.setStyleSheet(cat_btn_style)
        self.attach_tab.setStyleSheet(cat_btn_style)

        # Gmail message list items: thin border, hover #F2F6FC, selection #D3E3FD
        self.list_widget.setStyleSheet(
            f"QListWidget {{ background-color: {p.bg_surface}; outline: none; border: none; }} "
            f"QListWidget::item {{ border-bottom: 1px solid {p.border_subtle}; padding: 0; }} "
            f"QListWidget::item:hover {{ background-color: {p.bg_card_hover}; }} "
            f"QListWidget::item:selected {{ background-color: {p.bg_card_selected}; }}"
        )

    def _set_filter(self, mode: str) -> None:
        self._filter_mode = mode
        self.all_tab.setChecked(mode == "all")
        self.unread_tab.setChecked(mode == "unread")
        self.secure_tab.setChecked(mode == "secure")
        self.attach_tab.setChecked(mode == "attachments")
        self._apply_filters()

    def _set_filter_tab(self, unread_only: bool) -> None:
        self._set_filter("unread" if unread_only else "all")

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
        self.folder_title.setText(name)
        if total_count > 0:
            if unread_count > 0:
                self.count_lbl.setText(f"1–{total_count} of {total_count} ({unread_count} unread)")
            else:
                self.count_lbl.setText(f"1–{total_count} of {total_count}")
        else:
            self.count_lbl.setText("0 messages")

    def set_messages(self, messages_data: list[tuple[Any, dict[str, Any]]]) -> None:
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

            if self._filter_mode == "unread" and seen:
                continue
            if self._filter_mode == "secure" and (not indicator or indicator.badge_level != BadgeLevel.SECURE):
                continue
            if self._filter_mode == "attachments" and not has_attachments:
                continue

            if query:
                text_corpus = f"{sender} {subject} {snippet}".lower()
                if query not in text_corpus:
                    continue

            item = QListWidgetItem(self.list_widget)
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
            item.setData(Qt.ItemDataRole.UserRole, item_key)
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, card)
            visible_count += 1

        self.list_widget.blockSignals(False)
        self.empty_state.setVisible(visible_count == 0)
        self.list_widget.setVisible(visible_count > 0)
