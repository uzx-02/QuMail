"""
Presentation-layer mapping for outbox operation states.

These labels are DISPLAY-ONLY. They do not change, intercept, or override the
backend State enum, durable SQLite records, or any service logic.

Usage:
    from ui.outbox_state_labels import label_for_state, color_for_state, icon_for_state
"""

from ui.design_system import OUTBOX_STATE_LABELS, OUTBOX_STATE_COLORS, OUTBOX_STATE_ICONS, C


def label_for_state(raw_state: str) -> str:
    """Return the employee-readable display label for a backend state string."""
    return OUTBOX_STATE_LABELS.get(raw_state, raw_state)


def color_for_state(raw_state: str) -> str:
    """Return the CSS hex colour appropriate for displaying the given state."""
    return OUTBOX_STATE_COLORS.get(raw_state, C["text_secondary"])


def icon_for_state(raw_state: str) -> str:
    """Return the Unicode emoji appropriate for the given state."""
    return OUTBOX_STATE_ICONS.get(raw_state, "\U0001f4e7")


def annotate_state(raw_state: str) -> str:
    """Return 'icon  label' for display in table cells or status bars."""
    return f"{icon_for_state(raw_state)}  {label_for_state(raw_state)}"
