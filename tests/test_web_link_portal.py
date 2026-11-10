"""
tests/test_web_link_portal.py — Unit and Integration Tests for QuMail Secure Web Link (Pillar 2).

Tests:
1. Client-Side Symmetrical Sealing (AES-256-GCM, CSPRNG key/nonce, AAD binding, composite sender signature).
2. URL Fragment Key Security (Key is embedded in #fragment and NEVER sent to the portal server).
3. Recipient Browser Decryption (Decryption succeeds with valid fragment key, fails closed on tampered data).
4. Ephemeral Portal Backend (Blob staging, rejection of uploaded keys, server-secret keyed HMAC OTP verification, 3-attempt lockout, TTL purge).
"""

import base64
import hashlib
import time
from datetime import datetime, timezone, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from core.web_link_crypto import create_secure_web_link_package, decrypt_secure_web_link_package
from services.portal.server import PortalService, create_portal_app


def test_client_side_sealing_and_url_fragment_key_omission():
    """Verify client-side encryption and ensure key is NOT in uploaded blob."""
    sender_key = ed25519.Ed25519PrivateKey.generate()
    pkg = create_secure_web_link_package(
        plaintext_body="Confidential Corporate Financial Report",
        sender_email="alice@company.invalid",
        recipient_email="bob@external.invalid",
        sender_signing_key=sender_key,
        portal_base_url="https://portal.qumail.invalid",
        validity_days=7,
    )

    blob = pkg["blob_to_upload"]
    url = pkg["access_url"]
    key_hex = pkg["key_hex"]

    # 1. Critical Invariant: Key must NOT be present in blob
    assert "key" not in blob
    assert "key_hex" not in blob
    assert "k_msg" not in blob

    # 2. Critical Invariant: Key must reside exclusively in URL fragment (#...)
    assert f"#{key_hex}" in url
    assert url.startswith("https://portal.qumail.invalid/view/")

    # 3. Decryption using the fragment key must succeed
    decrypted = decrypt_secure_web_link_package(blob, key_hex)
    assert decrypted["plaintext"] == "Confidential Corporate Financial Report"
    assert decrypted["sender_email"] == "alice@company.invalid"
    assert decrypted["verified_sender"] is True


def test_tampered_ciphertext_fails_closed():
    """Verify that any modification to the ciphertext or AAD fails closed."""
    sender_key = ed25519.Ed25519PrivateKey.generate()
    pkg = create_secure_web_link_package(
        plaintext_body="Top Secret Payload",
        sender_email="alice@company.invalid",
        recipient_email="bob@external.invalid",
        sender_signing_key=sender_key,
    )

    blob = pkg["blob_to_upload"]
    key_hex = pkg["key_hex"]

    # Tamper with ciphertext bytes
    raw_ct = bytearray(base64.b64decode(blob["ciphertext_b64"]))
    raw_ct[0] ^= 0xFF
    blob["ciphertext_b64"] = base64.b64encode(raw_ct).decode("ascii")

    # Decryption must fail (AES-GCM authentication failure)
    with pytest.raises(Exception):
        decrypt_secure_web_link_package(blob, key_hex)


def test_portal_service_otp_verification_and_lockout():
    """Verify server-secret keyed HMAC OTP verification and 3-attempt lockout defense."""
    portal = PortalService()
    sender_key = ed25519.Ed25519PrivateKey.generate()

    pkg = create_secure_web_link_package(
        plaintext_body="Quarterly Audit",
        sender_email="auditor@firm.invalid",
        recipient_email="cfo@client.invalid",
        sender_signing_key=sender_key,
    )
    blob = pkg["blob_to_upload"]
    msg_id = pkg["message_id"]

    # 1. Stage blob
    portal.stage_blob(blob)

    # 2. Safety check: Staging a blob that contains a key must be rejected
    bad_blob = dict(blob)
    bad_blob["key_hex"] = "insecure_leak"
    with pytest.raises(ValueError, match="Security violation"):
        portal.stage_blob(bad_blob)

    # 3. Request OTP
    otp_res = portal.request_otp(msg_id, "cfo@client.invalid")
    assert otp_res["status"] == "otp_dispatched"
    test_otp = otp_res["_test_otp"]

    # 4. Attempt with wrong OTP
    with pytest.raises(ValueError, match="Incorrect verification code"):
        portal.verify_otp(msg_id, "000000")

    # 5. Two more wrong attempts -> Permanent lockout
    with pytest.raises(ValueError, match="Incorrect verification code"):
        portal.verify_otp(msg_id, "111111")

    with pytest.raises(ValueError, match="Access locked"):
        portal.verify_otp(msg_id, "222222")

    # 6. Even with the correct OTP now, access is permanently locked!
    with pytest.raises(ValueError, match="exceeded maximum failed attempts"):
        portal.verify_otp(msg_id, test_otp)


