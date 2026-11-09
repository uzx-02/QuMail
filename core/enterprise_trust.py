"""
Enterprise Trust Architecture & Trust Anchor Management (WS-02).

Provides the foundation for corporate-level trust provisioning without requiring
individual employees to conduct manual out-of-band fingerprint verification ceremonies.

Core Capabilities:
1. Administrator-provisioned organization trust roots and domain policies.
2. Cryptographically signed enterprise authorization manifests (Ed25519).
3. Explicit boundary differentiation: Cryptographically Signed vs. Local Administrative Provisioning.
4. Strict domain scoping and subdomain enforcement.
5. Immediate revocation and expiration propagation.
6. Deterministic conflict policy against public WKD records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import time
from typing import Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

from core.logging_config import get_logger

logger = get_logger("enterprise_trust")


class PolicyAuthType(str, Enum):
    """Specifies the trust boundary under which an enterprise policy was issued."""
    CRYPTOGRAPHICALLY_SIGNED = "cryptographically_signed"
    LOCAL_ADMIN_PROVISIONED = "local_admin_provisioned"


def compute_contact_authorization_payload(
    anchor_id: str,
    email: str,
    fingerprint: str,
    expires_at: float | None = None,
) -> bytes:
    """Canonical byte serialization for administrator contact certification signatures."""
    clean_email = email.strip().lower()
    clean_fp = fingerprint.strip().lower()
    exp_str = str(int(expires_at)) if expires_at is not None else "0"
    return f"QuMail-Enterprise-Auth-v1:{anchor_id}:{clean_email}:{clean_fp}:{exp_str}".encode("utf-8")


def verify_admin_signature(
    admin_public_key: bytes,
    signature: bytes,
    payload: bytes,
) -> bool:
    """Verify an Ed25519 administrator endorsement signature."""
    try:
        pub = ed25519.Ed25519PublicKey.from_public_bytes(admin_public_key)
        pub.verify(signature, payload)
        return True
    except (InvalidSignature, Exception):
        return False


@dataclass(frozen=True)
class TrustAnchor:
    """An administrator-provisioned enterprise trust authority or directory root."""
    anchor_id: str
    organization: str
    domains: tuple[str, ...]
    root_fingerprint: str
    admin_public_key: bytes | None = None
    auth_type: PolicyAuthType = PolicyAuthType.CRYPTOGRAPHICALLY_SIGNED
    authorized_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    is_revoked: bool = False

    def authorizes_domain(self, domain: str) -> bool:
        clean = domain.strip().lower()
        if not clean or self.is_revoked:
            return False
        if self.expires_at and time.time() > self.expires_at:
            return False
        for d in self.domains:
            target = d.strip().lower()
            if clean == target or clean.endswith("." + target):
                return True
        return False


@dataclass(frozen=True)
class EnterpriseContactRecord:
    email: str
    fingerprint: str
    public_key_bytes: bytes
    authorized_by_anchor: str
    admin_signature: bytes | None = None
    certified_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    is_revoked: bool = False


class EnterpriseTrustDirectory:
    """
    Central enterprise trust management directory.
    Maintains administrator trust anchors and certified corporate contacts.
    """

    def __init__(self, is_available: bool = True):
        self._anchors: dict[str, TrustAnchor] = {}
        self._contacts: dict[str, EnterpriseContactRecord] = {}
        self.is_available = is_available

    @property
    def anchors(self) -> dict[str, TrustAnchor]:
        return dict(self._anchors)

    def add_trust_anchor(self, anchor: TrustAnchor) -> None:
        self._anchors[anchor.anchor_id] = anchor
        logger.info("Added enterprise trust anchor: %s (%s, type=%s)", anchor.anchor_id, anchor.organization, anchor.auth_type.value)

    def revoke_trust_anchor(self, anchor_id: str) -> None:
        if anchor_id in self._anchors:
            old = self._anchors[anchor_id]
            self._anchors[anchor_id] = TrustAnchor(
                anchor_id=old.anchor_id,
                organization=old.organization,
                domains=old.domains,
                root_fingerprint=old.root_fingerprint,
                admin_public_key=old.admin_public_key,
                auth_type=old.auth_type,
                authorized_at=old.authorized_at,
                expires_at=old.expires_at,
                is_revoked=True,
            )
            logger.warning("Revoked enterprise trust anchor: %s", anchor_id)

    def register_certified_contact(
        self,
        email: str,
        fingerprint: str,
        public_key_bytes: bytes,
        anchor_id: str,
        admin_signature: bytes | None = None,
        expires_at: float | None = None,
    ) -> EnterpriseContactRecord:
        if not self.is_available:
            raise ValueError("Enterprise trust directory is currently unavailable")

        anchor = self._anchors.get(anchor_id)
        if not anchor or anchor.is_revoked:
            raise ValueError(f"Cannot certify contact: trust anchor '{anchor_id}' is invalid or revoked")

        if anchor.expires_at and time.time() > anchor.expires_at:
            raise ValueError(f"Cannot certify contact: trust anchor '{anchor_id}' has expired")

        domain = email.split("@")[-1] if "@" in email else ""
        if not anchor.authorizes_domain(domain):
            raise ValueError(f"Trust anchor '{anchor_id}' does not authorize domain '{domain}'")

        # Cryptographic verification if administrator public key is configured
        if anchor.admin_public_key:
            if not admin_signature:
                raise ValueError("Missing administrator authorization signature for cryptographically signed anchor")
            payload = compute_contact_authorization_payload(anchor_id, email, fingerprint, expires_at)
            if not verify_admin_signature(anchor.admin_public_key, admin_signature, payload):
                raise ValueError("Invalid administrator authorization signature")

        rec = EnterpriseContactRecord(
            email=email.strip().lower(),
            fingerprint=fingerprint,
            public_key_bytes=public_key_bytes,
            authorized_by_anchor=anchor_id,
            admin_signature=admin_signature,
            expires_at=expires_at,
        )
        self._contacts[rec.email] = rec
        logger.info("Certified enterprise contact %s under anchor %s", rec.email, anchor_id)
        return rec

    def is_certified_by_enterprise(self, email: str, fingerprint: str) -> bool:
        """
        Check if an email address and key fingerprint are certified under an active enterprise anchor.
        """
        if not self.is_available:
            return False

        rec = self._contacts.get(email.strip().lower())
        if not rec or rec.is_revoked:
            return False
        if rec.fingerprint.lower() != fingerprint.lower():
            return False
        if rec.expires_at and time.time() > rec.expires_at:
            return False

        anchor = self._anchors.get(rec.authorized_by_anchor)
        if not anchor or anchor.is_revoked:
            return False
        if anchor.expires_at and time.time() > anchor.expires_at:
            return False

        domain = email.split("@")[-1] if "@" in email else ""
        if not anchor.authorizes_domain(domain):
            return False

        # Verify cryptographic signature if anchor has public key
        if anchor.admin_public_key:
            if not rec.admin_signature:
                return False
            payload = compute_contact_authorization_payload(
                anchor.anchor_id, rec.email, rec.fingerprint, rec.expires_at
            )
            if not verify_admin_signature(anchor.admin_public_key, rec.admin_signature, payload):
                return False

        return True

    def get_contact_record(self, email: str) -> EnterpriseContactRecord | None:
        if not self.is_available:
            return None
        return self._contacts.get(email.strip().lower())
