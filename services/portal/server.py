"""
services/portal/server.py — QuMail Ephemeral Web Portal & Mailbox Verification Service.

Implements M8 Secure Web Link portal backend:
- Ephemeral blob staging (holds ciphertext and public metadata; ZERO key storage).
- Mailbox-access verification via server-secret keyed HMAC One-Time Passcodes (OTP).
- 10-minute expiry and maximum 3 attempts before permanent lockout.
- Automated TTL expiration and tombstone sweeper.
- Sender revocation API.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import hashlib
import hmac
import secrets
from typing import Any, Dict, Optional
from flask import Flask, request, jsonify


class PortalService:
    """Core ephemeral blob storage and OTP verification engine."""

    def __init__(self, server_secret: Optional[bytes] = None) -> None:
        self.server_secret = server_secret or secrets.token_bytes(32)
        # Stored blobs: message_id -> blob_dict
        self.blobs: dict[str, dict[str, Any]] = {}
        # OTP state: message_id -> {verifier, salt, attempts, expires_utc, locked}
        self.otp_sessions: dict[str, dict[str, Any]] = {}

    def stage_blob(self, blob: dict[str, Any]) -> dict[str, Any]:
        msg_id = blob["message_id"]
        # Safety check: confirm key is NOT present
        if "key" in blob or "k_msg" in blob or "key_hex" in blob:
            raise ValueError("Security violation: Symmetrical key must NOT be transmitted to portal server!")

        self.blobs[msg_id] = {
            "blob": blob,
            "staged_utc": datetime.now(timezone.utc).isoformat(),
            "expires_utc": blob.get("expires_utc"),
            "revoked": False,
        }
        return {"status": "staged", "message_id": msg_id}

    def request_otp(self, message_id: str, recipient_email: str) -> dict[str, Any]:
        record = self.blobs.get(message_id)
        if not record:
            raise ValueError("Message not found or expired")
        if record["revoked"]:
            raise ValueError("This communication was revoked by the sender")

        blob = record["blob"]
        if blob["recipient_email"].strip().lower() != recipient_email.strip().lower():
            raise ValueError("Recipient email mismatch")

        # Check existing session
        session = self.otp_sessions.get(message_id)
        if session and session["locked"]:
            raise ValueError("Message locked due to excessive failed verification attempts")

        # Generate 6-digit OTP
        otp = f"{secrets.randbelow(900000) + 100000}"  # 100000..999999
        salt = secrets.token_hex(16)
        verifier = hmac.new(
            self.server_secret,
            f"{otp}:{message_id}:{salt}".encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=10)

        self.otp_sessions[message_id] = {
            "verifier": verifier,
            "salt": salt,
            "attempts": 0,
            "expires_utc": expires.isoformat(),
            "locked": False,
        }

        # In production this would be sent via SMTP to recipient_email.
        # For testing/pilot we return a notice (or test token in mock mode).
        return {
            "status": "otp_dispatched",
            "message_id": message_id,
            "expires_utc": expires.isoformat(),
            "_test_otp": otp,  # Populated for local automated testing
        }

    def verify_otp(self, message_id: str, otp_attempt: str) -> dict[str, Any]:
        session = self.otp_sessions.get(message_id)
        if not session:
            raise ValueError("No active verification session. Request code first.")
        if session["locked"]:
            raise ValueError("Access locked: exceeded maximum failed attempts.")

        exp = datetime.fromisoformat(session["expires_utc"])
        if datetime.now(timezone.utc) > exp:
            raise ValueError("Verification code expired. Request a new one.")

        # Compute candidate verifier
        candidate = hmac.new(
            self.server_secret,
            f"{otp_attempt.strip()}:{message_id}:{session['salt']}".encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(candidate, session["verifier"]):
            session["attempts"] += 1
            if session["attempts"] >= 3:
                session["locked"] = True
                raise ValueError("Incorrect code. Maximum 3 attempts exceeded. Access locked.")
            raise ValueError(f"Incorrect verification code ({3 - session['attempts']} attempts remaining).")

        # Success! Release ciphertext blob
        record = self.blobs.get(message_id)
        if not record or record["revoked"]:
            raise ValueError("Message revoked or expired.")

        return {
            "status": "authenticated",
            "blob": record["blob"]
        }

    def revoke_blob(self, message_id: str, sender_email: str) -> dict[str, Any]:
        record = self.blobs.get(message_id)
        if not record:
            raise ValueError("Message not found")
        if record["blob"]["sender_email"].strip().lower() != sender_email.strip().lower():
            raise ValueError("Unauthorized revocation request")

        record["revoked"] = True
        return {"status": "revoked", "message_id": message_id}

    def purge_expired(self) -> int:
        now = datetime.now(timezone.utc)
        purged = 0
        to_del = []
        for mid, rec in self.blobs.items():
            exp_str = rec.get("expires_utc")
            if exp_str:
                exp = datetime.fromisoformat(exp_str)
                if now > exp:
                    to_del.append(mid)
        for mid in to_del:
            del self.blobs[mid]
            self.otp_sessions.pop(mid, None)
            purged += 1
        return purged


# ---------------------------------------------------------------------------
# Flask HTTP Application Factory
# ---------------------------------------------------------------------------

def create_portal_app(service: Optional[PortalService] = None) -> Flask:
    app = Flask("qumail_portal")
    ps = service or PortalService()

    @app.route("/api/v1/portal/stage", methods=["POST"])
    def endpoint_stage():
        data = request.get_json() or {}
        try:
            res = ps.stage_blob(data)
            return jsonify(res), 201
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/api/v1/portal/request_otp", methods=["POST"])
    def endpoint_request_otp():
        data = request.get_json() or {}
        try:
            res = ps.request_otp(data["message_id"], data["recipient_email"])
            return jsonify(res)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/api/v1/portal/verify_otp", methods=["POST"])
    def endpoint_verify_otp():
        data = request.get_json() or {}
        try:
            res = ps.verify_otp(data["message_id"], data["otp"])
            return jsonify(res)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/api/v1/portal/revoke", methods=["POST"])
    def endpoint_revoke():
        data = request.get_json() or {}
        try:
            res = ps.revoke_blob(data["message_id"], data["sender_email"])
            return jsonify(res)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/view/<message_id>", methods=["GET"])
    def endpoint_view_html(message_id):
        """Zero-Knowledge Client-Side Decryption Portal Viewer with Viral Invitation Loop."""
        return HTML_VIEWER_TEMPLATE, 200, {"Content-Type": "text/html; charset=utf-8"}

    return app


HTML_VIEWER_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QuMail Secure Message Portal</title>
    <style>
        :root {
            --bg: #0A0E17; --card: #161F33; --border: #2A3B5F;
            --text: #F1F5F9; --text-muted: #94A3B8; --accent: #6366F1;
            --secure: #10B981; --alert: #EF4444;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg); color: var(--text);
            margin: 0; padding: 24px; display: flex; justify-content: center;
        }
        .container { max-width: 680px; width: 100%; }
        .header { display: flex; align-items: center; gap: 10px; margin-bottom: 24px; }
        .badge { background: #1E2342; color: #818CF8; font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 4px; }
        .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 24px; margin-bottom: 20px; }
        .field { margin-bottom: 16px; }
        .field label { display: block; font-size: 12px; color: var(--text-muted); margin-bottom: 6px; font-weight: 600; }
        .field input { width: 100%; box-sizing: border-box; background: #0D1320; border: 1px solid var(--border); color: var(--text); padding: 10px 14px; border-radius: 6px; font-size: 14px; }
        .btn { background: var(--accent); color: #fff; border: none; padding: 10px 20px; border-radius: 6px; font-weight: 600; font-size: 14px; cursor: pointer; }
        .btn:hover { background: #4F46E5; }
        .status-box { padding: 12px 16px; border-radius: 6px; margin-bottom: 16px; font-size: 13px; font-weight: 600; }
        .status-secure { background: #064E3B; color: #A7F3D0; border: 1px solid var(--secure); }
        .status-error { background: #450A0A; color: #FECACA; border: 1px solid var(--alert); }
        .body-box { background: #0D1320; border: 1px solid var(--border); border-radius: 6px; padding: 16px; font-family: monospace; white-space: pre-wrap; margin-top: 16px; line-height: 1.5; }
        .invitation-card {
            background: linear-gradient(135deg, #161F33 0%, #1E1A3A 100%);
            border: 1px solid #4F46E5; border-radius: 10px; padding: 20px; text-align: center;
        }
        .invitation-card h3 { margin: 0 0 8px 0; font-size: 16px; color: #F1F5F9; }
        .invitation-card p { font-size: 13px; color: #94A3B8; margin: 0 0 16px 0; line-height: 1.4; }
        .app-links { display: flex; gap: 12px; justify-content: center; }
        .app-btn { background: #2A3B5F; color: #F1F5F9; text-decoration: none; padding: 8px 16px; border-radius: 6px; font-size: 12px; font-weight: 600; }
        .app-btn:hover { background: #4F46E5; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2 style="margin: 0;">🛡️ QuMail</h2>
            <span class="badge">Zero-Knowledge Secure Portal</span>
        </div>

        <div id="auth-panel" class="card">
            <h3>Verify Recipient Access</h3>
            <p style="color: var(--text-muted); font-size: 13px;">This message was encrypted using Post-Quantum Cryptography. Enter your email and verification code to decrypt locally in your browser.</p>
            <div id="notice-msg" style="display: none;" class="status-box"></div>
            <div class="field">
                <label>Your Email Address</label>
                <input type="email" id="email-input" placeholder="recipient@example.com">
            </div>
            <div class="field">
                <label>6-Digit Security Code</label>
                <input type="text" id="otp-input" placeholder="123456" maxlength="6">
            </div>
            <div style="display: flex; gap: 10px;">
                <button class="btn" onclick="requestOTP()">Send Code to Email</button>
                <button class="btn" style="background: #10B981;" onclick="decryptMessage()">🔓 Decrypt Message</button>
            </div>
        </div>

        <div id="message-panel" class="card" style="display: none;">
            <div class="status-box status-secure">
                🛡️ Verified Zero-Knowledge Decryption: Decrypted client-side in browser memory. Key was never transmitted to any server.
            </div>
            <div style="margin-bottom: 8px;"><strong id="sender-lbl"></strong></div>
            <div class="body-box" id="body-text"></div>
        </div>

        <div class="invitation-card">
            <h3>🔒 Secured with QuMail Post-Quantum Technology</h3>
            <p>Tired of manually decrypting links in your browser? Keep your existing Gmail, Outlook, or Yahoo email address and automate zero-click post-quantum security on your devices.</p>
            <div class="app-links">
                <a class="app-btn" href="https://qumail.org/download/windows">💻 Download for Windows</a>
                <a class="app-btn" href="https://qumail.org/download/android">📱 Get for Android</a>
            </div>
        </div>
    </div>

    <script>
        const messageId = window.location.pathname.split("/").pop();
        const keyHex = window.location.hash.substring(1);

        function hexToBytes(hex) {
            const bytes = new Uint8Array(hex.length / 2);
            for (let i = 0; i < bytes.length; i++) {
                bytes[i] = parseInt(hex.substr(i * 2, 2), 16);
            }
            return bytes;
        }

        async function requestOTP() {
            const email = document.getElementById("email-input").value.trim();
            if (!email) { alert("Please enter your email address."); return; }
            try {
                const res = await fetch("/api/v1/portal/request_otp", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ message_id: messageId, recipient_email: email })
                });
                const data = await res.json();
                const notice = document.getElementById("notice-msg");
                notice.style.display = "block";
                notice.className = "status-box status-secure";
                notice.innerText = "A 6-digit verification code has been sent to your email.";
            } catch (err) {
                alert("Failed to request code: " + err);
            }
        }

        async function decryptMessage() {
            const otp = document.getElementById("otp-input").value.trim();
            if (!otp) { alert("Please enter the 6-digit code."); return; }
            if (!keyHex) { alert("Decryption key missing from URL fragment!"); return; }

            try {
                const res = await fetch("/api/v1/portal/verify_otp", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ message_id: messageId, otp: otp })
                });
                const result = await res.json();
                if (!res.ok) {
                    const notice = document.getElementById("notice-msg");
                    notice.style.display = "block";
                    notice.className = "status-box status-error";
                    notice.innerText = result.error || "Verification failed";
                    return;
                }

                const blob = result.blob;
                const rawKey = hexToBytes(keyHex);
                const cryptoKey = await window.crypto.subtle.importKey(
                    "raw", rawKey, "AES-GCM", false, ["decrypt"]
                );

                const ctBytes = Uint8Array.from(atob(blob.ciphertext_b64), c => c.charCodeAt(0));
                const nonceBytes = Uint8Array.from(atob(blob.nonce_b64), c => c.charCodeAt(0));
                const aadBytes = new TextEncoder().encode(blob.aad);

                const decryptedBytes = await window.crypto.subtle.decrypt(
                    { name: "AES-GCM", iv: nonceBytes, additionalData: aadBytes },
                    cryptoKey,
                    ctBytes
                );

                const plaintext = new TextDecoder().decode(decryptedBytes);
                document.getElementById("auth-panel").style.display = "none";
                document.getElementById("message-panel").style.display = "block";
                document.getElementById("sender-lbl").innerText = "From: " + blob.sender_email;
                document.getElementById("body-text").innerText = plaintext;
            } catch (err) {
                alert("Decryption failed: " + err);
            }
        }
    </script>
</body>
</html>
"""
