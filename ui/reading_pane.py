"""
Right Reading Pane Component (WS-05).

Provides the right reading pane of the three-pane desktop layout:
- Inline message reader: opens selected messages directly without separate popups
- Security banner presenting plain-language verified/caution/alert trust state
- Header metadata: Subject, Sender, Recipients (To/Cc), Date
- Quick message action bar (Reply, Forward, Mark Read/Unread, Delete)
- Safe plain-text message body rendering (zero script execution, zero remote assets)
- Modern attachment cards with filename, formatted size, and explicit Save/Open actions
- Defensive attachment security: never auto-executes files
- Elegant empty state placeholder when no message is selected
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.security_indicators import BadgeLevel, SecurityIndicator
from ui.design_system import C, EmptyState
from ui.security_badge_widget import SecurityBanner


def format_file_size(num_bytes: int) -> str:
    """Format bytes into clean human-readable KB or MB."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    else:
        return f"{num_bytes / (1024 * 1024):.1f} MB"


class AttachmentCard(QFrame):
    """Card widget representing an attachment with explicit Save / Open actions."""

    save_requested = pyqtSignal(int)    # Emits attachment index
    open_requested = pyqtSignal(int)    # Emits attachment index

    def __init__(
        self,
        index: int,
        name: str,
        size_bytes: int,
        media_type: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.index = index
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            f"AttachmentCard {{ background-color: {C['bg_card']}; border: 1px solid {C['border']}; "
            f"border-radius: 6px; padding: 6px; }} AttachmentCard:hover {{ border-color: {C['accent_muted']}; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        # File Icon based on extension
        ext = Path(name).suffix.lower()
        if ext in (".pdf",):
            icon_str = "📄"
        elif ext in (".png", ".jpg", ".jpeg", ".gif"):
            icon_str = "🖼️"
        elif ext in (".txt", ".md", ".csv"):
            icon_str = "📝"
        else:
            icon_str = "📦"

        icon_lbl = QLabel(icon_str)
        icon_lbl.setStyleSheet("font-size: 16px;")
        layout.addWidget(icon_lbl)

        # Name and size details
        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"color: {C['text_primary']}; font-size: 12px; font-weight: 600;")
        info_col.addWidget(name_lbl)

        size_text = format_file_size(size_bytes)
        if media_type:
            size_text += f" · {media_type}"
        size_lbl = QLabel(size_text)
        size_lbl.setStyleSheet(f"color: {C['text_tertiary']}; font-size: 11px;")
        info_col.addWidget(size_lbl)

        layout.addLayout(info_col)
        layout.addStretch()

        # Action Buttons
        self.save_btn = QPushButton("💾 Save as…")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet(
            f"QPushButton {{ background-color: {C['bg_hover']}; color: {C['text_primary']}; "
            f"border: 1px solid {C['border']}; border-radius: 4px; padding: 4px 10px; font-size: 11px; }} "
            f"QPushButton:hover {{ background-color: {C['accent_muted']}; color: {C['accent_light']}; border-color: {C['accent']}; }}"
        )
        self.save_btn.clicked.connect(lambda: self.save_requested.emit(self.index))
        layout.addWidget(self.save_btn)

        self.open_btn = QPushButton("📂 Open")
        self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_btn.setStyleSheet(
            f"QPushButton {{ background-color: {C['bg_hover']}; color: {C['text_primary']}; "
            f"border: 1px solid {C['border']}; border-radius: 4px; padding: 4px 10px; font-size: 11px; }} "
            f"QPushButton:hover {{ background-color: {C['accent_muted']}; color: {C['accent_light']}; border-color: {C['accent']}; }}"
        )
        self.open_btn.clicked.connect(lambda: self.open_requested.emit(self.index))
        layout.addWidget(self.open_btn)


