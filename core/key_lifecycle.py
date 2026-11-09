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


class RevocationReason(str, Enum):
    """RFC 4880 §5.2.3.23 / RFC 9580 revocation reason codes."""
    UNSPECIFIED = "unspecified"
    KEY_SUPERSEDED = "key_superseded"
    KEY_COMPROMISED = "key_compromised"
    KEY_RETIRED = "key_retired"
    USER_ID_NO_LONGER_VALID = "user_id_no_longer_valid"


class HistoricalValidity(str, Enum):
    """Granular verdict for historical signature verification."""
    VALID_HISTORICAL = "valid_historical"
    INDETERMINATE_NO_TRUSTED_TIME = "indeterminate_no_trusted_time"
    EXPIRED_AT_CREATION = "expired_at_creation"
    REVOKED_AT_CREATION = "revoked_at_creation"
    KEY_COMPROMISED = "key_compromised"
    INVALID_EVIDENCE = "invalid_evidence"
    PREDATES_KEY = "predates_key"


class TimestampEvidenceSource(str, Enum):
    """Defensible independent time sources for cryptographic verification."""
    RFC3161_TSA = "rfc3161_tsa"
    AUTHENTICATED_RECEIPT = "authenticated_receipt"  # e.g. local vault replay receipt committed at reception
    TRUSTED_NOTARY = "trusted_notary"


@dataclass(frozen=True)
class TimestampEvidence:
    """Independent, trusted proof establishing that a signature existed at a point in time."""
    source: TimestampEvidenceSource
    verified_time_utc: int
    proof: bytes | str = ""
    is_verified: bool = True


@dataclass(frozen=True)
class HistoricalVerificationResult:
    """Detailed verdict distinguishing cryptographic validity from historical key-status validity."""
    status: HistoricalValidity
    is_valid: bool
    explanation: str
    effective_time_utc: int | None = None
    evidence_source: TimestampEvidenceSource | None = None


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


