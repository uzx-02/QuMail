"""
transport/oauth2_yahoo.py — Yahoo OAuth2 module (PURGED / DISABLED).
"""

from __future__ import annotations


class YahooAuthError(Exception):
    """Raised when Yahoo OAuth operations are attempted while purged."""
    pass


def get_access_token() -> str:
    raise YahooAuthError("Yahoo OAuth is permanently disabled.")


def revoke_token() -> None:
    pass
