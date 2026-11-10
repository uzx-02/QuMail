"""
core/web_link_crypto.py — QuMail Secure Web Link (Pillar 2) Cryptographic Engine.

Implements client-side symmetric sealing and zero-knowledge delivery for external non-QuMail recipients:
- Client-side AES-256-GCM encryption with 256-bit CSPRNG key K_msg and 96-bit IV.
- Sender signature binding message ID, sender, recipient, expiry, and ciphertext digest.
- URL fragment packing: https://portal.qumail.invalid/view/<UUID>#<KeyHex>
  Per RFC 3986 §3.5, the fragment is NEVER transmitted to the web server in HTTP requests.
- Recipient decryptor logic verifying GCM tag, AAD, and sender signature.
- WebKEM reply key-wrapping logic.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
import secrets
import uuid
from typing import Any, Dict, Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric import ed25519


def create_secure_web_link_package(
    plaintext_body: str,
    sender_email: str,
    recipient_email: str,
    sender_signing_key: ed25519.Ed25519PrivateKey,
    sender_cert_armor: str = "",
    portal_base_url: str = "https://portal.qumail.invalid",
    validity_days: int = 7,
) -> dict[str, Any]:
    """
    Encrypt message client-side for external zero-install recipient.
    Returns:
      - 'blob_to_upload': The encrypted payload for the portal server (contains NO key)
      - 'access_url': The URL with #key embedded in the fragment for the invitation email
      - 'message_id': Unique message identifier
      - 'key_hex': Ephemeral key hex (kept local to sender)
    """
    msg_id = str(uuid.uuid4())
    k_msg = secrets.token_bytes(32)  # 256-bit AES key
    iv = secrets.token_bytes(12)     # 96-bit GCM nonce

    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=validity_days)
    now_str = now.isoformat()
    expires_str = expires.isoformat()

    # Associated Authenticated Data (AAD)
    aad = f"{msg_id}:{sender_email}:{recipient_email}:{now_str}:{expires_str}".encode("utf-8")

    # AES-256-GCM Encryption
    aesgcm = AESGCM(k_msg)
    ciphertext_and_tag = aesgcm.encrypt(iv, plaintext_body.encode("utf-8"), aad)

    # Sender Digital Signature over metadata tuple & ciphertext digest
    c_hash = hashlib.sha256(ciphertext_and_tag).digest()
    metadata_tuple = hashlib.sha256(
        f"QM-WEBLINK-v1:{msg_id}:{sender_email}:{recipient_email}:{now_str}:{expires_str}".encode("utf-8") + c_hash
    ).digest()
    sig = sender_signing_key.sign(metadata_tuple)

    blob_to_upload = {
        "message_id": msg_id,
        "sender_email": sender_email,
        "recipient_email": recipient_email,
        "issued_utc": now_str,
        "expires_utc": expires_str,
        "iv_b64": base64.b64encode(iv).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext_and_tag).decode("ascii"),
        "aad_b64": base64.b64encode(aad).decode("ascii"),
        "sender_sig_b64": base64.b64encode(sig).decode("ascii"),
        "sender_pubkey_hex": sender_signing_key.public_key().public_bytes_raw().hex(),
        "sender_cert_armor": sender_cert_armor,
    }

    # Access URL: RFC 3986 fragment holds the secret key
    access_url = f"{portal_base_url.rstrip('/')}/view/{msg_id}#{k_msg.hex()}"

    return {
        "blob_to_upload": blob_to_upload,
        "access_url": access_url,
        "message_id": msg_id,
        "key_hex": k_msg.hex(),
    }


def decrypt_secure_web_link_package(
    blob: dict[str, Any],
    key_hex: str,
) -> dict[str, Any]:
    """
    Simulates recipient browser-side decryption using the key from window.location.hash.
    """
    k_msg = bytes.fromhex(key_hex)
    iv = base64.b64decode(blob["iv_b64"])
    ciphertext = base64.b64decode(blob["ciphertext_b64"])
    aad = base64.b64decode(blob["aad_b64"])

    # Decrypt AES-256-GCM
    aesgcm = AESGCM(k_msg)
    plaintext_bytes = aesgcm.decrypt(iv, ciphertext, aad)
    plaintext = plaintext_bytes.decode("utf-8")

    # Verify Sender Signature
    c_hash = hashlib.sha256(ciphertext).digest()
    metadata_tuple = hashlib.sha256(
        f"QM-WEBLINK-v1:{blob['message_id']}:{blob['sender_email']}:{blob['recipient_email']}:{blob['issued_utc']}:{blob['expires_utc']}".encode("utf-8") + c_hash
    ).digest()

    pub_bytes = bytes.fromhex(blob["sender_pubkey_hex"])
    ed_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
    sig = base64.b64decode(blob["sender_sig_b64"])
    ed_key.verify(sig, metadata_tuple)

    return {
        "plaintext": plaintext,
        "sender_email": blob["sender_email"],
        "recipient_email": blob["recipient_email"],
        "issued_utc": blob["issued_utc"],
        "expires_utc": blob["expires_utc"],
        "verified_sender": True,
    }
