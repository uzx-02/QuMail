"""
core/cloud_directory.py — Client implementation for QuMail Cloud Directory & WebLink Gateway.

Implements:
1. Exact email normalization matching Cloudflare Worker specification.
2. Authenticated POST-body public key directory lookups.
3. Multi-device registration with ML-DSA-65 Proof of Possession.
4. Sender-side full device-set pinning (TOFU) with change and addition warnings.
5. Ephemeral WebLink dispatch with client-side key derivation and server-gated passcode.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import urllib.request

from core.config import get_directory_server_url, get_user_data_dir
from core.logging_config import get_logger

logger = get_logger("cloud_directory")


def normalize_email(raw_email: str) -> str:
    """
    Normalize email according to domain-specific privacy and anti-aliasing rules.
    1. For gmail.com and googlemail.com: strip dots, strip +tags, normalize domain to gmail.com.
    2. For all other domains: lowercase and trim whitespace only (preserve dots and +tags).
    """
    cleaned = raw_email.strip().lower()
    if "@" not in cleaned:
        return cleaned

    local_part, domain = cleaned.split("@", 1)

    if domain == "googlemail.com":
        domain = "gmail.com"

    if domain == "gmail.com":
        no_plus = local_part.split("+")[0]
        no_dots = no_plus.replace(".", "")
        return f"{no_dots}@{domain}"

    return f"{local_part}@{domain}"


class KeyMismatchWarning(Exception):
    """Raised when an existing contact's pinned device key changes unexpectedly."""


class DeviceAddedNotice(Exception):
    """Raised when an existing contact enrolls an additional device."""


class ContactPinningStore:
    """
    Persistent store for contact device-set pinning (TOFU) in the local vault.
    Guards against rogue key injection by recording all active device fingerprints per recipient.
    """

    def __init__(self, data_dir: Optional[str] = None):
        self.store_path = (get_user_data_dir() if data_dir is None else get_user_data_dir()) / "contact_pins.json"
        self._pins: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        try:
            if self.store_path.is_file():
                with open(self.store_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as exc:
            logger.debug("Could not load contact pins: %s", exc)
        return {}

    def _save(self) -> None:
        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.store_path, "w", encoding="utf-8") as f:
                json.dump(self._pins, f, indent=2)
        except Exception as exc:
            logger.debug("Could not persist contact pins: %s", exc)

    def check_and_update_device_set(
        self,
        normalized_email: str,
        incoming_devices: List[Dict[str, Any]],
    ) -> Tuple[bool, str]:
        """
        Check incoming device set against local pinned device set.
        Returns (is_verified, warning_message).
        """
        if not incoming_devices:
            return False, "No active device certificates registered."

        incoming_fps = {d["fingerprint"] for d in incoming_devices}
        stored = self._pins.get(normalized_email)

        # 1. First interaction: Pin complete device set (Trust On First Use)
        if not stored:
            self._pins[normalized_email] = {
                "pinned_at": int(time.time()),
                "fingerprints": sorted(list(incoming_fps)),
                "devices": incoming_devices,
            }
            self._save()
            logger.info("Pinned %d initial device(s) for contact %s (TOFU)", len(incoming_fps), normalized_email)
            return True, ""

        pinned_fps = set(stored.get("fingerprints", []))

        # 2. Exact match: All keys identical
        if incoming_fps == pinned_fps:
            return True, ""

        # 3. New device added (subset expansion)
        if pinned_fps.issubset(incoming_fps):
            new_fps = incoming_fps - pinned_fps
            warning = f"Security Notice: {normalized_email} has added {len(new_fps)} new device(s)."
            # Update pinned set with recorded history
            self._pins[normalized_email]["fingerprints"] = sorted(list(incoming_fps))
            self._pins[normalized_email]["devices"] = incoming_devices
            self._pins[normalized_email]["last_updated"] = int(time.time())
            self._save()
            logger.warning(warning)
            return True, warning

        # 4. Device replaced or mismatched: Unexpected change!
        mismatch_warning = (
            f"SECURITY WARNING: Cryptographic device key for {normalized_email} has changed! "
            f"Expected: {sorted(list(pinned_fps))}, Received: {sorted(list(incoming_fps))}. "
            f"Potential Man-In-The-Middle or device reset. Verify fingerprints out-of-band."
        )
        logger.error(mismatch_warning)
        return False, mismatch_warning