def test_portal_ttl_purge_and_sender_revocation():
    """Verify TTL purging and sender revocation."""
    portal = PortalService()
    sender_key = ed25519.Ed25519PrivateKey.generate()

    pkg = create_secure_web_link_package(
        plaintext_body="Expiring Document",
        sender_email="alice@company.invalid",
        recipient_email="bob@external.invalid",
        sender_signing_key=sender_key,
        validity_days=-1,  # Already expired
    )
    blob = pkg["blob_to_upload"]
    msg_id = pkg["message_id"]

    portal.stage_blob(blob)
    assert len(portal.blobs) == 1

    # Purge expired
    purged_count = portal.purge_expired()
    assert purged_count == 1
    assert len(portal.blobs) == 0

    # Sender Revocation
    pkg2 = create_secure_web_link_package(
        plaintext_body="To Be Revoked",
        sender_email="alice@company.invalid",
        recipient_email="bob@external.invalid",
        sender_signing_key=sender_key,
        validity_days=7,
    )
    portal.stage_blob(pkg2["blob_to_upload"])
    portal.revoke_blob(pkg2["message_id"], "alice@company.invalid")

    # Requesting OTP for revoked message must fail
    with pytest.raises(ValueError, match="revoked by the sender"):
        portal.request_otp(pkg2["message_id"], "bob@external.invalid")


def test_portal_html_viewer_endpoint_and_viral_card():
    """Verify that GET /view/<message_id> serves the zero-knowledge WebCrypto page with viral invitation loop."""
    app = create_portal_app()
    client = app.test_client()

    resp = client.get("/view/msg-test-123")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")

    # Invariants: Zero-knowledge client-side script and viral invitation loop
    assert "Zero-Knowledge Secure Portal" in html
    assert "window.crypto.subtle" in html
    assert "window.location.hash" in html
    assert "replaceState" in html
    assert "Secured with QuMail Post-Quantum Technology" in html
    assert "Download for Windows" in html
    assert "Get for Android" in html

    # Verify strict browser defense headers
    assert resp.headers.get("Referrer-Policy") == "no-referrer"
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert "default-src 'self'" in resp.headers.get("Content-Security-Policy", "")
    assert "no-store" in resp.headers.get("Cache-Control", "")


def test_altered_aad_fails_authentication():
    """Verify that altering Authenticated Additional Data (AAD) causes cryptographic failure."""
    sender_key = ed25519.Ed25519PrivateKey.generate()
    pkg = create_secure_web_link_package(
        plaintext_body="Classified AAD Bound Message",
        sender_email="alice@company.invalid",
        recipient_email="bob@external.invalid",
        sender_signing_key=sender_key,
    )
    blob = pkg["blob_to_upload"]
    key_hex = pkg["key_hex"]

    # Alter AAD metadata (tamper with base64 encoded AAD)
    raw_aad = bytearray(base64.b64decode(blob["aad_b64"]))
    raw_aad[0] ^= 0xFF
    blob["aad_b64"] = base64.b64encode(raw_aad).decode("ascii")

    with pytest.raises(Exception):
        decrypt_secure_web_link_package(blob, key_hex)
