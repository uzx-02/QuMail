"""
Centralized Trust Policy Engine (WS-02).

Evaluates all identity, trust, and cryptographic policy decisions in a unified service.

Core Principles:
1. WKD / Directory discovery is strictly a KEY DISCOVERY mechanism, not identity trust.
2. An unverified discovered key NEVER receives a green 'Secured' indicator.
3. Trust decisions are policy-driven, centralized, and never inferred from loose UI booleans.
4. Distinguishes:
     - VERIFIED: Pinned or enterprise-certified identity.
     - DISCOVERED_NOT_VERIFIED: Known key, unverified identity.
     - ENCRYPTED_NOT_VERIFIED: Decrypted payload from unverified sender.
     - CHANGED_BLOCKED: Key changed unexpectedly (potential MITM).
     - VERIFICATION_FAILED: Signature invalid, tampered, or mismatched.
     - SECURITY_UNAVAILABLE: Key missing or service offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.enterprise_trust import EnterpriseTrustDirectory
from core.key_discovery import CachedKeyDiscoveryService, DiscoveredKey, DiscoveryStatus
from core.key_lifecycle import KeyStatus, evaluate_key_expiration
from core.logging_config import get_logger
from core.security_indicators import BadgeLevel, IndicatorCode, SecurityIndicator

logger = get_logger("trust_engine")


class TrustState(str, Enum):
    VERIFIED = "verified"
    DISCOVERED_NOT_VERIFIED = "discovered_not_verified"
    ENCRYPTED_NOT_VERIFIED = "encrypted_not_verified"
    CHANGED_BLOCKED = "changed_blocked"
    VERIFICATION_FAILED = "verification_failed"
    SECURITY_UNAVAILABLE = "security_unavailable"
    LOCAL_ENROLLED = "local_enrolled_identity"


@dataclass(frozen=True)
class TrustDecision:
    email: str
    state: TrustState
    fingerprint: str
    can_encrypt: bool
    is_identity_verified: bool
    indicator: SecurityIndicator
    reasons: list[str] = field(default_factory=list)


class TrustPolicyEngine:
    """Central decision engine for cryptographic identity and policy enforcement."""

    def __init__(
        self,
        discovery_service: CachedKeyDiscoveryService | None = None,
        enterprise_directory: EnterpriseTrustDirectory | None = None,
    ):
        self.discovery = discovery_service or CachedKeyDiscoveryService()
        self.enterprise = enterprise_directory or EnterpriseTrustDirectory()

    def evaluate_outbound_recipient(
        self,
        recipient_email: str,
        vault_contacts: dict[str, dict[str, Any]] | None = None,
    ) -> TrustDecision:
        """
        Evaluate recipient trust before drafting or sealing an email.
        Determines:
          1. Can we encrypt to this recipient?
          2. Is their identity verified or merely discovered?
        """
        clean_email = recipient_email.strip().lower()
        contacts = vault_contacts or {}
        contact = contacts.get(clean_email)

        # 1. Check local vault pinned contacts
        if contact:
            fp = contact.get("fingerprint", "")
            state = contact.get("state", "unverified")

            if state == "revoked":
                ind = SecurityIndicator.key_revoked_or_expired("revoked")
                return TrustDecision(
                    email=clean_email,
                    state=TrustState.VERIFICATION_FAILED,
                    fingerprint=fp,
                    can_encrypt=False,
                    is_identity_verified=False,
                    indicator=ind,
                    reasons=["Recipient key is revoked in local vault"],
                )

            if state == "changed_blocked":
                ind = SecurityIndicator.changed_key_blocked(clean_email)
                return TrustDecision(
                    email=clean_email,
                    state=TrustState.CHANGED_BLOCKED,
                    fingerprint=fp,
                    can_encrypt=False,
                    is_identity_verified=False,
                    indicator=ind,
                    reasons=["Recipient key changed unexpectedly compared to historical record"],
                )

            if state == "verified":
                ind = SecurityIndicator.secured(clean_email)
                return TrustDecision(
                    email=clean_email,
                    state=TrustState.VERIFIED,
                    fingerprint=fp,
                    can_encrypt=True,
                    is_identity_verified=True,
                    indicator=ind,
                    reasons=["Recipient identity pinned and verified in local vault"],
                )

        # 2. Check enterprise directory
        ent_rec = self.enterprise.get_contact_record(clean_email)
        if ent_rec and not ent_rec.is_revoked:
            ind = SecurityIndicator.secured(clean_email)
            return TrustDecision(
                email=clean_email,
                state=TrustState.VERIFIED,
                fingerprint=ent_rec.fingerprint,
                can_encrypt=True,
                is_identity_verified=True,
                indicator=ind,
                reasons=[f"Recipient certified by enterprise trust anchor '{ent_rec.authorized_by_anchor}'"],
            )

        # 3. Check automated key discovery (WKD / directory)
        discovery_res = self.discovery.discover(clean_email)
        if discovery_res.ok and discovery_res.key:
            # Successfully discovered key, but identity is NOT independently verified!
            ind = SecurityIndicator.external_correspondent(clean_email)
            return TrustDecision(
                email=clean_email,
                state=TrustState.DISCOVERED_NOT_VERIFIED,
                fingerprint=discovery_res.key.fingerprint,
                can_encrypt=True,
                is_identity_verified=False,
                indicator=ind,
                reasons=["Recipient key discovered via WKD/public directory; identity unverified"],
            )

        # 4. Key unavailable
        ind = SecurityIndicator.verification_unavailable(discovery_res.error_message or "No public key found")
        return TrustDecision(
            email=clean_email,
            state=TrustState.SECURITY_UNAVAILABLE,
            fingerprint="",
            can_encrypt=False,
            is_identity_verified=False,
            indicator=ind,
            reasons=["Public key could not be discovered for recipient"],
        )

    def evaluate_inbound_message(
        self,
        sender: str,
        signer_fingerprint: str,
        signature_valid: bool,
        identity_trust: str,
        replay_state: str,
        mismatches: tuple[str, ...],
        is_archive: bool = False,
        key_expires_at: int | None = None,
        key_is_revoked: bool = False,
    ) -> TrustDecision:
        """
        Evaluate inbound message trust state and generate a consumer-facing SecurityIndicator.
        """
        clean_sender = sender.strip().lower()

        # Check 1: Cryptographic signature validity
        if not signature_valid:
            ind = SecurityIndicator.signature_invalid()
            return TrustDecision(
                email=clean_sender,
                state=TrustState.VERIFICATION_FAILED,
                fingerprint=signer_fingerprint,
                can_encrypt=False,
                is_identity_verified=False,
                indicator=ind,
                reasons=["Mathematical digital signature verification failed"],
            )

        # Check 2: Revocation or Expiration
        if key_is_revoked:
            ind = SecurityIndicator.key_revoked_or_expired("revoked")
            return TrustDecision(
                email=clean_sender,
                state=TrustState.VERIFICATION_FAILED,
                fingerprint=signer_fingerprint,
                can_encrypt=False,
                is_identity_verified=False,
                indicator=ind,
                reasons=["Signer certificate has been revoked"],
            )

        if key_expires_at:
            exp_check = evaluate_key_expiration(key_expires_at)
            if exp_check.status == KeyStatus.EXPIRED:
                ind = SecurityIndicator.key_revoked_or_expired("expired")
                return TrustDecision(
                    email=clean_sender,
                    state=TrustState.VERIFICATION_FAILED,
                    fingerprint=signer_fingerprint,
                    can_encrypt=False,
                    is_identity_verified=False,
                    indicator=ind,
                    reasons=["Signer key has expired"],
                )

        # Check 3: Key changed unexpectedly
        if identity_trust == "changed_blocked":
            ind = SecurityIndicator.changed_key_blocked(clean_sender)
            return TrustDecision(
                email=clean_sender,
                state=TrustState.CHANGED_BLOCKED,
                fingerprint=signer_fingerprint,
                can_encrypt=False,
                is_identity_verified=False,
                indicator=ind,
                reasons=["Signer key changed unexpectedly compared to verified historical record"],
            )

        # Check 4: Metadata / outer-inner header mismatches
        if mismatches:
            ind = SecurityIndicator.identity_mismatch(clean_sender, f"mismatches: {', '.join(mismatches)}")
            return TrustDecision(
                email=clean_sender,
                state=TrustState.VERIFICATION_FAILED,
                fingerprint=signer_fingerprint,
                can_encrypt=False,
                is_identity_verified=False,
                indicator=ind,
                reasons=[f"Outer and inner metadata mismatch: {mismatches}"],
            )

        # Check 5: Replay protection
        if replay_state == "protected_identity_conflict":
            ind = SecurityIndicator.signature_invalid()
            return TrustDecision(
                email=clean_sender,
                state=TrustState.VERIFICATION_FAILED,
                fingerprint=signer_fingerprint,
                can_encrypt=False,
                is_identity_verified=False,
                indicator=ind,
                reasons=["Replay conflict: message identifier collision with different ciphertext"],
            )

        # Check 6: Verified identity (Pinned, Local Enrolled, or Enterprise Certified)
        is_enterprise_certified = self.enterprise.is_certified_by_enterprise(clean_sender, signer_fingerprint)
        is_verified_identity = (
            identity_trust in ("independently_verified", "local_enrolled_identity") or
            is_enterprise_certified
        )

        if is_verified_identity:
            ind = SecurityIndicator.secured(clean_sender)
            return TrustDecision(
                email=clean_sender,
                state=TrustState.LOCAL_ENROLLED if identity_trust == "local_enrolled_identity" else TrustState.VERIFIED,
                fingerprint=signer_fingerprint,
                can_encrypt=True,
                is_identity_verified=True,
                indicator=ind,
                reasons=["Identity verified and digital signature valid"],
            )

        # Check 7: Encrypted but unverified identity
        ind = SecurityIndicator.encrypted_unverified(clean_sender)
        return TrustDecision(
            email=clean_sender,
            state=TrustState.ENCRYPTED_NOT_VERIFIED,
            fingerprint=signer_fingerprint,
            can_encrypt=True,
            is_identity_verified=False,
            indicator=ind,
            reasons=["Digital signature valid and payload decrypted, but sender identity is unverified"],
        )