class CloudDirectoryClient:
    """
    Client for interacting with the QuMail 24/7 Cloudflare Public Key Directory & WebLink Gateway.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        session_token: Optional[str] = None,
        http_timeout: float = 8.0,
    ):
        self.base_url = (base_url or get_directory_server_url()).rstrip("/")
        self.session_token = session_token or os.environ.get("QUMAIL_SESSION_TOKEN", "")
        self.timeout = http_timeout
        self.pinning_store = ContactPinningStore()

    def _post(self, path: str, payload: Dict[str, Any], require_auth: bool = False) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "QuMail-Desktop/1.0",
        }
        if require_auth and self.session_token:
            headers["Authorization"] = f"Bearer {self.session_token}"

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as err:
            err_body = err.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(err_body)
                msg = parsed.get("error", err_body)
            except Exception:
                msg = err_body
            raise RuntimeError(f"Directory request failed ({err.code}): {msg}") from err
        except Exception as exc:
            raise RuntimeError(f"Could not connect to QuMail Directory: {exc}") from exc

    def get_challenge(self) -> str:
        """Fetch fresh Proof-of-Possession challenge nonce."""
        res = self._post("/api/v1/auth/challenge", {})
        return res.get("nonce_hex", "")

    def register_google(
        self,
        id_token: str,
        device_id: str,
        device_label: str,
        kem_public_bytes: bytes,
        dsa_public_bytes: bytes,
        pop_signature_bytes: bytes,
        server_nonce: str,
    ) -> Dict[str, Any]:
        """Enroll device using Google OIDC ID token."""
        payload = {
            "id_token": id_token,
            "device_id": device_id,
            "device_label": device_label,
            "public_key_bundle": {
                "kem_public_base64": base64.b64encode(kem_public_bytes).decode("ascii"),
                "dsa_public_base64": base64.b64encode(dsa_public_bytes).decode("ascii"),
            },
            "pop_signature": base64.b64encode(pop_signature_bytes).decode("ascii"),
            "server_nonce": server_nonce,
        }
        res = self._post("/api/v1/auth/google", payload)
        if res.get("session_token"):
            self.session_token = res["session_token"]
        return res

    def send_custom_otp(self, email: str, turnstile_token: str = "") -> Dict[str, Any]:
        """Dispatch 6-digit OTP to custom mailbox via Cloudflare Worker & Resend."""
        return self._post("/api/v1/auth/custom/send-otp", {
            "email": email,
            "turnstile_token": turnstile_token,
        })

    def verify_custom_otp_and_enroll(
        self,
        email: str,
        challenge_id: str,
        otp: str,
        device_id: str,
        device_label: str,
        kem_public_bytes: bytes,
        dsa_public_bytes: bytes,
        pop_signature_bytes: bytes,
        server_nonce: str,
    ) -> Dict[str, Any]:
        """Verify OTP and enroll device."""
        payload = {
            "email": email,
            "challenge_id": challenge_id,
            "otp": otp,
            "device_id": device_id,
            "device_label": device_label,
            "public_key_bundle": {
                "kem_public_base64": base64.b64encode(kem_public_bytes).decode("ascii"),
                "dsa_public_base64": base64.b64encode(dsa_public_bytes).decode("ascii"),
            },
            "pop_signature": base64.b64encode(pop_signature_bytes).decode("ascii"),
            "server_nonce": server_nonce,
        }
        res = self._post("/api/v1/auth/custom/verify-otp", payload)
        if res.get("session_token"):
            self.session_token = res["session_token"]
        return res

    def lookup(self, recipient_email: str) -> Dict[str, Any]:
        """
        Query public key directory via authenticated POST body (metadata-minimized).
        Returns device certificates and evaluates client-side TOFU pinning.
        """
        norm_email = normalize_email(recipient_email)
        res = self._post("/api/v1/directory/lookup", {"email": norm_email}, require_auth=True)

        if not res.get("found") or not res.get("devices"):
            return {
                "found": False,
                "email": norm_email,
                "devices": [],
                "verified": False,
                "warning": "Recipient has not registered with QuMail.",
            }

        devices = res["devices"]
        is_ok, warning = self.pinning_store.check_and_update_device_set(norm_email, devices)

        return {
            "found": True,
            "email": norm_email,
            "devices": devices,
            "verified": is_ok,
            "warning": warning,
        }

    def create_weblink(
        self,
        plaintext_body: str,
        sender_email: str,
        recipient_email: str,
        passcode: Optional[str] = None,
        max_views: int = 5,
        burn_after_read: bool = False,
        ttl_days: int = 7,
    ) -> Dict[str, Any]:
        """
        Generate Ephemeral WebLink (Pillar 2).
        Encrypts payload client-side with AES-256-GCM.
        Generates secret URL fragment (#key=...) that is never transmitted to Cloudflare.
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        raw_aes_key = secrets.token_bytes(32)
        iv = secrets.token_bytes(12)

        has_passcode = bool(passcode and passcode.strip())
        passcode_salt_hex = ""
        passcode_tag = ""

        # Derive encryption key if passcode is configured
        if has_passcode:
            salt_bytes = secrets.token_bytes(16)
            passcode_salt_hex = salt_bytes.hex()
            # K = HMAC-SHA256(raw_key, passcode)
            enc_key = hmac_bytes(raw_aes_key, passcode.strip().encode("utf-8"))
            # Tag for server gate authentication
            passcode_tag = hashlib.sha256(passcode.strip().encode("utf-8") + salt_bytes).hexdigest()
        else:
            enc_key = raw_aes_key

        # Encrypt payload
        aesgcm = AESGCM(enc_key)
        payload_bytes = plaintext_body.encode("utf-8")
        ciphertext = aesgcm.encrypt(iv, payload_bytes, None)

        payload = {
            "encrypted_payload": base64.b64encode(ciphertext).decode("ascii"),
            "iv_hex": iv.hex(),
            "has_passcode": has_passcode,
            "passcode_tag": passcode_tag if has_passcode else None,
            "passcode_salt_hex": passcode_salt_hex if has_passcode else None,
            "max_views": max_views,
            "burn_after_read": burn_after_read,
            "ttl_days": ttl_days,
        }

        res = self._post("/api/v1/weblinks/create", payload, require_auth=True)
        link_id = res.get("link_id", "")
        access_url = res.get("access_url", f"{self.base_url}/v/{link_id}")

        # The decryption key is appended strictly to the URL fragment (#)
        full_url = f"{access_url}#key={raw_aes_key.hex()}"

        return {
            "link_id": link_id,
            "access_url": full_url,
            "has_passcode": has_passcode,
            "expires_at": res.get("expires_at"),
            "burn_after_read": burn_after_read,
        }


def hmac_bytes(key: bytes, msg: bytes) -> bytes:
    import hmac
    return hmac.new(key, msg, hashlib.sha256).digest()
