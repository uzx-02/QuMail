"""
tests/test_react_desktop_bridge.py — Acceptance and contract tests for the React 19 + WebView2 bridge.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from launch_react_desktop import (
    FRONTEND_DIST,
    DistHTTPRequestHandler,
    QuMailJsApi,
)


def test_frontend_dist_bundle_exists():
    """Verify production Vite build artifacts exist and have required structure."""
    assert FRONTEND_DIST.exists(), f"Frontend dist directory does not exist at {FRONTEND_DIST}"
    index_html = FRONTEND_DIST / "index.html"
    assert index_html.exists(), "frontend/dist/index.html is missing"
    
    content = index_html.read_text(encoding="utf-8")
    assert '<div id="root"' in content, "Root element missing in index.html"
    assert "assets/index-" in content, "Vite hashed assets not linked in index.html"


def test_http_request_handler_mime_types():
    """Verify DistHTTPRequestHandler resolves correct MIME types for modern ES modules."""
    handler = DistHTTPRequestHandler.__new__(DistHTTPRequestHandler)
    assert handler.guess_type("bundle.js") == "application/javascript"
    assert handler.guess_type("module.mjs") == "application/javascript"
    assert handler.guess_type("styles.css") == "text/css"
    assert handler.guess_type("logo.svg") == "image/svg+xml"
    assert handler.guess_type("manifest.json") == "application/json"


def test_qumail_js_api_messages_roundtrip():
    """Verify QuMailJsApi message queries, creation, starring, and deletion on live data."""
    api = QuMailJsApi()
    # Default is clean — zero mock messages
    assert api.account_email == ""
    assert len(api.getMessages()) == 0

    # Sign in
    acc = api.loginAccount("user@company.com", "Jane Doe", "Acme R&D")
    assert acc["email"] == "user@company.com"
    assert acc["displayName"] == "Jane Doe"
    assert acc["isEnrolled"] is True

    # Send a new message
    result = api.sendMessage({
        "recipients": ["security@cert-in.org.in"],
        "subject": "Post-Quantum Handshake Test",
        "body": "Validating ML-KEM-768 encapsulation across live nodes.",
        "attachments": [],
    })
    assert result["success"] is True
    msg_id = result["id"]

    updated_msgs = api.getMessages()
    assert len(updated_msgs) == 1
    new_msg = updated_msgs[0]
    assert new_msg["id"] == msg_id
    assert new_msg["senderEmail"] == "user@company.com"
    assert new_msg["subject"] == "Post-Quantum Handshake Test"
    assert new_msg["indicator"]["badgeLevel"] == "SECURE"

    # Toggle star
    assert api.toggleStar(msg_id) is True
    assert next(m for m in api.getMessages() if m["id"] == msg_id)["starred"] is True

    # Mark read / unread
    assert api.markRead(msg_id, False) is True
    assert next(m for m in api.getMessages() if m["id"] == msg_id)["seen"] is False

    # Delete message (moves to trash first)
    assert api.deleteMessage(msg_id) is True
    assert next(m for m in api.getMessages() if m["id"] == msg_id)["folder"] == "trash"

    # Delete again (purges from trash)
    assert api.deleteMessage(msg_id) is True
    assert len(api.getMessages()) == 0

    # Logout
    assert api.logoutAccount() is True
    assert api.getAccount()["email"] == ""
    assert api.getAccount()["isEnrolled"] is False


def test_qumail_js_api_hsm_and_entropy():
    """Verify QuMailJsApi queries live hardware TRNG coordinator and reports honest status."""
    api = QuMailJsApi()
    status = api.getHSMStatus()

    assert "mode" in status
    assert "isHardwareActive" in status
    # When no real TRNG hardware is connected, isHardwareActive must be False!
    assert status["isHardwareActive"] is False
    assert "shannonEntropy" in status
    assert status["shannonEntropy"] > 7.0
    assert "activePort" in status
    assert "baudRate" in status

    # Sample entropy
    sample = api.sampleEntropy()
    assert sample["success"] is True
    assert len(sample["hex"]) == 64  # 32 bytes hex encoded
    assert sample["rate"] == 115200


def test_qumail_js_api_google_auth_and_ports():
    """Verify Google OAuth configuration methods and COM port detection."""
    api = QuMailJsApi()
    acc = api.getAccount()
    assert acc["email"] == ""
    assert acc["isEnrolled"] is False
    assert acc["kemAlgorithm"] == "ML-KEM-768 (NIST FIPS 203)"
    assert acc["dsaAlgorithm"] == "ML-DSA-65 (NIST FIPS 204)"

    # Check google configuration
    cfg = api.checkGoogleConfigured()
    assert "configured" in cfg
    assert "tokenExists" in cfg

    # Save credentials manually test
    res = api.saveGoogleCredentials("test-id.apps.googleusercontent.com", "test-secret")
    assert res["success"] is True
    assert Path("secrets/gmail_client_secret.json").exists()

    # List ports
    ports = api.listPorts()
    assert isinstance(ports, list)

    # Vault lock
    assert api.lockVault() is True


def test_custom_mailbox_authentication_and_host_inference(tmp_path, monkeypatch):
    """Verify custom mailbox host inference, credentials rejection, and Fernet storage."""
    from transport.custom_mailbox import (
        infer_server_hosts,
        save_custom_account,
        load_custom_account,
        clear_custom_account,
    )

    # 1. Host inference checks
    assert infer_server_hosts("alice@outlook.com") == ("outlook.office365.com", 993, "smtp.office365.com", 587)
    assert infer_server_hosts("bob@gmail.com") == ("imap.gmail.com", 993, "smtp.gmail.com", 587)
    assert infer_server_hosts("charlie@yahoo.com") == ("imap.mail.yahoo.com", 993, "smtp.mail.yahoo.com", 587)
    assert infer_server_hosts("dave@zoho.com") == ("imap.zoho.com", 993, "smtp.zoho.com", 587)
    assert infer_server_hosts("eve@icloud.com") == ("imap.mail.me.com", 993, "smtp.mail.me.com", 587)
    assert infer_server_hosts("user@custom-corp.org") == ("imap.custom-corp.org", 993, "smtp.custom-corp.org", 587)

    # 2. QuMailJsApi rejection of invalid custom mailbox inputs
    api = QuMailJsApi()
    res1 = api.authenticateCustomMailbox({"email": "not-an-email", "password": "pass"})
    assert res1["success"] is False
    assert "valid email" in res1["message"].lower()

    res2 = api.authenticateCustomMailbox({"email": "valid@corp.com", "password": ""})
    assert res2["success"] is False
    assert "password" in res2["message"].lower()

    # 3. Encrypted credentials persistence check
    assert save_custom_account(
        email="test@corp.com",
        password="secret-app-pass",
        display_name="Test User",
        organization="Corp",
        imap_host="imap.corp.com",
        imap_port=993,
    ) is True

    loaded = load_custom_account("test@corp.com")
    assert loaded is not None
    assert loaded["email"] == "test@corp.com"
    assert loaded["password"] == "secret-app-pass"
    assert loaded["imapHost"] == "imap.corp.com"

    # Cleanup
    clear_custom_account()


def test_google_oauth_html_success_page_and_ssl_sanitization(monkeypatch):
    """Verify HTML success landing page has 5-second countdown and SSL environment sanitization."""
    from transport.oauth2_gmail import SUCCESS_HTML_PAGE, sanitize_ssl_environment

    # Verify HTML template structure
    assert "<!DOCTYPE html>" in SUCCESS_HTML_PAGE
    assert "Authentication Successful" in SUCCESS_HTML_PAGE
    assert "window.close()" in SUCCESS_HTML_PAGE
    assert 'id="timer"' in SUCCESS_HTML_PAGE
    assert "5" in SUCCESS_HTML_PAGE

    # Verify SSL sanitization removes nonexistent SSLKEYLOGFILE
    monkeypatch.setenv("SSLKEYLOGFILE", r"C:\nonexistent_qumail_dir_12345\keylog.txt")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", r"C:\nonexistent_qumail_dir_12345\bundle.pem")
    sanitize_ssl_environment()

    import os
    assert "SSLKEYLOGFILE" not in os.environ
    # REQUESTS_CA_BUNDLE was repointed to valid certifi cacert.pem
    assert "nonexistent" not in os.environ.get("REQUESTS_CA_BUNDLE", "")
    assert os.path.exists(os.environ["REQUESTS_CA_BUNDLE"])
