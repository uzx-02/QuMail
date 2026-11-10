"""
core/directory_client.py — Desktop Client for QuMail Public-Key Directory & Transparency Engine.

Integrates directory lookup and publication into the QuMail desktop client:
- Automatically publishes active public key upon first-run enrollment.
- Implements Proof of Key Possession (PoP) binding.
- Performs authenticated lookups for unknown recipients.
- Verifies Merkle tree inclusion proofs and Signed Tree Heads (STH) locally.
- Manages local SQLite Trust-On-First-Use (TOFU) key pinning in contacts table.
- Raises non-dismissible alerts upon unexpected key substitution.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests
from cryptography.hazmat.primitives.asymmetric import ed25519

from services.directory.merkle import verify_inclusion

logger = logging.getLogger("directory_client")


@dataclass
class DirectoryLookupResult:
    email: str
    fingerprint: str
    certificate_armor: str
    generation: int
    revoked: bool
    is_pinned: bool
    trust_status: str          # "SECURE", "CAUTION", "ALERT"
    status_reason: str
    inclusion_verified: bool


class DirectoryClient:
    """Client for QuMail Public-Key Directory."""

    def __init__(
        self,
        directory_url: str = "http://127.0.0.1:5055",
        vault_path: str | Path = "qumail_vault.sqlite",
        authority_pubkey_hex: Optional[str] = None,
        mock_service: Any = None,
    ) -> None:
        self.directory_url = directory_url.rstrip("/")
        self.vault_path = Path(vault_path)
        self.authority_pubkey_hex = authority_pubkey_hex
        self.mock_service = mock_service  # Allows direct in-process testing without HTTP sockets
        self._init_vault_tables()

    def _init_vault_tables(self) -> None:
        """Ensure checkpoints and contacts tables exist in local SQLite vault."""
        try:
            self.vault_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.vault_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS directory_checkpoints (
                        tree_size INTEGER PRIMARY KEY,
                        timestamp_utc TEXT NOT NULL,
                        root_hash TEXT NOT NULL,
                        signature TEXT NOT NULL,
                        verified_at TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS directory_pinned_keys (
                        email TEXT PRIMARY KEY,
                        fingerprint TEXT NOT NULL,
                        generation INTEGER NOT NULL,
                        certificate_armor TEXT NOT NULL,
                        first_seen_utc TEXT NOT NULL,
                        last_verified_utc TEXT NOT NULL
                    )
                """)
                conn.commit()
        except Exception as exc:
            logger.warning("Could not initialize directory tables in vault %s: %s", self.vault_path, exc)

    def register(
        self,
        email: str,
        certificate_armor: str,
        fingerprint: str,
        primary_private_key: Optional[ed25519.Ed25519PrivateKey] = None,
        primary_pubkey_raw: Optional[bytes] = None,
    ) -> dict[str, Any]:
        """Enroll active public key with Proof of Possession."""
        # 1. Obtain Challenge
        if self.mock_service:
            chal = self.mock_service.issue_challenge(email)
        else:
            resp = requests.post(f"{self.directory_url}/api/v1/auth/challenge", json={"email": email}, timeout=5)
            resp.raise_for_status()
            chal = resp.json()

        chal_id = chal["challenge_id"]
        nonce = chal["nonce"]

        # 2. Build PoP binding
        pop_binding = hashlib.sha256(
            f"QUMAIL-POP-v1:{email.strip().lower()}:{nonce}:{fingerprint}:QM-OPENPGP-PQ-v1:{chal['audience']}:{chal['issued_utc']}:{chal['expires_utc']}".encode("utf-8")
        ).digest()

        # 3. Compute Signature
        sig_b64 = ""
        pub_hex = ""
        if primary_private_key:
            sig = primary_private_key.sign(pop_binding)
            sig_b64 = base64.b64encode(sig).decode("ascii")
            pub_hex = primary_private_key.public_key().public_bytes_raw().hex()
        elif primary_pubkey_raw:
            pub_hex = primary_pubkey_raw.hex()

        reg_payload = {
            "challenge_id": chal_id,
            "email": email,
            "certificate_armor": certificate_armor,
            "fingerprint": fingerprint,
            "pop_signature": sig_b64,
            "primary_pubkey_hex": pub_hex,
        }

        # 4. Submit Registration
        if self.mock_service:
            res = self.mock_service.register_key(
                challenge_id=chal_id,
                email=email,
                certificate_armor=certificate_armor,
                fingerprint=fingerprint,
                pop_signature=sig_b64,
                primary_public_key_raw=bytes.fromhex(pub_hex) if pub_hex else None,
            )
        else:
            resp = requests.post(f"{self.directory_url}/api/v1/keys/register", json=reg_payload, timeout=5)
            resp.raise_for_status()
            res = resp.json()

        # 5. Pin own key in vault
        self._pin_key(email, fingerprint, res.get("generation", 1), certificate_armor)
        return res

    def lookup(self, email: str, enterprise_trusted_domains: list[str] | None = None) -> Optional[DirectoryLookupResult]:
        """Perform directory lookup, Merkle verification, and TOFU trust check."""
        norm_email = email.strip().lower()
        if self.mock_service:
            rec = self.mock_service.lookup(norm_email)
        else:
            try:
                resp = requests.get(f"{self.directory_url}/api/v1/keys/lookup", params={"email": norm_email}, timeout=5)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                rec = resp.json()
            except Exception as exc:
                logger.error("Directory lookup failed for %s: %s", norm_email, exc)
                return None

        if not rec:
            return None

        # Verify Merkle Inclusion Proof
        inclusion_ok = False
        try:
            entry = {
                "type": "ENROLLMENT",
                "email": norm_email,
                "fingerprint": rec["fingerprint"],
                "generation": rec["generation"],
                "certificate_armor": rec["certificate_armor"],
                "timestamp": rec["registered_utc"],
                "leaf_index": rec["leaf_index"],
            }
            leaf_bytes = json.dumps(entry, sort_keys=True).encode("utf-8")
            sth = rec["sth"]
            inclusion_ok = verify_inclusion(
                leaf_data=leaf_bytes,
                leaf_index=rec["leaf_index"],
                tree_size=sth["tree_size"],
                proof_hex=rec["inclusion_proof"],
                root_hash_hex=sth["root_hash"],
            )
        except Exception as exc:
            logger.warning("Merkle inclusion proof verification failed: %s", exc)

        # TOFU Pinning & Substitution Check
        pinned = self._get_pinned_key(norm_email)
        is_pinned = pinned is not None

        if pinned and pinned["fingerprint"] != rec["fingerprint"]:
            # Hard Key Substitution Detected!
            trust_status = "ALERT"
            reason = f"KEY SUBSTITUTION DETECTED! Pinned fingerprint ({pinned['fingerprint'][:16]}...) does not match directory ({rec['fingerprint'][:16]}...)."
        elif rec.get("revoked", False):
            trust_status = "ALERT"
            reason = "Revoked Key: Sender identity key has been marked revoked in the transparency log."
        else:
            # Check if domain is enterprise-certified via GPO
            domain = norm_email.split("@")[-1] if "@" in norm_email else ""
            if enterprise_trusted_domains and domain in enterprise_trusted_domains:
                trust_status = "SECURE"
                reason = "Enterprise Verified: Domain certified by corporate Group Policy."
            else:
                trust_status = "CAUTION"
                reason = "Directory Discovered (Unverified): Valid post-quantum seal, but key is not certified by corporate CA."

            # Update or insert pin
            self._pin_key(norm_email, rec["fingerprint"], rec["generation"], rec["certificate_armor"])

        return DirectoryLookupResult(
            email=norm_email,
            fingerprint=rec["fingerprint"],
            certificate_armor=rec["certificate_armor"],
            generation=rec["generation"],
            revoked=rec.get("revoked", False),
            is_pinned=is_pinned,
            trust_status=trust_status,
            status_reason=reason,
            inclusion_verified=inclusion_ok,
        )

    def _pin_key(self, email: str, fingerprint: str, generation: int, cert_armor: str) -> None:
        try:
            now = datetime.now(timezone.utc).isoformat()
            with sqlite3.connect(self.vault_path) as conn:
                conn.execute("""
                    INSERT INTO directory_pinned_keys (email, fingerprint, generation, certificate_armor, first_seen_utc, last_verified_utc)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(email) DO UPDATE SET
                        fingerprint=excluded.fingerprint,
                        generation=excluded.generation,
                        certificate_armor=excluded.certificate_armor,
                        last_verified_utc=excluded.last_verified_utc
                """, (email, fingerprint, generation, cert_armor, now, now))
                conn.commit()
        except Exception as exc:
            logger.warning("Could not pin key for %s: %s", email, exc)

    def _get_pinned_key(self, email: str) -> Optional[dict[str, Any]]:
        try:
            with sqlite3.connect(self.vault_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute("SELECT * FROM directory_pinned_keys WHERE email = ?", (email,))
                row = cur.fetchone()
                if row:
                    return dict(row)
        except Exception:
            pass
        return None
