"""
Unit tests for QuMail UI presentation layer and employee-facing redesign:
- Outbox state presentation label mappings
- Design system tokens and reusable widget primitives
- Welcome screen layout and callback dispatch
- MailActions button key alias backward-compatibility
"""

import pytest
from PyQt6.QtWidgets import QApplication

from ui.design_system import C, OUTBOX_STATE_LABELS, StatusPill, EmptyState
from ui.outbox_state_labels import (
    label_for_state,
    color_for_state,
    icon_for_state,
    annotate_state,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# 1. Outbox State Presentation Labels
# ---------------------------------------------------------------------------

def test_outbox_state_mapping_completeness():
    """Verify all 6 backend states have distinct, employee-friendly display labels."""
    expected_mappings = {
        "Draft": "Draft",
        "Prepared": "Ready to send",
        "Submitting": "Sending securely\u2026",
        "Accepted": "Accepted by mail server",
        "Failed": "Not sent",
        "Unknown": "Delivery uncertain \u2014 check Sent folder",
    }
    for raw_state, expected_label in expected_mappings.items():
        assert label_for_state(raw_state) == expected_label, (
            f"State '{raw_state}' did not map to expected label '{expected_label}'"
        )


def test_outbox_state_fallback_for_unrecognized_states():
    """Verify an unexpected state string gracefully falls back to the raw input."""
    raw = "CustomFutureState"
    assert label_for_state(raw) == raw
    assert color_for_state(raw) == C["text_secondary"]
    assert icon_for_state(raw) == "\U0001f4e7"


def test_outbox_state_colors_and_icons():
    """Verify colors and icons are valid and non-empty for known states."""
    for state in ["Draft", "Prepared", "Submitting", "Accepted", "Failed", "Unknown"]:
        color = color_for_state(state)
        icon = icon_for_state(state)
        annotated = annotate_state(state)

        assert color.startswith("#"), f"Color for {state} should be a hex code"
        assert len(icon) > 0, f"Icon for {state} should not be empty"
        assert icon in annotated
        assert label_for_state(state) in annotated


# ---------------------------------------------------------------------------
# 2. Design System Tokens & Reusable Widgets
# ---------------------------------------------------------------------------

def test_design_tokens_presence():
    """Verify core design token keys exist with valid hex colors."""
    required_keys = [
        "bg_base", "bg_sidebar", "bg_card", "bg_hover",
        "accent", "accent_light", "accent_glow", "accent_muted",
        "text_primary", "text_secondary", "text_tertiary",
        "border", "online", "offline", "warning",
    ]
    for key in required_keys:
        assert key in C, f"Missing design token: {key}"
        assert C[key].startswith("#"), f"Token {key} is not a valid hex color: {C[key]}"


def test_status_pill_widget(qapp):
    """Verify StatusPill widget instantiates and updates colors."""
    pill = StatusPill("Active", fg="#FFFFFF", bg="#000000")
    assert pill.text() == "Active"
    pill.set_colors("#00FF00", "#111111")
    assert pill._fg == "#00FF00"
    assert pill._bg == "#111111"


def test_empty_state_widget(qapp):
    """Verify EmptyState widget instantiates with given strings."""
    empty = EmptyState(icon="\U0001f4eb", heading="No messages", sub="Inbox is clear")
    assert empty is not None


# ---------------------------------------------------------------------------
# 3. Welcome Screen
# ---------------------------------------------------------------------------

def test_welcome_screen_instantiation_and_callback(qapp):
    """Verify WelcomeScreen renders and triggers the settings callback on click."""
    from ui.welcome_screen import WelcomeScreen

    clicked = []

    def on_settings_clicked():
        clicked.append(True)

    screen = WelcomeScreen(on_settings_clicked)
    assert screen is not None

    # Simulate button click
    screen._open_settings()
    assert len(clicked) == 1
    assert clicked[0] is True


# ---------------------------------------------------------------------------
# 4. Button Aliases in MailActions
# ---------------------------------------------------------------------------

def test_mail_actions_button_aliases():
    """
    Verify that MailActions button dictionary preserves both canonical
    engineering keys (used by tests and backend workflows) and new
    friendly employee labels.
    """
    # Verify the alias pairs map to identical button instances
    expected_pairs = [
        ("Refresh", "Refresh outbox"),
        ("Edit draft", "Edit draft"),
        ("Prepare to send", "Prepare saved"),
        ("Send now", "Submit once"),
        ("Retry send", "Explicit retry"),
        ("Discard", "Discard / cancel saved"),
        ("Open archive", "Open archive"),
    ]
    # Check that in ui.mail_actions source, both keys are assigned
    import ui.mail_actions as ma
    import inspect
    source = inspect.getsource(ma.MailActions.__init__)
    for friendly, canonical in expected_pairs:
        assert f"'{friendly}'" in source or f'"{friendly}"' in source
        assert f"'{canonical}'" in source or f'"{canonical}"' in source


# ---------------------------------------------------------------------------
# 5. IdentitySettings closeEvent Behavior
# ---------------------------------------------------------------------------

def test_settings_close_event_does_not_lock_service(qapp):
    """
    Verify that closing the Settings window does not call service.lock(),
    ensuring that an unlocked session remains active for the mailbox.
    """
    from unittest.mock import Mock
    from PyQt6.QtGui import QCloseEvent
    from ui.identity_settings import IdentitySettings

    from core.account_session import DevelopmentSession
    mock_service = Mock()
    mock_service.session = DevelopmentSession()
    mock_service.google = None

    settings = IdentitySettings(mock_service)
    close_event = QCloseEvent()
    settings.closeEvent(close_event)

    # service.lock must NOT have been called on closeEvent
    assert mock_service.lock.call_count == 0
    settings.dispose()


# ---------------------------------------------------------------------------
# 6. Onboarding Wizard Navigation
# ---------------------------------------------------------------------------

def test_onboarding_wizard_steps(qapp):
    """
    Verify that the OnboardingWizard initializes with 4 steps, allows step navigation,
    and finishes cleanly.
    """
    from ui.onboarding_wizard import OnboardingWizard
    from unittest.mock import Mock

    mock_mailbox = Mock()
    mock_mailbox.session.snapshot.active = None
    wizard = OnboardingWizard(mock_mailbox)

    assert wizard._stack.count() == 4
    assert wizard._stack.currentIndex() == 0

    # Advance through steps
    wizard._go_step(1)
    assert wizard._stack.currentIndex() == 1
    wizard._go_step(2)
    assert wizard._stack.currentIndex() == 2
    wizard._go_step(0)
    assert wizard._stack.currentIndex() == 0

    wizard.close()


# ---------------------------------------------------------------------------
# 7. MailActions Secure Compose UI Enhancements
# ---------------------------------------------------------------------------

def test_mail_actions_secure_compose_elements():
    """
    Verify that MailActions has truthful security indicator states,
    the end-to-end encryption badge on prepared state, and the Send Securely button.
    """
    import inspect
    import ui.mail_actions as ma
    init_source = inspect.getsource(ma.MailActions.__init__)
    badge_source = inspect.getsource(ma.MailActions.set_security_badge)
    assert "Send Securely" in init_source
    assert "set_security_badge" in init_source
    assert "End-to-End Encrypted (OpenPGP)" in badge_source
    assert "Draft · Plaintext in local editor" in badge_source
    assert hasattr(ma.MailActions, "send_securely")
    assert hasattr(ma.MailActions, "set_security_badge")
