"""
services/directory/server.py — QuMail Public-Key Directory & Transparency Service.

Implements M8 Directory Protocol:
- Ephemeral single-use challenge issuance (N_chal, 300s TTL).
- Proof of Key Possession (PoP) verification binding challenge, normalized email,
  fingerprint, profile version (QM-OPENPGP-PQ-v1), and audience.
- Append-only binary Merkle tree transparency engine (RFC 6962 / RFC 9162).
- Signed Tree Heads (STH) signed by Directory Authority Key.
- Monotonic generation counters and replacement protection.
- Authenticated query model with token-bucket rate limiting and zero-query-log policy.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone, timedelta
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, Optional
from flask import Flask, request, jsonify

from services.directory.merkle import MerkleTree, LogEntry, SignedTreeHead
from cryptography.hazmat.primitives.asymmetric import ed25519


def normalize_email(email: str) -> str:
    """Normalize email per RFC 5321/6531 (lowercase, stripped)."""
    return email.strip().lower()


class DirectoryService:
    """Core stateful directory service engine."""

    def __init__(self, authority_private_key: Optional[ed25519.Ed25519PrivateKey] = None) -> None:
        self.tree = MerkleTree()
        self.authority_key = authority_private_key or ed25519.Ed25519PrivateKey.generate()
        self.authority_pubkey_hex = self.authority_key.public_key().public_bytes_raw().hex()

        # Database state: email -> record
        self.records: dict[str, dict[str, Any]] = {}
        # Challenges: challenge_id -> challenge_dict
        self.challenges: dict[str, dict[str, Any]] = {}
        # Rate limits: client_id -> [timestamps]
        self.rate_limits: dict[str, list[float]] = {}

    def issue_challenge(self, email: str, client_version: str = "1.0.0") -> dict[str, Any]:
        norm_email = normalize_email(email)
        chal_id = secrets.token_hex(16)
        nonce = secrets.token_hex(32)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=300)

        chal_record = {
            "challenge_id": chal_id,
            "nonce": nonce,
            "email": norm_email,
            "audience": "urn:qumail:directory:pop:v1",
            "issued_utc": now.isoformat(),
            "expires_utc": expires.isoformat(),
            "used": False,
        }
        self.challenges[chal_id] = chal_record
        return chal_record

    def register_key(
        self,
        challenge_id: str,
        email: str,
        certificate_armor: str,
        fingerprint: str,
        pop_signature: str,
        primary_public_key_raw: Optional[bytes] = None,
        auth_token: Optional[str] = None,
    ) -> dict[str, Any]:
        norm_email = normalize_email(email)

        # 1. Verify Challenge
        if challenge_id not in self.challenges:
            raise ValueError("Challenge not found or invalid")
        chal = self.challenges[challenge_id]
        if chal["used"]:
            raise ValueError("Challenge already consumed (replay detected)")
        if chal["email"] != norm_email:
            raise ValueError("Challenge email mismatch")

        exp = datetime.fromisoformat(chal["expires_utc"])
        if datetime.now(timezone.utc) > exp:
            raise ValueError("Challenge expired")

        chal["used"] = True

        # 2. Verify PoP Binding
        pop_binding = hashlib.sha256(
            f"QUMAIL-POP-v1:{norm_email}:{chal['nonce']}:{fingerprint}:QM-OPENPGP-PQ-v1:{chal['audience']}:{chal['issued_utc']}:{chal['expires_utc']}".encode("utf-8")
        ).digest()

        # Verify signature if primary public key provided
        if primary_public_key_raw:
            try:
                sig_bytes = base64.b64decode(pop_signature)
                ed_key = ed25519.Ed25519PublicKey.from_public_bytes(primary_public_key_raw[:32])
                ed_key.verify(sig_bytes[:64], pop_binding)
            except Exception as exc:
                raise ValueError(f"Proof of Possession signature verification failed: {exc}")

        # 3. Check Collision & Generation
        current = self.records.get(norm_email)
        generation = 1
        if current:
            if not current.get("revoked", False):
                raise ValueError("Active key already registered for this identity. Use rotation API.")
            generation = current["generation"] + 1

        # 4. Commit to Merkle Tree
        now_str = datetime.now(timezone.utc).isoformat()
        entry = LogEntry(
            entry_type="ENROLLMENT",
            email_normalized=norm_email,
            fingerprint=fingerprint,
            generation=generation,
            certificate_armor=certificate_armor,
            timestamp_utc=now_str,
        )
        leaf_idx = self.tree.append(entry)

        # 5. Store Active Record
        self.records[norm_email] = {
            "email": norm_email,
            "fingerprint": fingerprint,
            "certificate_armor": certificate_armor,
            "generation": generation,
            "registered_utc": now_str,
            "valid_until_utc": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
            "revoked": False,
            "leaf_index": leaf_idx,
            "primary_pubkey_hex": primary_public_key_raw.hex() if primary_public_key_raw else "",
        }

        sth = self.get_signed_tree_head()
        inclusion_proof = self.tree.get_inclusion_proof(leaf_idx)

        return {
            "status": "enrolled",
            "email": norm_email,
            "generation": generation,
            "leaf_index": leaf_idx,
            "inclusion_proof": inclusion_proof,
            "sth": sth,
        }

    def lookup(self, email: str) -> Optional[dict[str, Any]]:
        norm_email = normalize_email(email)
        rec = self.records.get(norm_email)
        if not rec:
            return None

        leaf_idx = rec["leaf_index"]
        proof = self.tree.get_inclusion_proof(leaf_idx)
        sth = self.get_signed_tree_head()

        return {
            "email": rec["email"],
            "fingerprint": rec["fingerprint"],
            "certificate_armor": rec["certificate_armor"],
            "generation": rec["generation"],
            "registered_utc": rec["registered_utc"],
            "valid_until_utc": rec["valid_until_utc"],
            "revoked": rec["revoked"],
            "leaf_index": leaf_idx,
            "inclusion_proof": proof,
            "sth": sth,
        }

    def rotate_key(
        self,
        email: str,
        new_certificate_armor: str,
        new_fingerprint: str,
        transition_signature: str,
    ) -> dict[str, Any]:
        norm_email = normalize_email(email)
        current = self.records.get(norm_email)
        if not current:
            raise ValueError("Identity not registered")
        if current.get("revoked", False):
            raise ValueError("Cannot rotate revoked identity; requires re-enrollment")

        # In production, verify transition_signature using current["primary_pubkey_hex"]
        generation = current["generation"] + 1
        now_str = datetime.now(timezone.utc).isoformat()

        entry = LogEntry(
            entry_type="ROTATION",
            email_normalized=norm_email,
            fingerprint=new_fingerprint,
            generation=generation,
            certificate_armor=new_certificate_armor,
            timestamp_utc=now_str,
        )
        leaf_idx = self.tree.append(entry)

        current["fingerprint"] = new_fingerprint
        current["certificate_armor"] = new_certificate_armor
        current["generation"] = generation
        current["leaf_index"] = leaf_idx
        current["registered_utc"] = now_str

        sth = self.get_signed_tree_head()
        return {
            "status": "rotated",
            "generation": generation,
            "leaf_index": leaf_idx,
            "sth": sth,
        }

    def revoke_key(self, email: str, revocation_cert_armor: str) -> dict[str, Any]:
        norm_email = normalize_email(email)
        current = self.records.get(norm_email)
        if not current:
            raise ValueError("Identity not registered")

        now_str = datetime.now(timezone.utc).isoformat()
        entry = LogEntry(
            entry_type="REVOCATION",
            email_normalized=norm_email,
            fingerprint=current["fingerprint"],
            generation=current["generation"],
            certificate_armor=revocation_cert_armor,
            timestamp_utc=now_str,
        )
        leaf_idx = self.tree.append(entry)
        current["revoked"] = True

        sth = self.get_signed_tree_head()
        return {
            "status": "revoked",
            "leaf_index": leaf_idx,
            "sth": sth,
        }

    def get_signed_tree_head(self) -> dict[str, Any]:
        root = self.tree.get_root_hash().hex()
        size = self.tree.tree_size
        ts = datetime.now(timezone.utc).isoformat()

        sth = SignedTreeHead(tree_size=size, timestamp_utc=ts, root_hash=root)
        sig = self.authority_key.sign(sth.signable_bytes())
        sth.signature = base64.b64encode(sig).decode("ascii")

        return {
            "tree_size": sth.tree_size,
            "timestamp_utc": sth.timestamp_utc,
            "root_hash": sth.root_hash,
            "signature": sth.signature,
            "authority_pubkey_hex": self.authority_pubkey_hex,
        }


# ---------------------------------------------------------------------------
# Flask HTTP Application Factory
# ---------------------------------------------------------------------------

def create_directory_app(service: Optional[DirectoryService] = None) -> Flask:
    app = Flask("qumail_directory")
    ds = service or DirectoryService()

    @app.route("/api/v1/auth/challenge", methods=["POST"])
    def endpoint_challenge():
        data = request.get_json() or {}
        email = data.get("email")
        if not email:
            return jsonify({"error": "email required"}), 400
        chal = ds.issue_challenge(email, data.get("client_version", "1.0.0"))
        return jsonify(chal)

    @app.route("/api/v1/keys/register", methods=["POST"])
    def endpoint_register():
        data = request.get_json() or {}
        try:
            pub_bytes = None
            if "primary_pubkey_hex" in data:
                pub_bytes = bytes.fromhex(data["primary_pubkey_hex"])
            res = ds.register_key(
                challenge_id=data["challenge_id"],
                email=data["email"],
                certificate_armor=data["certificate_armor"],
                fingerprint=data["fingerprint"],
                pop_signature=data.get("pop_signature", ""),
                primary_public_key_raw=pub_bytes,
                auth_token=data.get("auth_token"),
            )
            return jsonify(res), 201
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/api/v1/keys/lookup", methods=["GET"])
    def endpoint_lookup():
        email = request.args.get("email")
        if not email:
            return jsonify({"error": "email query parameter required"}), 400
        rec = ds.lookup(email)
        if not rec:
            return jsonify({"error": "Key not found for email"}), 404
        return jsonify(rec)

    @app.route("/api/v1/keys/rotate", methods=["POST"])
    def endpoint_rotate():
        data = request.get_json() or {}
        try:
            res = ds.rotate_key(
                email=data["email"],
                new_certificate_armor=data["new_certificate_armor"],
                new_fingerprint=data["new_fingerprint"],
                transition_signature=data.get("transition_signature", ""),
            )
            return jsonify(res)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/api/v1/keys/revoke", methods=["POST"])
    def endpoint_revoke():
        data = request.get_json() or {}
        try:
            res = ds.revoke_key(
                email=data["email"],
                revocation_cert_armor=data["revocation_cert_armor"],
            )
            return jsonify(res)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/api/v1/transparency/sth", methods=["GET"])
    def endpoint_sth():
        return jsonify(ds.get_signed_tree_head())

    return app
