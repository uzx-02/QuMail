"""
Cryptographic Subkey Lifecycle & Rotation Manager (WS-02).

Manages:
1. Subkey validity period checks and upcoming expiration warnings (< 30 days).
2. Key revocation inspection and immediate enforcement.
3. Distinguishing authorized subkey rotation from unauthorized root key replacement.
4. Historical verification preservation (evaluating signature validity with respect to message date).
5. Preventing unverified replacement keys from silently inheriting verified trust.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import time
from typing import Callable

from core.logging_config import get_logger

logger = get_logger("key_lifecycle")

EXPIRATION_WARNING_SECONDS = 30 * 86400  # 30 days


class KeyStatus(str, Enum):
    ACTIVE = "active"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"
    REVOKED = "revoked"
    INVALID = "invalid"


class RotationType(str, Enum):
    AUTHORIZED_SUBKEY_ROTATION = "authorized_subkey_rotation"
    UNAUTHORIZED_ROOT_REPLACEMENT = "unauthorized_root_replacement"
    IDENTICAL_KEY = "identical_key"


@dataclass(frozen=True)
class ExpirationCheckResult:
    status: KeyStatus
    days_remaining: int
    expires_at_timestamp: int | None = None
    warning_message: str = ""

    @property
    def needs_warning(self) -> bool:
        return self.status == KeyStatus.EXPIRING_SOON


def evaluate_key_expiration(
    expires_at_timestamp: int | None,
    current_time: float | None = None,
    warning_threshold_seconds: float = EXPIRATION_WARNING_SECONDS,
) -> ExpirationCheckResult:
    """Evaluate subkey expiration relative to current or specified time."""
    if expires_at_timestamp is None or expires_at_timestamp <= 0:
        return ExpirationCheckResult(status=KeyStatus.ACTIVE, days_remaining=9999)

    now = time.time() if current_time is None else current_time
    remaining_seconds = expires_at_timestamp - now

    if remaining_seconds <= 0:
        return ExpirationCheckResult(
            status=KeyStatus.EXPIRED,
            days_remaining=0,
            expires_at_timestamp=expires_at_timestamp,
            warning_message="Cryptographic subkey has expired and must be renewed.",
        )

    days_remaining = int(round(remaining_seconds / 86400.0))
    if remaining_seconds < warning_threshold_seconds:
        return ExpirationCheckResult(
            status=KeyStatus.EXPIRING_SOON,
            days_remaining=days_remaining,
            expires_at_timestamp=expires_at_timestamp,
            warning_message=f"Cryptographic subkey will expire in {days_remaining} days. Please rotate key.",
        )

    return ExpirationCheckResult(
        status=KeyStatus.ACTIVE,
        days_remaining=days_remaining,
        expires_at_timestamp=expires_at_timestamp,
    )


def evaluate_key_transition(
    existing_fingerprint: str,
    new_fingerprint: str,
    existing_signing_subkey: str,
    new_signing_subkey: str,
    existing_encryption_subkey: str,
    new_encryption_subkey: str,
    retired_subkeys: list[str] | None = None,
) -> RotationType:
    """
    Distinguish authorized subkey rotation from unauthorized root replacement.

    Authorized Subkey Rotation:
      - Root fingerprint remains identical.
      - Signing or encryption subkey changed.
      - Replaced subkeys are recorded in retired_subkeys.

    Unauthorized Replacement:
      - Root fingerprint changed without an authorized cross-certification.
      - MUST trigger CHANGED_BLOCKED.
    """
    retired = set(retired_subkeys or [])

    if existing_fingerprint.lower() != new_fingerprint.lower():
        # Root key itself changed -> Unexpected replacement!
        logger.warning(
            "Root fingerprint mismatch detected for contact: %s vs %s (unauthorized replacement)",
            existing_fingerprint,
            new_fingerprint,
        )
        return RotationType.UNAUTHORIZED_ROOT_REPLACEMENT

    # Same root key
    subkeys_changed = (
        existing_signing_subkey.lower() != new_signing_subkey.lower() or
        existing_encryption_subkey.lower() != new_encryption_subkey.lower()
    )

    if subkeys_changed:
        # Check that new subkeys were not previously retired (no rollback to old subkeys)
        if new_signing_subkey.lower() in retired or new_encryption_subkey.lower() in retired:
            logger.error("Attempt to rotate to previously retired subkey!")
            return RotationType.UNAUTHORIZED_ROOT_REPLACEMENT

        logger.info("Authorized subkey rotation confirmed under root %s", existing_fingerprint)
        return RotationType.AUTHORIZED_SUBKEY_ROTATION

    return RotationType.IDENTICAL_KEY


def is_signature_historically_valid(
    message_timestamp_utc: int,
    key_valid_from: int,
    key_expires_at: int | None,
    revocation_timestamp: int | None = None,
) -> bool:
    """
    RFC 4880 / RFC 9580 time-aware historical signature validity check.

    A message signed while a key was active and valid remains historically authentic,
    provided the message was signed BEFORE any revocation or expiration took place.
    """
    if message_timestamp_utc < key_valid_from:
        return False  # Message predates the key's creation

    if key_expires_at and message_timestamp_utc > key_expires_at:
        return False  # Message was signed after key expired

    if revocation_timestamp and message_timestamp_utc > revocation_timestamp:
        return False  # Message was signed after key was revoked

    return True
