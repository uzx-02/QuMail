"""Yahoo OAuth2 stub. Yahoo accounts are not supported; token requests raise."""

from __future__ import annotations


class YahooAuthError(Exception):
    """Raised when a Yahoo OAuth operation is requested."""
    pass


def get_access_token() -> str:
    raise YahooAuthError("Yahoo OAuth is permanently disabled.")


def revoke_token() -> None:
    pass
