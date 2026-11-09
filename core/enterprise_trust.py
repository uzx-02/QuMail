"""
Enterprise Trust Architecture & Trust Anchor Management (WS-02).

Provides the foundation for corporate-level trust provisioning without requiring
individual employees to conduct manual out-of-band fingerprint verification ceremonies.

Core Capabilities:
1. Administrator-provisioned organization trust roots and domain policies.
2. Enterprise domain key verification (e.g., verifying that keys belonging to @company.com
   are signed or sanctioned by the corporate trust authority).
3. Revocation and trust anchor updates.
4. Comprehensive audit logging for all enterprise trust evaluations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import time
from typing import Callable

from core.logging_config import get_logger

logger = get_logger("enterprise_trust")


@dataclass(frozen=True)
class TrustAnchor:
    """An administrator-provisioned enterprise trust authority or directory record."""
    anchor_id: str
    organization: str
    domains: tuple[str, ...]
    root_fingerprint: str
    authorized_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    is_revoked: bool = False

    def authorizes_domain(self, domain: str) -> bool:
        clean = domain.strip().lower()
        if self.is_revoked:
            return False
        if self.expires_at and time.time() > self.expires_at:
            return False
        return any(clean == d.lower() or clean.endswith("." + d.lower()) for d in self.domains)


@dataclass(frozen=True)
class EnterpriseContactRecord:
    email: str
    fingerprint: str
    public_key_bytes: bytes
    authorized_by_anchor: str
    certified_at: float = field(default_factory=time.time)
    is_revoked: bool = False


class EnterpriseTrustDirectory:
    """
    Central enterprise trust management directory.
    Maintains administrator trust anchors and certified corporate contacts.
    """

    def __init__(self):
        self._anchors: dict[str, TrustAnchor] = {}
        self._contacts: dict[str, EnterpriseContactRecord] = {}

    def add_trust_anchor(self, anchor: TrustAnchor) -> None:
        self._anchors[anchor.anchor_id] = anchor
        logger.info("Added enterprise trust anchor: %s (%s)", anchor.anchor_id, anchor.organization)

    def revoke_trust_anchor(self, anchor_id: str) -> None:
        if anchor_id in self._anchors:
            old = self._anchors[anchor_id]
            self._anchors[anchor_id] = TrustAnchor(
                anchor_id=old.anchor_id,
                organization=old.organization,
                domains=old.domains,
                root_fingerprint=old.root_fingerprint,
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
    ) -> EnterpriseContactRecord:
        anchor = self._anchors.get(anchor_id)
        if not anchor or anchor.is_revoked:
            raise ValueError(f"Cannot certify contact: trust anchor '{anchor_id}' is invalid or revoked")

        domain = email.split("@")[-1] if "@" in email else ""
        if not anchor.authorizes_domain(domain):
            raise ValueError(f"Trust anchor '{anchor_id}' does not authorize domain '{domain}'")

        rec = EnterpriseContactRecord(
            email=email.strip().lower(),
            fingerprint=fingerprint,
            public_key_bytes=public_key_bytes,
            authorized_by_anchor=anchor_id,
        )
        self._contacts[rec.email] = rec
        logger.info("Certified enterprise contact %s under anchor %s", rec.email, anchor_id)
        return rec

    def is_certified_by_enterprise(self, email: str, fingerprint: str) -> bool:
        """
        Check if an email address and key fingerprint are certified under an active enterprise anchor.
        """
        rec = self._contacts.get(email.strip().lower())
        if not rec or rec.is_revoked:
            return False
        if rec.fingerprint.lower() != fingerprint.lower():
            return False
        anchor = self._anchors.get(rec.authorized_by_anchor)
        if not anchor or not anchor.authorizes_domain(email.split("@")[-1]):
            return False
        return True

    def get_contact_record(self, email: str) -> EnterpriseContactRecord | None:
        return self._contacts.get(email.strip().lower())
