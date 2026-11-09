"""
Security Indicator Contract (WS-02).

Defines the centralized, stable security-state contract consumed by the UI (WS-05).
Provides plain-language explanations and actionable security advice for corporate employees,
eliminating raw technical codes and hexadecimal fingerprints from user-facing screens.

SECURITY ENFORCEMENT:
The green 'SECURED_BY_QUMAIL' indicator is strictly restricted to cases where:
1. Message signature is valid.
2. Signer identity is independently verified or corporate-anchored.
3. Message replay status is fresh.
4. Outer and inner MIME metadata are consistent.
5. Signer key is active (not revoked, not expired).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BadgeLevel(str, Enum):
    SECURE = "secure"      # Green: Verified corporate identity & post-quantum encryption
    CAUTION = "caution"    # Amber/Yellow: Encrypted, but sender identity is unverified
    ALERT = "alert"        # Red: Signature failed, identity mismatch, or revoked/expired key
    NEUTRAL = "neutral"    # Gray: Verification info unavailable or external party


class IndicatorCode(str, Enum):
    SECURED_BY_QUMAIL = "secured_by_qumail"
    ENCRYPTED_UNVERIFIED = "encrypted_unverified_identity"
    EXTERNAL_CORRESPONDENT = "external_correspondent"
    SIGNATURE_INVALID = "signature_invalid"
    IDENTITY_MISMATCH = "identity_mismatch"
    KEY_REVOKED_OR_EXPIRED = "key_revoked_or_expired"
    CHANGED_BLOCKED = "changed_key_blocked"
    VERIFICATION_UNAVAILABLE = "verification_unavailable"


@dataclass(frozen=True)
class SecurityIndicator:
    code: IndicatorCode
    badge_level: BadgeLevel
    headline: str
    description: str
    action_advice: str
    is_safe_to_trust: bool = False
    is_encrypted: bool = True

    @classmethod
    def secured(cls, sender: str = "") -> SecurityIndicator:
        who = f"from {sender}" if sender else "from sender"
        return cls(
            code=IndicatorCode.SECURED_BY_QUMAIL,
            badge_level=BadgeLevel.SECURE,
            headline="Secured by QuMail",
            description=f"Verified corporate identity {who}. Encrypted with post-quantum security.",
            action_advice="Identity and digital signature are authenticated. Safe to communicate.",
            is_safe_to_trust=True,
            is_encrypted=True,
        )

    @classmethod
    def encrypted_unverified(cls, sender: str = "") -> SecurityIndicator:
        who = f"from {sender}" if sender else "this correspondent"
        return cls(
            code=IndicatorCode.ENCRYPTED_UNVERIFIED,
            badge_level=BadgeLevel.CAUTION,
            headline="Encrypted — Sender Identity Unverified",
            description=f"Message is encrypted with post-quantum security, but identity {who} has not been verified.",
            action_advice="If this message contains sensitive business instructions or financial details, verify via an independent channel.",
            is_safe_to_trust=False,
            is_encrypted=True,
        )

    @classmethod
    def external_correspondent(cls, email: str = "") -> SecurityIndicator:
        return cls(
            code=IndicatorCode.EXTERNAL_CORRESPONDENT,
            badge_level=BadgeLevel.NEUTRAL,
            headline="External Correspondent",
            description=f"Public key for {email} was discovered via public directory, but no corporate trust relationship exists.",
            action_advice="Standard external communication. Messages can be encrypted.",
            is_safe_to_trust=False,
            is_encrypted=False,
        )

    @classmethod
    def signature_invalid(cls) -> SecurityIndicator:
        return cls(
            code=IndicatorCode.SIGNATURE_INVALID,
            badge_level=BadgeLevel.ALERT,
            headline="Security Alert — Digital Signature Invalid",
            description="The digital signature on this message could not be verified. The message may have been altered or corrupted in transit.",
            action_advice="DO NOT trust this message or click any attachments. Report to IT Security.",
            is_safe_to_trust=False,
            is_encrypted=False,
        )

    @classmethod
    def identity_mismatch(cls, claimed: str, actual: str) -> SecurityIndicator:
        return cls(
            code=IndicatorCode.IDENTITY_MISMATCH,
            badge_level=BadgeLevel.ALERT,
            headline="Security Alert — Sender Address Mismatch",
            description=f"The sender address '{claimed}' does not match the certified certificate identity '{actual}'.",
            action_advice="DO NOT release sensitive information. The sender may be spoofed.",
            is_safe_to_trust=False,
            is_encrypted=False,
        )

    @classmethod
    def key_revoked_or_expired(cls, reason: str = "expired") -> SecurityIndicator:
        return cls(
            code=IndicatorCode.KEY_REVOKED_OR_EXPIRED,
            badge_level=BadgeLevel.ALERT,
            headline="Security Alert — Signer Key Inactive",
            description=f"The cryptographic key used to sign this message is {reason} and is no longer authorized for use.",
            action_advice="Contact the sender through an alternate channel to request an updated key.",
            is_safe_to_trust=False,
            is_encrypted=False,
        )

    @classmethod
    def changed_key_blocked(cls, address: str) -> SecurityIndicator:
        return cls(
            code=IndicatorCode.CHANGED_BLOCKED,
            badge_level=BadgeLevel.ALERT,
            headline="Security Alert — Key Changed Unexpectedly",
            description=f"The cryptographic key for '{address}' has changed since it was previously verified.",
            action_advice="Communication is blocked until the new key is authenticated to prevent potential interception.",
            is_safe_to_trust=False,
            is_encrypted=False,
        )

    @classmethod
    def verification_unavailable(cls, reason: str = "") -> SecurityIndicator:
        desc = f"Security verification could not be completed ({reason})." if reason else "Security verification could not be completed."
        return cls(
            code=IndicatorCode.VERIFICATION_UNAVAILABLE,
            badge_level=BadgeLevel.NEUTRAL,
            headline="Security Verification Unavailable",
            description=desc,
            action_advice="Check network connectivity or retry after verification services are reachable.",
            is_safe_to_trust=False,
            is_encrypted=False,
        )