class ReadingPane(QFrame):
    """
    Right inline message reader pane.
    """

    reply_requested = pyqtSignal()
    forward_requested = pyqtSignal()
    mark_seen_requested = pyqtSignal(bool)   # seen=True or seen=False
    delete_requested = pyqtSignal()
    export_attachment_requested = pyqtSignal(int, str)  # (attachment_index, destination_path)
    open_attachment_requested = pyqtSignal(int)         # (attachment_index)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(380)
        self.setStyleSheet(f"ReadingPane {{ background-color: {C['bg_base']}; }}")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Empty state container (shown when no message selected)
        self.empty_container = QWidget()
        empty_layout = QVBoxLayout(self.empty_container)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_widget = EmptyState("📬", "No message selected", "Select a message from the list to view its contents.")
        empty_layout.addWidget(self.empty_widget)
        main_layout.addWidget(self.empty_container)

        # 2. Content container (shown when message is loaded)
        self.content_container = QWidget()
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(16, 14, 16, 14)
        content_layout.setSpacing(12)

        # Action Toolbar (Top)
        self.toolbar = QHBoxLayout()
        self.toolbar.setSpacing(6)

        self.reply_btn = QPushButton("↩️ Reply")
        self.reply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reply_btn.setStyleSheet(
            f"QPushButton {{ background-color: {C['bg_card']}; color: {C['text_primary']}; "
            f"border: 1px solid {C['border']}; border-radius: 5px; padding: 5px 12px; font-size: 12px; font-weight: 600; }} "
            f"QPushButton:hover {{ background-color: {C['bg_hover']}; }}"
        )
        self.reply_btn.clicked.connect(self.reply_requested.emit)
        self.toolbar.addWidget(self.reply_btn)

        self.forward_btn = QPushButton("↪️ Forward")
        self.forward_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.forward_btn.setStyleSheet(
            f"QPushButton {{ background-color: {C['bg_card']}; color: {C['text_primary']}; "
            f"border: 1px solid {C['border']}; border-radius: 5px; padding: 5px 12px; font-size: 12px; font-weight: 600; }} "
            f"QPushButton:hover {{ background-color: {C['bg_hover']}; }}"
        )
        self.forward_btn.clicked.connect(self.forward_requested.emit)
        self.toolbar.addWidget(self.forward_btn)

        self.mark_unread_btn = QPushButton("📩 Mark Unread")
        self.mark_unread_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mark_unread_btn.setStyleSheet(
            f"QPushButton {{ background-color: {C['bg_card']}; color: {C['text_secondary']}; "
            f"border: 1px solid {C['border']}; border-radius: 5px; padding: 5px 12px; font-size: 12px; }} "
            f"QPushButton:hover {{ background-color: {C['bg_hover']}; color: {C['text_primary']}; }}"
        )
        self.mark_unread_btn.clicked.connect(lambda: self.mark_seen_requested.emit(False))
        self.toolbar.addWidget(self.mark_unread_btn)

        self.toolbar.addStretch()

        self.delete_btn = QPushButton("🗑️")
        self.delete_btn.setToolTip("Delete message")
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.setStyleSheet(
            f"QPushButton {{ background-color: {C['bg_card']}; color: {C['offline']}; "
            f"border: 1px solid {C['border']}; border-radius: 5px; padding: 5px 10px; font-size: 12px; }} "
            f"QPushButton:hover {{ background-color: #450A0A; }}"
        )
        self.delete_btn.clicked.connect(self.delete_requested.emit)
        self.toolbar.addWidget(self.delete_btn)

        content_layout.addLayout(self.toolbar)

        # Security Banner
        self.security_banner = SecurityBanner()
        content_layout.addWidget(self.security_banner)

        # Subject Title
        self.subject_lbl = QLabel()
        self.subject_lbl.setWordWrap(True)
        self.subject_lbl.setStyleSheet(f"color: {C['text_primary']}; font-size: 18px; font-weight: 800; line-height: 1.3;")
        content_layout.addWidget(self.subject_lbl)

        # Header Info Card (Sender, Recipients, Date)
        header_card = QFrame()
        header_card.setStyleSheet(
            f"QFrame {{ background-color: {C['bg_card']}; border: 1px solid {C['border']}; border-radius: 6px; padding: 10px; }}"
        )
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(8, 8, 8, 8)
        header_layout.setSpacing(4)

        # Sender row
        sender_row = QHBoxLayout()
        self.from_lbl = QLabel("From:")
        self.from_lbl.setStyleSheet(f"color: {C['text_secondary']}; font-size: 12px; font-weight: 600; width: 45px;")
        sender_row.addWidget(self.from_lbl)

        self.sender_val = QLabel()
        self.sender_val.setStyleSheet(f"color: {C['text_primary']}; font-size: 12px; font-weight: 600;")
        sender_row.addWidget(self.sender_val)
        sender_row.addStretch()

        self.date_val = QLabel()
        self.date_val.setStyleSheet(f"color: {C['text_secondary']}; font-size: 11px;")
        sender_row.addWidget(self.date_val)
        header_layout.addLayout(sender_row)

        # Recipients row
        to_row = QHBoxLayout()
        self.to_lbl = QLabel("To:")
        self.to_lbl.setStyleSheet(f"color: {C['text_secondary']}; font-size: 12px; font-weight: 600; width: 45px;")
        to_row.addWidget(self.to_lbl)

        self.recipients_val = QLabel()
        self.recipients_val.setStyleSheet(f"color: {C['text_secondary']}; font-size: 12px;")
        self.recipients_val.setWordWrap(True)
        to_row.addWidget(self.recipients_val)
        to_row.addStretch()
        header_layout.addLayout(to_row)

        content_layout.addWidget(header_card)

        # Message Body (Safe Plain Text Viewer)
        self.body_view = QPlainTextEdit()
        self.body_view.setReadOnly(True)
        self.body_view.setFrameShape(QFrame.Shape.NoFrame)
        self.body_view.setTabChangesFocus(True)
        self.body_view.setStyleSheet(
            f"QPlainTextEdit {{ background-color: {C['bg_base']}; color: {C['text_primary']}; "
            f"font-size: 13px; line-height: 1.6; border: none; padding: 4px; }} "
            f"QPlainTextEdit:focus {{ outline: none; }}"
        )
        content_layout.addWidget(self.body_view, stretch=1)

        # Attachments Section (Scrollable list of cards)
        self.attachments_container = QWidget()
        self.attachments_layout = QVBoxLayout(self.attachments_container)
        self.attachments_layout.setContentsMargins(0, 0, 0, 0)
        self.attachments_layout.setSpacing(6)

        self.attachments_header = QLabel("📎 Attachments")
        self.attachments_header.setStyleSheet(f"color: {C['text_secondary']}; font-size: 12px; font-weight: 700;")
        self.attachments_layout.addWidget(self.attachments_header)

        self.attachments_card_layout = QVBoxLayout()
        self.attachments_card_layout.setSpacing(6)
        self.attachments_layout.addLayout(self.attachments_card_layout)

        content_layout.addWidget(self.attachments_container)

        main_layout.addWidget(self.content_container)

        # Default: show empty container
        self.clear()

    def clear(self) -> None:
        """Clear message and show empty state placeholder."""
        self.current_display = None
        self.current_attachments = []
        self.subject_lbl.clear()
        self.sender_val.clear()
        self.recipients_val.clear()
        self.date_val.clear()
        self.body_view.clear()
        self._clear_attachment_cards()
        self.attachments_container.setVisible(False)
        self.content_container.setVisible(False)
        self.empty_container.setVisible(True)

    def _clear_attachment_cards(self) -> None:
        while self.attachments_card_layout.count():
            item = self.attachments_card_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def show_message(
        self,
        subject: str,
        sender: str,
        recipients: str,
        date_str: str,
        body: str,
        indicator: SecurityIndicator | None = None,
        attachments: list[dict[str, Any]] | None = None,
        raw_display: Any | None = None,
    ) -> None:
        """
        Render an opened message inside the inline reading pane.
        """
        self.current_display = raw_display
        self.current_attachments = attachments or []

        self.subject_lbl.setText(subject or "(No Subject)")
        self.sender_val.setText(sender)
        self.recipients_val.setText(recipients or "You")
        self.date_val.setText(date_str)
        self.body_view.setPlainText(body)

        # Security indicator
        if indicator:
            self.security_banner.set_indicator(indicator)
            self.security_banner.setVisible(True)
        else:
            self.security_banner.setVisible(False)

        # Attachments
        self._clear_attachment_cards()
        if self.current_attachments:
            self.attachments_header.setText(f"📎 Attachments ({len(self.current_attachments)})")
            for idx, a in enumerate(self.current_attachments):
                name = a.get("name", f"attachment_{idx+1}")
                size = a.get("size", len(a.get("data", b"")))
                mtype = a.get("media_type", "application/octet-stream")
                card = AttachmentCard(idx, name, size, mtype)
                card.save_requested.connect(self._on_save_attachment)
                card.open_requested.connect(self.open_attachment_requested.emit)
                self.attachments_card_layout.addWidget(card)
            self.attachments_container.setVisible(True)
        else:
            self.attachments_container.setVisible(False)

        self.empty_container.setVisible(False)
        self.content_container.setVisible(True)

    def _on_save_attachment(self, index: int) -> None:
        """Prompt user with file dialog for save destination."""
        if not (0 <= index < len(self.current_attachments)):
            return
        att = self.current_attachments[index]
        default_name = att.get("name", "attachment")
        path, _ = QFileDialog.getSaveFileName(self, "Save Attachment", default_name)
        if path:
            self.export_attachment_requested.emit(index, path)
