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


def test_qumail_js_api_ping_and_ports(tmp_path, monkeypatch):
    """Verify ping readiness, account status, and COM port detection."""
    monkeypatch.setenv("QUMAIL_DATA_DIR", str(tmp_path))

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

    # Google OAuth embedded client configuration check
    cfg = api.checkGoogleConfigured()
    assert cfg["configured"] is True
    assert "953431543574" in cfg["clientId"]
    assert cfg["tokenExists"] is False

    # List ports
    ports = api.listPorts()
    assert isinstance(ports, list)

    # Vault lock
    assert api.lockVault() is True


def test_oauth_token_retrieval_safety_when_unauthenticated(tmp_path, monkeypatch):
    """Verify that OAuth operations fail closed safely when unauthenticated."""
    monkeypatch.setenv("QUMAIL_DATA_DIR", str(tmp_path))
    from transport.oauth2_gmail import get_access_token, GmailAuthError
    # Without cached credentials or browser interaction, get_access_token fails cleanly with GmailAuthError
    def mock_flow(*args, **kwargs):
        raise GmailAuthError("Authorization cancelled by user")
    monkeypatch.setattr("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file", mock_flow)
    with pytest.raises(GmailAuthError):
        get_access_token()


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


def test_google_oauth_authorized_user_credentials(tmp_path, monkeypatch):
    """Verify Google OAuth token retrieval and credential persistence."""
    monkeypatch.setenv("QUMAIL_DATA_DIR", str(tmp_path))
    from transport.oauth2_gmail import _save_credentials, _load_credentials
    from google.oauth2.credentials import Credentials
    fake_creds = Credentials(
        token="ya29.test-valid-access-token",
        refresh_token="1//test-refresh-token",
        client_id="test-client-id.apps.googleusercontent.com",
        client_secret="test-client-secret",
    )
    _save_credentials(fake_creds, {"email": "user@gmail.com", "displayName": "Test User", "client_id": "test-client-id.apps.googleusercontent.com", "client_secret": "test-client-secret"})
    loaded_creds, meta = _load_credentials()
    assert loaded_creds is not None
    assert loaded_creds.token == "ya29.test-valid-access-token"
    assert meta["email"] == "user@gmail.com"


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
    assert pq_inbox_msg.get("isQuMail") is True
    assert pq_inbox_msg.get("securityTier") == "pq_sealed"

    # Verify Conventional email: Correctly categorized as Content Shielded (NEUTRAL)
    conv_inbox_msg = next(m for m in inbox if m["id"] == "imap-1002")
    assert "PRIVACY PROTECTION NOTICE" in conv_inbox_msg["body"]
    assert "Shielded" in conv_inbox_msg["subject"]
    assert conv_inbox_msg["indicator"]["badgeLevel"] == "NEUTRAL"
    assert "Content Shielded" in conv_inbox_msg["indicator"]["headline"]
    assert conv_inbox_msg.get("isQuMail") is False
    assert conv_inbox_msg.get("securityTier") == "standard_tls"

    # Safe Deletion Guard: Conventional emails cannot be deleted, while QuMail emails can
    assert api.deleteMessage("imap-1002") is False
    assert api.deleteMessage("imap-1001") is True


def test_starred_and_seen_imap_flag_sync_and_pending_guard(tmp_path, monkeypatch):
    """Verify IMAP \\Flagged/\\Seen hydration, async flag sync, and polling protection."""
    from email.message import EmailMessage
    from transport.imap_receiver import InboxMessage

    vault_file = tmp_path / "vault_flags.sqlite"
    api = QuMailJsApi(account_email="alice@qumail.sec", vault_path=vault_file)
    api.session_state = "MAILBOX_READY"

    sync_calls = []
    monkeypatch.setattr(
        api,
        "_sync_imap_flag_async",
        lambda msg_id, add_flags=None, remove_flags=None: sync_calls.append((msg_id, add_flags, remove_flags)),
    )

    raw_msg = EmailMessage()
    raw_msg["From"] = "news@example.com"
    raw_msg["Subject"] = "Weekly Update"
    raw_msg.set_content("Hello")

    server_item = InboxMessage(
        uid="2001",
        subject="Weekly Update",
        sender="news@example.com",
        date="2026-11-12",
        message=raw_msg,
        starred=True,
        seen=False,
    )
    monkeypatch.setattr("transport.imap_receiver.fetch_inbox", lambda account_email, max_count=30: [server_item])

    msgs = api.fetchInbox()
    target = next(m for m in msgs if m["id"] == "imap-2001")
    assert target["starred"] is True
    assert target["seen"] is False

    # User unstars & marks read locally
    assert api.toggleStar("imap-2001") is True
    assert api.markRead("imap-2001", True) is True
    assert ("imap-2001", None, ["\\Flagged"]) in sync_calls
    assert ("imap-2001", ["\\Seen"], None) in sync_calls

    # Simulate poll returning stale server flags before STORE completes:
    # local edits must be preserved by _pending_flag_updates
    msgs_after_poll = api.fetchInbox()
    target_after = next(m for m in msgs_after_poll if m["id"] == "imap-2001")
    assert target_after["starred"] is False
    assert target_after["seen"] is True
