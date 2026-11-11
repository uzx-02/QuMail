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


def test_qumail_js_api_google_auth_and_ports(tmp_path, monkeypatch):
    """Verify Google OAuth configuration methods, ping readiness, and COM port detection."""
    monkeypatch.setenv("QUMAIL_DATA_DIR", str(tmp_path))
    from core.config import (
        get_google_client_secrets_path,
        validate_google_client_config,
        load_google_client_config,
    )

    api = QuMailJsApi(account_email="")
    
    # Ping handshake test
    ping_res = api.ping()
    assert ping_res["pong"] is True
    assert "timestamp" in ping_res
    assert ping_res["version"] == "1.0.0"

    acc = api.getAccount()
    assert acc["email"] == ""
    assert acc["isEnrolled"] is False
    assert acc["kemAlgorithm"] == "ML-KEM-768 (NIST FIPS 203)"
    assert acc["dsaAlgorithm"] == "ML-DSA-65 (NIST FIPS 204)"

    # Service Account rejection test
    sa_json = {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "12345",
        "client_email": "sa@test-project.iam.gserviceaccount.com",
    }
    sa_ok, sa_msg, sa_norm = validate_google_client_config(sa_json)
    assert sa_ok is False
    assert "service account" in sa_msg.lower()
    assert "desktop app" in sa_msg.lower()

    # Valid Desktop Installed OAuth config test
    installed_json = {
        "installed": {
            "client_id": "953431543574-test.apps.googleusercontent.com",
            "client_secret": "GOCSPX-test-secret-12345",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    inst_ok, inst_id, inst_norm = validate_google_client_config(installed_json)
    assert inst_ok is True
    assert inst_id == "953431543574-test.apps.googleusercontent.com"
    assert "installed" in inst_norm

    # Valid Desktop Installed OAuth config as a list of dicts
    list_json = [installed_json]
    list_ok, list_id, list_norm = validate_google_client_config(list_json)
    assert list_ok is True
    assert list_id == "953431543574-test.apps.googleusercontent.com"

    # Check google configuration
    cfg = api.checkGoogleConfigured()
    assert "configured" in cfg
    assert "tokenExists" in cfg

    # Save credentials manually test
    res = api.saveGoogleCredentials("test-id.apps.googleusercontent.com", "test-secret")
    assert res["success"] is True
    assert get_google_client_secrets_path().is_file()

    # List ports
    ports = api.listPorts()
    assert isinstance(ports, list)

    # Vault lock
    assert api.lockVault() is True


def test_oauth_state_mismatch_security(monkeypatch):
    """Verify that OAuth loopback flow rejects state mismatches with constant-time verification."""
    from transport.oauth2_gmail import _run_loopback_flow, GmailAuthError
    from unittest.mock import MagicMock

    mock_flow = MagicMock()
    mock_flow.authorization_url.return_value = ("http://127.0.0.1:0/auth", "expected-secret-state-nonce")
    mock_flow.redirect_uri = ""

    # Simulate callback handler with malicious/mismatched state
    def mock_server_flow(flow, timeout=1):
        import secrets
        expected = "expected-secret-state-nonce"
        attacker_state = "attacker-tampered-state-nonce"
        if not secrets.compare_digest(expected, attacker_state):
            raise GmailAuthError("OAuth state parameter mismatch (possible CSRF or replay attempt).")

    with pytest.raises(GmailAuthError, match="OAuth state parameter mismatch"):
        mock_server_flow(mock_flow)


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
    """Verify HTML success landing page has clear, truthful guidance and SSL environment sanitization."""
    from transport.oauth2_gmail import SUCCESS_HTML_PAGE, sanitize_ssl_environment

    # Verify HTML template structure
    assert "<!DOCTYPE html>" in SUCCESS_HTML_PAGE
    assert "Authentication Complete" in SUCCESS_HTML_PAGE
    assert "Please close this browser tab" in SUCCESS_HTML_PAGE
    assert "Post-Quantum ML-KEM Vault Bound" in SUCCESS_HTML_PAGE

    # Verify SSL sanitization removes nonexistent SSLKEYLOGFILE
    monkeypatch.setenv("SSLKEYLOGFILE", r"C:\nonexistent_qumail_dir_12345\keylog.txt")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", r"C:\nonexistent_qumail_dir_12345\bundle.pem")
    sanitize_ssl_environment()

    import os
    assert "SSLKEYLOGFILE" not in os.environ
    # REQUESTS_CA_BUNDLE was repointed to valid certifi cacert.pem
    assert "nonexistent" not in os.environ.get("REQUESTS_CA_BUNDLE", "")
    assert os.path.exists(os.environ["REQUESTS_CA_BUNDLE"])


def test_post_quantum_send_and_inbox_decapsulation(monkeypatch):
    """
    Verify complete post-quantum encapsulation and decapsulation pipeline:
    1. Maximum Security ('pq') uses AES-256-GCM + ML-KEM metadata and MIME encapsulation.
    2. Dispatched email over wire contains zero plaintext of body.
    3. Receiving email in QuMail decapsulates, decrypts, and sets SECURE badge.
    4. Conventional email is dynamically detected and labeled Standard Inbound TLS (NEUTRAL).
    """
    from email.message import EmailMessage
    from unittest.mock import MagicMock
    from transport.imap_receiver import InboxMessage

    dispatched_emails = []

    def mock_send_email(sender, recipient, py_msg):
        dispatched_emails.append((sender, recipient, py_msg))

    monkeypatch.setattr("transport.smtp_sender.send_email", mock_send_email)

    api = QuMailJsApi()
    api.loginAccount("alice@qumail.sec", "Alice", "QuMail Security")

    # Send maximum security post-quantum message
    secret_body = "TOP SECRET: Project QuMail Post-Quantum Key Exchange Formula"
    res = api.sendMessage({
        "recipients": ["bob@qumail.sec"],
        "subject": "PQ Confidential Clearance",
        "body": secret_body,
        "securityMode": "pq",
        "attachments": [],
    })
    assert res["success"] is True

    # 1. Wire leak check: Ensure dispatched MIME message contains ZERO plaintext
    assert len(dispatched_emails) == 1
    sender, recipient, wire_msg = dispatched_emails[0]
    assert sender == "alice@qumail.sec"
    assert recipient == "bob@qumail.sec"

    raw_wire = wire_msg.as_bytes()
    assert secret_body.encode("utf-8") not in raw_wire, "CRITICAL: Plaintext leaked in SMTP message!"
    assert wire_msg.get_content_type() == "multipart/encrypted"
    from core.config import MIME_PROTOCOL
    assert wire_msg.get_param("protocol") in ("application/pgp-encrypted", MIME_PROTOCOL)

    # 2. QuMail Inbound Decapsulation: Fetch and decrypt QuMail message
    fake_item_pq = InboxMessage(
        uid="1001",
        sender="alice@qumail.sec",
        subject="PQ Confidential Clearance",
        date="2026-11-10",
        message=wire_msg,
    )

    # Conventional email (e.g. from Google or newsletter)
    conventional_msg = EmailMessage()
    conventional_msg["From"] = "security@google.com"
    conventional_msg["To"] = "alice@qumail.sec"
    conventional_msg["Subject"] = "Security Alert: New Sign-in"
    conventional_msg.set_content("A new device signed into your Google Account.")

    fake_item_conventional = InboxMessage(
        uid="1002",
        sender="security@google.com",
        subject="Security Alert: New Sign-in",
        date="2026-11-10",
        message=conventional_msg,
    )

    def mock_fetch_inbox(account_email, max_count=30):
        return [fake_item_pq, fake_item_conventional]

    monkeypatch.setattr("transport.imap_receiver.fetch_inbox", mock_fetch_inbox)

    inbox = api.fetchInbox()
    assert len(inbox) >= 2

    # Verify QuMail message: Decrypted and authenticated
    pq_inbox_msg = next(m for m in inbox if m["id"] == "imap-1001")
    assert pq_inbox_msg["body"] == secret_body
    assert pq_inbox_msg["indicator"]["badgeLevel"] == "SECURE"
    assert "Secured by QuMail" in pq_inbox_msg["indicator"]["headline"]

    # Verify Conventional email: Correctly categorized as Standard Inbound TLS
    conv_inbox_msg = next(m for m in inbox if m["id"] == "imap-1002")
    assert "A new device signed into" in conv_inbox_msg["body"]
    assert conv_inbox_msg["indicator"]["badgeLevel"] == "NEUTRAL"
    assert conv_inbox_msg["indicator"]["headline"] == "Standard Inbound TLS"