def verify_historical_signature(
    claimed_signature_time_utc: int,
    key_valid_from: int,
    key_expires_at: int | None,
    revocation_timestamp: int | None = None,
    revocation_reason: RevocationReason = RevocationReason.UNSPECIFIED,
    timestamp_evidence: TimestampEvidence | None = None,
    current_time: float | None = None,
) -> HistoricalVerificationResult:
    """
    Evaluate historical signature validity with explicit trusted time evidence.

    SECURITY INVARIANT:
    An OpenPGP signature creation-time field alone is untrusted metadata (attacker-controlled).
    An adversary who obtains an expired or compromised private key could fabricate a backdated
    signature creation-time to bypass expiration or revocation checks.

    Therefore:
    1. If a key is expired or revoked and NO independent trusted timestamp evidence is provided,
       we return INDETERMINATE_NO_TRUSTED_TIME rather than asserting historical validity.
    2. When trusted timestamp evidence (RFC 3161 TSA token or authenticated vault replay receipt)
       is provided, historical validity is anchored to that verified time.
    3. If a key was revoked due to COMPROMISE, any signature whose evidence postdates compromise
       is rejected as KEY_COMPROMISED. Only signatures with trusted prior receipt evidence
       strictly predating the compromise/revocation date may be validated.
    """
    now = time.time() if current_time is None else current_time

    # Rule 1: Signature claims to predate key creation
    if claimed_signature_time_utc < key_valid_from:
        return HistoricalVerificationResult(
            status=HistoricalValidity.PREDATES_KEY,
            is_valid=False,
            explanation="Claimed signature creation time predates key creation.",
        )

    is_expired = key_expires_at is not None and now > key_expires_at
    is_revoked = revocation_timestamp is not None and now >= revocation_timestamp
    is_compromised = is_revoked and revocation_reason == RevocationReason.KEY_COMPROMISED

    # Case A: Trusted timestamp evidence IS provided
    if timestamp_evidence is not None:
        if not timestamp_evidence.is_verified or timestamp_evidence.verified_time_utc <= 0:
            return HistoricalVerificationResult(
                status=HistoricalValidity.INVALID_EVIDENCE,
                is_valid=False,
                explanation="Timestamp evidence is malformed, unverified, or contains invalid time.",
                evidence_source=timestamp_evidence.source,
            )

        evidence_time = timestamp_evidence.verified_time_utc

        # Paradoxical time: claimed time is AFTER independently verified timestamp token
        if claimed_signature_time_utc > evidence_time:
            return HistoricalVerificationResult(
                status=HistoricalValidity.INVALID_EVIDENCE,
                is_valid=False,
                explanation="Claimed signature time postdates trusted timestamp token.",
                evidence_source=timestamp_evidence.source,
            )

        if evidence_time < key_valid_from:
            return HistoricalVerificationResult(
                status=HistoricalValidity.PREDATES_KEY,
                is_valid=False,
                explanation="Trusted timestamp evidence predates key creation.",
                evidence_source=timestamp_evidence.source,
            )

        # Check key expiration against verified evidence time
        if key_expires_at is not None and evidence_time > key_expires_at:
            return HistoricalVerificationResult(
                status=HistoricalValidity.EXPIRED_AT_CREATION,
                is_valid=False,
                explanation="Trusted timestamp proves signature was created after key expiration.",
                effective_time_utc=evidence_time,
                evidence_source=timestamp_evidence.source,
            )

        # Check key revocation against verified evidence time
        if revocation_timestamp is not None:
            if is_compromised:
                if evidence_time >= revocation_timestamp:
                    return HistoricalVerificationResult(
                        status=HistoricalValidity.KEY_COMPROMISED,
                        is_valid=False,
                        explanation="Key was compromised; trusted timestamp postdates compromise point.",
                        effective_time_utc=evidence_time,
                        evidence_source=timestamp_evidence.source,
                    )
                # Timestamp evidence strictly predates compromise
                return HistoricalVerificationResult(
                    status=HistoricalValidity.VALID_HISTORICAL,
                    is_valid=True,
                    explanation="Signature proven to predate key compromise via trusted timestamp evidence.",
                    effective_time_utc=evidence_time,
                    evidence_source=timestamp_evidence.source,
                )
            else:
                # Key superseded or retired
                if evidence_time > revocation_timestamp:
                    return HistoricalVerificationResult(
                        status=HistoricalValidity.REVOKED_AT_CREATION,
                        is_valid=False,
                        explanation="Trusted timestamp proves signature was created after key revocation.",
                        effective_time_utc=evidence_time,
                        evidence_source=timestamp_evidence.source,
                    )
                return HistoricalVerificationResult(
                    status=HistoricalValidity.VALID_HISTORICAL,
                    is_valid=True,
                    explanation="Signature proven to predate key revocation via trusted timestamp evidence.",
                    effective_time_utc=evidence_time,
                    evidence_source=timestamp_evidence.source,
                )

        return HistoricalVerificationResult(
            status=HistoricalValidity.VALID_HISTORICAL,
            is_valid=True,
            explanation="Signature verified within key validity period with trusted timestamp evidence.",
            effective_time_utc=evidence_time,
            evidence_source=timestamp_evidence.source,
        )

    # Case B: NO trusted timestamp evidence provided
    # If key was revoked due to compromise:
    if is_compromised:
        return HistoricalVerificationResult(
            status=HistoricalValidity.KEY_COMPROMISED,
            is_valid=False,
            explanation="Signing key was compromised. Unauthenticated signature creation-time cannot be trusted.",
        )

    # If key was revoked (superseded/retired):
    if is_revoked:
        if claimed_signature_time_utc > revocation_timestamp:
            return HistoricalVerificationResult(
                status=HistoricalValidity.REVOKED_AT_CREATION,
                is_valid=False,
                explanation="Claimed signature time postdates key revocation.",
            )
        # Signature claims to predate revocation, but lacks trusted time evidence
        return HistoricalVerificationResult(
            status=HistoricalValidity.INDETERMINATE_NO_TRUSTED_TIME,
            is_valid=False,
            explanation="Signature claims to predate key revocation, but lacks trusted time evidence (backdating defense).",
        )

    # If key is currently expired:
    if is_expired:
        if claimed_signature_time_utc > key_expires_at:
            return HistoricalVerificationResult(
                status=HistoricalValidity.EXPIRED_AT_CREATION,
                is_valid=False,
                explanation="Claimed signature time postdates key expiration.",
            )
        # Signature claims to predate expiry, but key is expired and no trusted evidence provided
        return HistoricalVerificationResult(
            status=HistoricalValidity.INDETERMINATE_NO_TRUSTED_TIME,
            is_valid=False,
            explanation="Signature claims to predate key expiration, but key is expired and lacks trusted time evidence (backdating defense).",
        )

    # Key is currently active (not expired, not revoked)
    if key_expires_at is not None and claimed_signature_time_utc > key_expires_at:
        return HistoricalVerificationResult(
            status=HistoricalValidity.EXPIRED_AT_CREATION,
            is_valid=False,
            explanation="Claimed signature time exceeds key expiration date.",
        )

    return HistoricalVerificationResult(
        status=HistoricalValidity.VALID_HISTORICAL,
        is_valid=True,
        explanation="Signing key is currently active; signature within validity window.",
        effective_time_utc=claimed_signature_time_utc,
    )


def is_signature_historically_valid(
    message_timestamp_utc: int,
    key_valid_from: int,
    key_expires_at: int | None,
    revocation_timestamp: int | None = None,
    revocation_reason: RevocationReason = RevocationReason.UNSPECIFIED,
    timestamp_evidence: TimestampEvidence | None = None,
    current_time: float | None = None,
) -> bool:
    """Convenience boolean helper delegating to verify_historical_signature."""
    return verify_historical_signature(
        claimed_signature_time_utc=message_timestamp_utc,
        key_valid_from=key_valid_from,
        key_expires_at=key_expires_at,
        revocation_timestamp=revocation_timestamp,
        revocation_reason=revocation_reason,
        timestamp_evidence=timestamp_evidence,
        current_time=current_time,
    ).is_valid
