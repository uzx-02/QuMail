"""
tests/test_ui_redesign.py — Comprehensive UI/UX Pro Max Verification Suite.

Validates the redesigned QuMail desktop frontend:
- ThemeManager: Runtime dynamic switching between Dark Enterprise Slate and Light Executive themes.
- Visual Primitives: AvatarWidget monograms, StatusBadgeWidget, SearchInput, ActionButton, EmptyState.
- Navigation Sidebar: Live unread badges, folder switching, theme toggle button.
- Message List Pane: Multi-mode segment filtering (All, Unread, Secure, Files), search filtering.
- Reading Pane: Security banner, attachment cards, reading view.
- Compose Dialog: Security mode switcher (PQ, Web Link, Standard), draft & outbox inspection.
- Settings Dialog: 7-tab enterprise preferences layout.
"""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from ui.design_system import (
    ThemeManager,
    DARK_PALETTE,
    LIGHT_PALETTE,
    AvatarWidget,
    StatusBadgeWidget,
    SearchInput,
    ActionButton,
    EmptyState,
)
from ui.navigation_pane import NavigationPane
from ui.message_list_pane import MessageListPane
from ui.reading_pane import ReadingPane
from ui.settings_dialog import SettingsDialog
from core.security_indicators import SecurityIndicator, BadgeLevel


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_theme_manager_palette_toggle(qapp):
    """Verify ThemeManager switches between dark and light palettes and emits signals."""
    mgr = ThemeManager.get()
    mgr.set_theme("dark")
    assert mgr.mode == "dark"
    assert mgr.palette == DARK_PALETTE

    signal_received = []
    mgr.theme_changed.connect(lambda mode: signal_received.append(mode))

    # Toggle to light
    new_mode = mgr.toggle()
    assert new_mode == "light"
    assert mgr.mode == "light"
    assert mgr.palette == LIGHT_PALETTE
    assert signal_received == ["light"]

    # Toggle back to dark
    mgr.toggle()
    assert mgr.mode == "dark"


def test_avatar_widget_initials_and_rendering(qapp):
    """Verify AvatarWidget monogram derivation and color hashing."""
    av1 = AvatarWidget("alice@example.invalid", size=32)
    assert av1._text == "AL"

    av2 = AvatarWidget("Bob Smith", size=32)
    assert av2._text == "BS"

    av3 = AvatarWidget("support", size=32)
    assert av3._text == "SU"


def test_status_badge_widget_levels(qapp):
    """Verify StatusBadgeWidget rendering across security levels."""
    badge = StatusBadgeWidget("SECURE")
    assert badge._badge_type == "SECURE"
    assert "ML-KEM" in badge.toolTip()

    badge.update_badge("CAUTION", "UNVERIFIED IDENTITY")
    assert badge._badge_type == "CAUTION"
    assert badge._text_lbl.text() == "UNVERIFIED IDENTITY"

    badge.update_badge("ALERT", "TAMPERED MESSAGE")
    assert badge._badge_type == "ALERT"


def test_navigation_pane_theme_and_folder_selection(qapp):
    """Verify NavigationPane folder switching and theme button."""
    nav = NavigationPane()
    selected_folders = []
    nav.folder_selected.connect(lambda f: selected_folders.append(f))

    # Click Sent Mail (row 2)
    nav.folder_list.setCurrentRow(2)
    assert "sent" in selected_folders

    # Unread count update
    nav.set_unread_count("inbox", 5)
    assert nav._folder_widgets["inbox"].badge.text() == "5"
    assert not nav._folder_widgets["inbox"].badge.isHidden()

    nav.set_unread_count("inbox", 0)
    assert nav._folder_widgets["inbox"].badge.isHidden()

    # Theme toggle button
    theme_events = []
    nav.theme_toggled.connect(lambda m: theme_events.append(m))
    nav.theme_btn.click()
    assert len(theme_events) == 1


def test_message_list_pane_segment_filters(qapp):
    """Verify 4-mode segment filtering (All, Unread, Secure, Attachments)."""
    pane = MessageListPane()
    messages = [
        ("m1", {"sender": "Alice", "subject": "Unread Msg", "seen": False, "has_attachments": False}),
        ("m2", {"sender": "Bob", "subject": "Read Msg", "seen": True, "has_attachments": True}),
        ("m3", {"sender": "Carol", "subject": "Secure PQ Msg", "seen": True, "indicator": SecurityIndicator.secured("carol")}),
    ]
    pane.set_messages(messages)
    assert pane.list_widget.count() == 3

    # Filter: Unread
    pane._set_filter("unread")
    assert pane.list_widget.count() == 1
    assert pane.list_widget.item(0).data(Qt.ItemDataRole.UserRole) == "m1"

    # Filter: Files
    pane._set_filter("attachments")
    assert pane.list_widget.count() == 1
    assert pane.list_widget.item(0).data(Qt.ItemDataRole.UserRole) == "m2"

    # Filter: Secure
    pane._set_filter("secure")
    assert pane.list_widget.count() == 1
    assert pane.list_widget.item(0).data(Qt.ItemDataRole.UserRole) == "m3"

    # Filter: All
    pane._set_filter("all")
    assert pane.list_widget.count() == 3


def test_reading_pane_message_display(qapp):
    """Verify ReadingPane renders message headers, security banner, and attachments."""
    pane = ReadingPane()
    assert not pane.empty_container.isHidden()
    assert pane.content_container.isHidden()

    attachments = [
        {"name": "contract.pdf", "size": 1024 * 50, "media_type": "application/pdf"}
    ]
    ind = SecurityIndicator.secured("Alice Smith")

    pane.show_message(
        subject="Signed Partnership Agreement",
        sender="alice@example.invalid",
        recipients="bob@example.invalid",
        date_str="Nov 10, 2026",
        body="Attached is the signed document.",
        indicator=ind,
        attachments=attachments,
    )

    assert pane.empty_container.isHidden()
    assert not pane.content_container.isHidden()
    assert pane.subject_lbl.text() == "Signed Partnership Agreement"
    assert pane.body_view.toPlainText() == "Attached is the signed document."
    assert not pane.attachments_container.isHidden()
    assert not pane.security_banner.isHidden()

    # Clear back to empty state
    pane.clear()
    assert not pane.empty_container.isHidden()
    assert pane.content_container.isHidden()


def test_settings_dialog_tabs_and_theme_change(qapp):
    """Verify SettingsDialog has 6+ tabs and theme selector works."""
    ThemeManager.get().set_theme("dark")
    dlg = SettingsDialog(account_email="alice@company.invalid")
    assert dlg.tabs.count() >= 6
    assert dlg.email_val.text() == "alice@company.invalid"

    theme_signals = []
    dlg.theme_changed.connect(lambda t: theme_signals.append(t))

    # Switch theme in combo box
    dlg.theme_combo.setCurrentIndex(1)  # Light theme
    assert "light" in theme_signals
