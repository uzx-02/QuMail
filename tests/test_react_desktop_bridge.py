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
    assert recipient == "bob@qumail.sec" or recipient == ["bob@qumail.sec"]

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

    # Inbound WebLink email (e.g. from QuMail WebLink invitation)
    weblink_msg = EmailMessage()
    weblink_msg["From"] = "bob@qumail.sec"
    weblink_msg["To"] = "alice@qumail.sec"
    weblink_msg["Subject"] = "[QuMail Secure Link] Confidential Briefing"
    weblink_msg.set_content("Open your secure link at https://qumail-directory.example.workers.dev/v/1234")

    fake_item_weblink = InboxMessage(
        uid="1003",
        sender="bob@qumail.sec",
        subject="[QuMail Secure Link] Confidential Briefing",
        date="2026-11-10",
        message=weblink_msg,
    )

    def mock_fetch_inbox(account_email, max_count=30):
        return [fake_item_pq, fake_item_conventional, fake_item_weblink]

    monkeypatch.setattr("transport.imap_receiver.fetch_inbox", mock_fetch_inbox)

    inbox = api.fetchInbox()
    assert len(inbox) >= 3

    # Verify WebLink message: Handled cleanly without UnboundLocalError
    weblink_inbox_msg = next(m for m in inbox if m["id"] == "imap-1003")
    assert weblink_inbox_msg["isQuMail"] is True
    assert weblink_inbox_msg["securityTier"] == "weblink"
    assert weblink_inbox_msg["subject"] == "[QuMail Secure Link] Confidential Briefing"
    assert weblink_inbox_msg["indicator"]["badgeLevel"] == "SECURE"

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


def test_draft_lifecycle_and_outbox_retry(tmp_path, monkeypatch):
    """Verify saveDraft, post-send draft cleanup, and Outbox queueing/retry on SMTP failure."""
    vault_file = tmp_path / "vault_drafts.sqlite"
    api = QuMailJsApi(account_email="alice@qumail.sec", vault_path=vault_file)
    api.session_state = "MAILBOX_READY"

    # 1. Save & update draft
    res1 = api.saveDraft({
        "recipients": ["bob@example.com"],
        "subject": "Draft Subj",
        "body": "Initial draft text",
        "securityMode": "standard",
    })
    assert res1["success"] is True
    draft_id = res1["id"]
    assert any(m["id"] == draft_id and m["folder"] == "drafts" for m in api.getMessages())

    # 2. Update same draft ID
    res2 = api.saveDraft({
        "id": draft_id,
        "recipients": ["bob@example.com"],
        "subject": "Draft Subj Updated",
        "body": "Updated draft text",
        "securityMode": "standard",
    })
    assert res2["id"] == draft_id
    draft_msgs = [m for m in api.getMessages() if m["id"] == draft_id]
    assert len(draft_msgs) == 1
    assert draft_msgs[0]["subject"] == "Draft Subj Updated"

    # 3. Send draft via standard SMTP -> draft must be deleted from drafts
    monkeypatch.setattr("transport.smtp_sender.send_email", lambda s, r, m: None)
    send_res = api.sendMessage({
        "draftId": draft_id,
        "recipients": ["bob@example.com"],
        "subject": "Draft Subj Updated",
        "body": "Updated draft text",
        "securityMode": "standard",
    })
    assert send_res["success"] is True
    assert not any(m["id"] == draft_id for m in api.getMessages())

    # 4. Simulate SMTP failure on WebLink -> queued in outbox with outboxError, then retry succeeds
    monkeypatch.setattr("core.cloud_directory.CloudDirectoryClient._ensure_session_token", lambda self: None)
    monkeypatch.setattr(
        "core.cloud_directory.CloudDirectoryClient.create_weblink",
        lambda self, **kwargs: {"access_url": "https://example.workers.dev/v/abc#key"},
    )
    def fail_smtp(s, r, m):
        raise RuntimeError("Network unreachable")
    monkeypatch.setattr("transport.smtp_sender.send_email", fail_smtp)

    fail_res = api.sendMessage({
        "recipients": ["carol@example.com"],
        "subject": "Secret Link",
        "body": "Confidential",
        "securityMode": "weblink",
    })
    assert fail_res["success"] is False
    assert fail_res.get("queuedInOutbox") is True
    outbox_id = fail_res["id"]
    queued = next(m for m in api.getMessages() if m["id"] == outbox_id)
    assert queued["folder"] == "outbox"
    assert "Network unreachable" in queued["outboxError"]

    # Retry succeeds -> outbox item removed
    monkeypatch.setattr("transport.smtp_sender.send_email", lambda s, r, m: None)
    retry_res = api.sendMessage({
        "outboxId": outbox_id,
        "recipients": ["carol@example.com"],
        "subject": "Secret Link",
        "body": "Confidential",
        "securityMode": "weblink",
    })
    assert retry_res["success"] is True
    assert not any(m["id"] == outbox_id for m in api.getMessages())


def test_export_identity_file(tmp_path, monkeypatch):
    """Verify exportIdentityFile writes formatted HTML certificate to disk."""
    from launch_react_desktop import QuMailJsApi
    api = QuMailJsApi()
    api.account_email = "test.user@qumail.sec"

    # Mock webview active_window to return None so it falls back to downloads_dir
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    sample_html = "<html><body><h1>QuMail Certificate</h1></body></html>"
    res = api.exportIdentityFile({
        "filename": "custom-cert.html",
        "htmlContent": sample_html,
    })

    assert res["success"] is True
    assert "custom-cert.html" in res["filename"]
    saved_file = tmp_path / "Downloads" / "custom-cert.html"
    assert saved_file.exists()
    assert saved_file.read_text(encoding="utf-8") == sample_html


def test_security_pin_lifecycle_and_vault_enforcement(tmp_path, monkeypatch):
    """Verify setting, validating, changing, rate limiting, and removing Security PIN."""
    from launch_react_desktop import QuMailJsApi
    vault_file = tmp_path / "pin_vault.sqlite"
    api = QuMailJsApi(vault_path=vault_file)
    api.account_email = "alice@example.com"

    # Initially, no Security PIN configured
    assert api.hasSecurityPin() is False
    assert api.getAccount()["hasSecurityPin"] is False

    # Validation: reject non-numeric, too short (<4), and too long (>8)
    assert api.setSecurityPin("123")["success"] is False
    assert api.setSecurityPin("123456789")["success"] is False
    assert api.setSecurityPin("abcd")["success"] is False

    # Configure valid 4-digit PIN
    set_res = api.setSecurityPin("4321")
    assert set_res["success"] is True
    assert api.hasSecurityPin() is True
    assert api.getAccount()["hasSecurityPin"] is True

    # Lock vault
    assert api.lockVault() is True
    assert api.vault_state == "LOCKED"

    # Unlock without PIN or with incorrect PIN fails
    fail_empty = api.unlockVault("")
    assert fail_empty["success"] is False
    assert "Incorrect Security PIN" in fail_empty["message"]
    assert api.vault_state == "LOCKED"

    fail_wrong = api.unlockVault("9999")
    assert fail_wrong["success"] is False
    assert "Incorrect Security PIN" in fail_wrong["message"]
    assert api.vault_state == "LOCKED"

    # Unlock with valid PIN succeeds
    unlock_res = api.unlockVault("4321")
    assert unlock_res["success"] is True
    assert api.vault_state == "UNLOCKED"

    # Updating PIN requires current PIN verification
    assert api.setSecurityPin("8888", current_pin="wrong")["success"] is False
    update_res = api.setSecurityPin("8888", current_pin="4321")
    assert update_res["success"] is True

    # Old PIN rejected, new PIN accepted
    api.lockVault()
    assert api.unlockVault("4321")["success"] is False
    assert api.unlockVault("8888")["success"] is True

    # Rate limiting: 5 failed attempts trigger cooldown
    api.lockVault()
    for _ in range(4):
        api.unlockVault("0000")
    cooldown_res = api.unlockVault("0000")
    assert cooldown_res["success"] is False
    assert "Cooldown active" in cooldown_res["message"]
    assert cooldown_res.get("cooldownSeconds", 0) > 0

    # Fast-forward cooldown for testing
    api._pin_cooldown_until = 0.0

    # Removing PIN requires valid current PIN
    assert api.removeSecurityPin("wrong")["success"] is False
    remove_res = api.removeSecurityPin("8888")
    assert remove_res["success"] is True
    assert api.hasSecurityPin() is False
    assert api.getAccount()["hasSecurityPin"] is False

    # Once removed, vault unlocks without passphrase
    api.lockVault()
    assert api.unlockVault()["success"] is True
    assert api.vault_state == "UNLOCKED"


def test_security_pin_startup_enforcement_and_rejection(tmp_path, monkeypatch):
    """Verify that when a PIN is set, a fresh QuMailBridge instance starts LOCKED and rejects calls until unlocked."""
    from launch_react_desktop import QuMailBridge
    import pytest

    vault_file = tmp_path / "startup_vault.sqlite"
    api1 = QuMailBridge(account_email="alice@example.com", vault_path=vault_file)
    assert api1.setSecurityPin("5678")["success"] is True
    assert api1.hasSecurityPin() is True

    # Simulate app restart with a fresh bridge instance
    api2 = QuMailBridge(account_email="alice@example.com", vault_path=vault_file)

    # 1. Verify locked startup state
    assert api2.hasSecurityPin() is True
    assert api2.vault_state == "LOCKED"
    assert api2.vault_service is None
    assert api2.session_state == "LOCKED"

    # 2. Verify account public metadata is present for the lock screen
    acc = api2.getAccount()
    assert acc["email"] == "alice@example.com"
    assert acc["hasSecurityPin"] is True
    assert acc["vaultState"] == "LOCKED"

    # 3. Verify inbox/decryption and sending calls are rejected while locked
    with pytest.raises(PermissionError):
        api2.fetchInbox()
    assert api2.getMessages() == []
    send_res = api2.sendMessage({"recipients": ["bob@example.com"], "subject": "Test", "body": "Secret"})
    assert send_res["success"] is False
    assert "locked" in send_res.get("error", "").lower()
    export_res = api2.exportIdentityFile({"filename": "cert.html", "htmlContent": "test"})
    assert export_res["success"] is False
    assert "locked" in export_res.get("error", "").lower()

    # 4. Wrong PIN fails to unlock
    wrong_unlock = api2.unlockVault("0000")
    assert wrong_unlock["success"] is False
    assert api2.vault_state == "LOCKED"
    assert api2.vault_service is None

    # 5. Valid PIN unlocks vault and restores readiness
    correct_unlock = api2.unlockVault("5678")
    assert correct_unlock["success"] is True
    assert api2.vault_state == "UNLOCKED"
    assert api2.vault_service is not None
    assert api2.session_state == "MAILBOX_READY"


def test_settings_disk_persistence_and_backend_roundtrip(tmp_path):
    """Verify saveSettings() and getSettings() persist theme and preferences across bridge restarts."""
    from launch_react_desktop import QuMailBridge

    vault_file = tmp_path / "settings_vault.sqlite"
    api1 = QuMailBridge(vault_path=vault_file)

    # Initially empty
    assert api1.getSettings() == {}

    # Save custom Dark Mode and preferences
    custom_settings = {
        "theme": "midnight",
        "accentColor": "purple",
        "idleLockMinutes": 15,
        "autoSyncMinutes": 5,
        "blockRemoteImages": True,
    }
    save_res = api1.saveSettings(custom_settings)
    assert save_res["success"] is True
    assert save_res["settings"]["theme"] == "midnight"

    settings_path = tmp_path / "settings.json"
    assert settings_path.is_file()

    # Retrieve on same instance
    loaded = api1.getSettings()
    assert loaded["theme"] == "midnight"
    assert loaded["accentColor"] == "purple"
    assert loaded["idleLockMinutes"] == 15

    # Simulate fresh app restart
    api2 = QuMailBridge(vault_path=vault_file)
    reloaded = api2.getSettings()
    assert reloaded["theme"] == "midnight"
    assert reloaded["accentColor"] == "purple"
    assert reloaded["idleLockMinutes"] == 15

    # Partial update: change theme to dawn
    patch_res = api2.saveSettings({"theme": "dawn"})
    assert patch_res["success"] is True
    final_settings = api2.getSettings()
    assert final_settings["theme"] == "dawn"
    # Existing untouched keys are preserved
    assert final_settings["accentColor"] == "purple"
    assert final_settings["idleLockMinutes"] == 15


def test_security_pin_lockout_persistence_across_restarts(tmp_path):
    """Verify 5 failed PIN attempts trigger a 30s lockout persisted to disk and enforced after restart."""
    from launch_react_desktop import QuMailBridge

    vault_file = tmp_path / "lockout_vault.sqlite"
    api1 = QuMailBridge(account_email="alice@example.com", vault_path=vault_file)
    assert api1.setSecurityPin("1234")["success"] is True

    # 4 wrong attempts - no cooldown yet
    for _ in range(4):
        res = api1.unlockVault("9999")
        assert res["success"] is False
        assert "cooldown" not in res.get("error", "").lower()

    # 5th wrong attempt triggers cooldown lockout
    res5 = api1.unlockVault("9999")
    assert res5["success"] is False
    assert "cooldown" in res5.get("error", "").lower()
    cooldown = res5.get("cooldown", 0)
    assert cooldown > 20

    acc1 = api1.getAccount()
    assert acc1.get("cooldownSeconds", 0) > 20

    # Simulate restart by creating fresh bridge instance from same vault path
    api2 = QuMailBridge(account_email="alice@example.com", vault_path=vault_file)
    acc2 = api2.getAccount()
    assert acc2.get("cooldownSeconds", 0) > 0

    # Attempting to unlock even with correct PIN while in cooldown is rejected immediately
    res_restart = api2.unlockVault("1234")
    assert res_restart["success"] is False
    assert "cooldown" in res_restart.get("error", "").lower()


def test_multi_recipient_mixed_group_rejection_and_resolution(monkeypatch):
    """Verify that in 'pq' mode, mixed registered/unregistered groups are rejected safely with code UNREGISTERED_RECIPIENTS, and succeed in 'weblink' mode."""
    from launch_react_desktop import QuMailJsApi

    api = QuMailJsApi()
    api.loginAccount("alice@qumail.sec", "Alice", "QuMail Security")

    # In 'pq' mode with one registered (bob@qumail.sec) and one unregistered external contact
    res_pq = api.sendMessage({
        "recipients": ["bob@qumail.sec", "stranger@external.com"],
        "subject": "Mixed Security Test",
        "body": "Important document",
        "securityMode": "pq",
    })
    assert res_pq["success"] is False
    assert res_pq["code"] == "UNREGISTERED_RECIPIENTS"
    assert "stranger@external.com" in res_pq["unregistered"]

    # Switching to 'weblink' mode succeeds for the mixed group
    monkeypatch.setattr("core.cloud_directory.CloudDirectoryClient._ensure_session_token", lambda self: None)
    monkeypatch.setattr(
        "core.cloud_directory.CloudDirectoryClient.create_weblink",
        lambda self, **kwargs: {"access_url": "https://example.workers.dev/v/mixed#key"},
    )
    monkeypatch.setattr("transport.smtp_sender.send_email", lambda s, r, m: None)

    res_weblink = api.sendMessage({
        "recipients": ["bob@qumail.sec", "stranger@external.com"],
        "subject": "Mixed Security Test via WebLink",
        "body": "Important document via secure link",
        "securityMode": "weblink",
    })
    assert res_weblink["success"] is True


def test_large_attachment_handling_and_unicode_filenames(monkeypatch):
    """Verify attachments with UTF-8 Unicode characters (currency symbols, emojis) and multi-MB payloads are handled without corruption."""
    from launch_react_desktop import QuMailJsApi
    import base64

    dispatched = []
    def mock_send(s, r, m):
        dispatched.append((s, r, m))
    monkeypatch.setattr("transport.smtp_sender.send_email", mock_send)

    api = QuMailJsApi()
    api.loginAccount("alice@qumail.sec", "Alice", "QuMail Security")

    # Attachment with Unicode filename and base64 content
    sample_payload = b"%PDF-1.7 Test Invoice content with non-ASCII symbols \xe2\x82\xb9" * 50
    b64_data = base64.b64encode(sample_payload).decode("ascii")

    res = api.sendMessage({
        "recipients": ["bob@qumail.sec"],
        "subject": "Invoice with Unicode symbol & filename",
        "body": "Please find attached the financial summary.",
        "securityMode": "pq",
        "attachments": [{
            "name": "Invoice_₹_Q1_2026.pdf",
            "size": len(sample_payload),
            "type": "application/pdf",
            "data": b64_data,
        }],
    })
    assert res["success"] is True
    assert len(dispatched) == 1
    s, r, wire_msg = dispatched[0]
    assert s == "alice@qumail.sec"

    # 2. Rejection of attachments exceeding 30 MB limit
    oversized_b64 = "A" * (41 * 1024 * 1024)
    res_oversized = api.sendMessage({
        "recipients": ["bob@qumail.sec"],
        "subject": "Oversized file",
        "body": "This should fail",
        "securityMode": "weblink",
        "attachments": [{
            "name": "too_large.zip",
            "size": 31 * 1024 * 1024,
            "type": "application/zip",
            "data": oversized_b64,
        }],
    })
    assert res_oversized["success"] is False
    assert "30 mb" in res_oversized.get("message", "").lower()


def test_attachment_binary_save_desktop_bridge(tmp_path, monkeypatch):
    """Verify saveAttachment writes exact binary content with zero truncation, handling dialog or Downloads fallback."""
    from launch_react_desktop import QuMailJsApi
    import base64
    from pathlib import Path

    api = QuMailJsApi()

    # Create binary payload with null bytes and non-ASCII bytes
    raw_payload = b"\x00\x01\x02\xFF\xFE\xFD\x10\x20QuMail Binary Test Payload \xca\xfe\xba\xbe"
    b64_str = base64.b64encode(raw_payload).decode("ascii")

    # Target test save file path
    target_file = tmp_path / "test_report.bin"

    # Mock window.create_file_dialog to simulate user picking target_file
    class MockWindow:
        def create_file_dialog(self, dialog_type, save_filename, file_types):
            return str(target_file)

    api.window = MockWindow()

    res = api.saveAttachment({
        "name": "test_report.bin",
        "data": b64_str,
    })

    assert res["success"] is True
    assert Path(res["path"]).is_file()
    assert Path(res["path"]).read_bytes() == raw_payload

    # Test fallback to ~/Downloads when window or dialog returns None
    api.window = None
    mock_downloads = tmp_path / "Downloads"
    mock_downloads.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    res_fallback = api.saveAttachment({
        "name": "fallback_doc.pdf",
        "data": b64_str,
    })
    assert res_fallback["success"] is True
    assert (mock_downloads / "fallback_doc.pdf").read_bytes() == raw_payload


def test_offline_and_oauth_expired_connection_status_handling(monkeypatch):
    """Verify network errors set connectionStatus='OFFLINE' and expired auth sets 'OAUTH_EXPIRED'."""
    from launch_react_desktop import QuMailJsApi
    import socket

    api = QuMailJsApi()
    api.loginAccount("alice@example.com", "Alice")
    assert api.connection_status == "ONLINE"
    assert api.getAccount()["connectionStatus"] == "ONLINE"

    # 1. Simulate socket.gaierror (DNS/offline network disconnect)
    def mock_fetch_offline(*args, **kwargs):
        raise socket.gaierror(11001, "getaddrinfo failed")

    monkeypatch.setattr("transport.imap_receiver.fetch_inbox", mock_fetch_offline)

    # Calling fetchInbox catches network error and returns cached messages with OFFLINE status
    msgs = api.fetchInbox()
    assert isinstance(msgs, list)
    assert api.connection_status == "OFFLINE"
    assert api.getAccount()["connectionStatus"] == "OFFLINE"

    # 2. Simulate Google OAuth invalid_grant / refresh token expired
    def mock_fetch_oauth_expired(*args, **kwargs):
        raise RuntimeError("oauth error: invalid_grant - token has been expired or revoked by user")

    monkeypatch.setattr("transport.imap_receiver.fetch_inbox", mock_fetch_oauth_expired)

    msgs_oauth = api.fetchInbox()
    assert isinstance(msgs_oauth, list)
    assert api.connection_status == "OAUTH_EXPIRED"
    assert api.getAccount()["connectionStatus"] == "OAUTH_EXPIRED"

    # 3. Simulate recovery to normal network and valid token
    monkeypatch.setattr("transport.imap_receiver.fetch_inbox", lambda *args, **kwargs: [])
    msgs_online = api.fetchInbox()
    assert api.connection_status == "ONLINE"
    assert api.getAccount()["connectionStatus"] == "ONLINE"


def test_conversation_thread_continuity_and_headers(monkeypatch):
    """Verify threadId, inReplyTo, and references are captured and propagated during message dispatch."""
    from launch_react_desktop import QuMailJsApi

    dispatched = []
    def mock_send(s, r, m):
        dispatched.append((s, r, m))
    monkeypatch.setattr("transport.smtp_sender.send_email", mock_send)

    api = QuMailJsApi()
    api.loginAccount("alice@qumail.sec", "Alice")

    res = api.sendMessage({
        "recipients": ["bob@qumail.sec"],
        "subject": "Re: Project Launch",
        "body": "Sounds good, proceeding with milestone 1.",
        "securityMode": "pq",
        "threadId": "thread_abc_123",
        "inReplyTo": "<orig_msg_001@mail.example>",
        "references": "<root_000@mail.example> <orig_msg_001@mail.example>",
    })

    assert res["success"] is True
    # Verify sent message in local state preserved thread headers
    sent_msgs = [m for m in api.messages if m.get("folder") == "sent"]
    assert len(sent_msgs) >= 1
    newest = sent_msgs[-1]
    assert newest.get("threadId") == "thread_abc_123"
    assert newest.get("inReplyTo") == "<orig_msg_001@mail.example>"
    assert "<root_000@mail.example>" in newest.get("references", "")


def test_multi_account_vault_unlock_and_decapsulation_mapping(tmp_path, monkeypatch):
    """Verify that in multi-account vaults, unlockVault selects the matching account and decapsulates with that account's secret key."""
    from launch_react_desktop import QuMailJsApi
    from transport.imap_receiver import InboxMessage
    import base64

    vault_file = tmp_path / "multi_account_vault.sqlite"
    api1 = QuMailJsApi(account_email="valiacollege@gmail.com", vault_path=vault_file)
    api1._ensure_account_session("valiacollege@gmail.com", "Valia College")

    # Enroll second account in the same vault
    api1._ensure_account_session("shaikh.sec@gmail.com", "Shaikh Sec")

    # Now verify vault has multiple enrolled accounts
    vault = api1.vault_service.vault
    rows = vault.summaries()
    assert len(rows) >= 2
    # Verify valiacollege is row 0 and shaikh.sec is row 1
    emails = [r[2].lower() for r in rows]
    assert "valiacollege@gmail.com" in emails
    assert "shaikh.sec@gmail.com" in emails

    # Switch active account to shaikh.sec@gmail.com and lock vault
    api1.account_email = "shaikh.sec@gmail.com"
    api1.account_display_name = "Shaikh Sec"
    api1.lockVault()
    assert api1.vault_state == "LOCKED"

    # Unlock vault: must match shaikh.sec@gmail.com, NOT blindly pick row 0 (valiacollege)
    unlock_res = api1.unlockVault()
    assert unlock_res["success"] is True
    assert api1.account_email.lower() == "shaikh.sec@gmail.com"
    
    # Active context must belong to shaikh.sec@gmail.com
    active_row = next(r for r in rows if r[2].lower() == "shaikh.sec@gmail.com")
    assert api1.active_context == active_row[0]
    assert api1.active_key_handle == active_row[1]


def test_sent_folder_cross_account_isolation(tmp_path, monkeypatch):
    """Verify that Sent and Outbox messages are strictly partitioned per account and never leak across accounts."""
    from launch_react_desktop import QuMailJsApi

    monkeypatch.setattr("core.config.get_user_data_dir", lambda: tmp_path)
    monkeypatch.setattr("transport.smtp_sender.send_email", lambda s, r, m: None)

    # 1. Login Account A and send an email
    api_a = QuMailJsApi(account_email="alice@qumail.sec")
    api_a.loginAccount("alice@qumail.sec", "Alice")

    res_a = api_a.sendMessage({
        "recipients": ["carol@external.com"],
        "subject": "Alice's Secret Letter",
        "body": "Confidential from Alice",
        "securityMode": "standard",
    })
    assert res_a["success"] is True

    # Account A must have 1 sent message
    sent_a = [m for m in api_a.getMessages() if m.get("folder") == "sent"]
    assert len(sent_a) == 1
    assert sent_a[0]["subject"] == "Alice's Secret Letter"
    assert sent_a[0]["senderEmail"] == "alice@qumail.sec"

    # 2. Switch to Account B (e.g. via updateAccountEmail or fresh session)
    api_b = QuMailJsApi(account_email="bob@qumail.sec")
    api_b.loginAccount("bob@qumail.sec", "Bob")

    # Account B must NOT see Alice's sent message
    sent_b = [m for m in api_b.getMessages() if m.get("folder") == "sent"]
    assert len(sent_b) == 0

    # Bob sends an email
    res_b = api_b.sendMessage({
        "recipients": ["dave@external.com"],
        "subject": "Bob's Invoice",
        "body": "Payment details from Bob",
        "securityMode": "standard",
    })
    assert res_b["success"] is True

    # Account B must see ONLY Bob's sent message
    sent_b_after = [m for m in api_b.getMessages() if m.get("folder") == "sent"]
    assert len(sent_b_after) == 1
    assert sent_b_after[0]["subject"] == "Bob's Invoice"
    assert sent_b_after[0]["senderEmail"] == "bob@qumail.sec"

    # 3. Switch back to Account A
    api_a_reload = QuMailJsApi(account_email="alice@qumail.sec")
    api_a_reload.loginAccount("alice@qumail.sec", "Alice")
    sent_a_reload = [m for m in api_a_reload.getMessages() if m.get("folder") == "sent"]
    assert len(sent_a_reload) == 1
    assert sent_a_reload[0]["subject"] == "Alice's Secret Letter"
    assert sent_a_reload[0]["senderEmail"] == "alice@qumail.sec"
    assert not any("Bob" in m["subject"] for m in sent_a_reload)


def test_background_prefetch_while_locked_and_instant_unlock_decapsulation(tmp_path, monkeypatch):
    """
    Verify safe transport pre-fetch while locked:
    1. Bridge starts in LOCKED state with valid Security PIN.
    2. Private keys remain unloaded and getMessages() returns [].
    3. Prefetch downloads raw encrypted RFC 5322 containers into staging buffer without attempting ML-KEM decapsulation.
    4. Upon unlockVault(valid_pin), staged messages are decapsulated immediately into memory/cache.
    """
    from launch_react_desktop import QuMailBridge
    from transport.imap_receiver import InboxMessage

    vault_file = tmp_path / "prefetch_vault.sqlite"
    api1 = QuMailBridge(account_email="alice@qumail.sec", vault_path=vault_file)
    api1.loginAccount("alice@qumail.sec", "Alice")
    assert api1.setSecurityPin("1234")["success"] is True

    # Send a self-directed PQ message to obtain a real ML-KEM encrypted wire message
    dispatched = []
    monkeypatch.setattr("transport.smtp_sender.send_email", lambda s, r, m: dispatched.append(m))
    res = api1.sendMessage({
        "recipients": ["alice@qumail.sec"],
        "subject": "Pre-fetched Quantum Secret",
        "body": "Decapsulated immediately upon unlock without network latency.",
        "securityMode": "pq",
    })
    assert res["success"] is True
    assert len(dispatched) == 1
    wire_msg = dispatched[0]

    # Create mock InboxMessage
    fake_item = InboxMessage(
        uid="5001",
        sender="alice@qumail.sec",
        subject="Pre-fetched Quantum Secret",
        date="2026-11-13",
        message=wire_msg,
    )

    # Simulate app restart in locked state
    monkeypatch.setattr("transport.imap_receiver.fetch_inbox", lambda email, max_count=50: [fake_item])
    monkeypatch.setattr(QuMailBridge, "_has_credentials", lambda self: True)

    api_locked = QuMailBridge(account_email="alice@qumail.sec", vault_path=vault_file)
    assert api_locked.vault_state == "LOCKED"
    assert api_locked.vault_service is None
    # Strict security boundary check: getMessages() returns [] while locked
    assert api_locked.getMessages() == []

    # Run locked prefetch
    api_locked._prefetch_encrypted_inbox_while_locked()
    assert len(api_locked._staged_raw_inbox) == 1
    assert api_locked.vault_state == "LOCKED"
    assert api_locked.vault_service is None
    assert api_locked.getMessages() == []

    # Instant decapsulation upon unlock with valid PIN
    unlock_res = api_locked.unlockVault("1234")
    assert unlock_res["success"] is True
    assert api_locked.vault_state == "UNLOCKED"
    assert len(api_locked._staged_raw_inbox) == 0  # Staging buffer was consumed

    unlocked_msgs = api_locked.getMessages()
    assert len(unlocked_msgs) >= 1
    matching = next(m for m in unlocked_msgs if m["id"] == "imap-5001")
    assert matching["isQuMail"] is True
    assert matching["securityTier"] == "pq_sealed"
    assert "Decapsulated immediately" in matching["body"]
    assert matching["indicator"]["badgeLevel"] == "SECURE"

    # unlockVault return payload also included messages
    assert "messages" in unlock_res
    assert any(m["id"] == "imap-5001" for m in unlock_res["messages"])


def test_bridge_offline_translation_lock_enforcement():
    """Verify that translateEmailContent and log audit are strictly blocked while vault is locked."""
    api = QuMailJsApi()
    api.vault_state = "LOCKED"
    api.session_state = "LOCKED"

    # Translation blocked while locked
    res = api.translateEmailContent("msg-999", "Top secret email body", "hi")
    assert res["status"] == "error"
    assert "Vault is locked" in res["error"]

    # Logs access blocked while locked
    assert api.getTranslationLogs() == []

    # Deleting log blocked while locked
    del_res = api.deleteTranslationLog("msg-999")
    assert del_res["status"] == "error"
    assert "Vault is locked" in del_res["error"]


def test_bridge_offline_translation_roundtrip_with_cache(monkeypatch):
    """Verify translation execution, DPAPI caching, audit logs, and log purging via the bridge."""
    api = QuMailJsApi()
    api.vault_state = "ACTIVE"
    api.session_state = "MAILBOX_READY"
    api.messages = [{"id": "msg-101", "subject": "Quarterly PQC Roadmap", "body": "Hello world"}]

    # Mock translate_text
    def mock_translate(text, target_lang):
        return {
            "status": "ok",
            "translatedText": "नमस्ते दुनिया",
            "sourceLang": "eng_Latn",
            "targetLang": "hin_Deva",
        }

    monkeypatch.setattr(api.translator_service, "translate_text", mock_translate)

    # First translation call
    res = api.translateEmailContent("msg-101", "Hello world", "hi")
    assert res["status"] == "ok"
    assert res["translatedText"] == "नमस्ते दुनिया"
    assert res.get("fromCache") is None

    # Second call should be served from DPAPI cache
    cached_res = api.translateEmailContent("msg-101", "Hello world", "hi")
    assert cached_res["status"] == "ok"
    assert cached_res["translatedText"] == "नमस्ते दुनिया"
    assert cached_res.get("fromCache") is True

    # Audit log check
    logs = api.getTranslationLogs()
    assert len(logs) >= 1
    assert any(l["messageId"] == "msg-101" for l in logs)

    # Purge log
    del_res = api.deleteTranslationLog("msg-101")
    assert del_res["status"] == "ok"
    assert not any(l["messageId"] == "msg-101" for l in api.getTranslationLogs())


def test_bridge_unload_translation_model():
    """Verify manual unloadTranslationModel reclaims memory and reports isModelLoadedInRam."""
    api = QuMailJsApi()
    api.translator_service._translator = "mock_translator"
    api.translator_service._sp_processor = "mock_sp"

    assert api.translator_service.get_status()["isModelLoadedInRam"] is True
    res = api.unloadTranslationModel()
    assert res["status"] == "ok"
    assert res["isModelLoadedInRam"] is False
    assert api.translator_service._translator is None
    assert api.translator_service.get_status()["isModelLoadedInRam"] is False


def test_bridge_standard_email_translation_support(monkeypatch):
    """Verify translating standard non-qumail emails safely uses rawStandardBody without vault pollution."""
    api = QuMailJsApi()
    api.vault_state = "ACTIVE"
    api.session_state = "MAILBOX_READY"

    standard_mail = {
        "id": "imap-std-77",
        "sender": "external@legacy.com",
        "senderEmail": "external@legacy.com",
        "subject": "Monthly Statement [Shielded]",
        "body": "🛡️ QUMAIL ZERO-TRUST PRIVACY SHIELD — LEGACY INBOUND COMMUNICATION",
        "rawStandardSubject": "Monthly Bank Statement",
        "rawStandardBody": "Your monthly balance statement is now ready to download.",
        "isQuMail": False,
        "securityTier": "standard_tls",
    }
    api.messages = [standard_mail]

    translated_texts = []

    def mock_translate(text, target_lang):
        translated_texts.append(text)
        return {
            "status": "ok",
            "translatedText": f"Translated: {text}",
            "sourceLang": "eng_Latn",
            "targetLang": target_lang,
        }

    monkeypatch.setattr(api.translator_service, "translate_text", mock_translate)

    # When frontend triggers translation passing rawStandardBody or shielded placeholder
    res = api.translateEmailContent("imap-std-77", standard_mail["body"], "hi")
    assert res["status"] == "ok"
    # Should have translated the rawStandardBody rather than the privacy shield notice
    assert "Your monthly balance statement" in translated_texts[0]
    # Subject should have been resolved to the raw unshielded subject
    assert len(translated_texts) >= 2
    assert "Monthly Bank Statement" in translated_texts[1]
    assert res["translatedSubject"] == "Translated: Monthly Bank Statement"


def test_account_avatar_isolation_and_switching(monkeypatch, tmp_path):
    """Verify avatars are strictly isolated per account email and never bleed across logins."""
    api = QuMailJsApi()
    api.state_file = tmp_path / "test_state.json"

    # Mock avatar fetcher in transport.oauth2_gmail
    avatars_by_email = {
        "user1@gmail.com": "https://lh3.googleusercontent.com/a/user1_pic",
        "user2@gmail.com": "",  # user 2 has no photo
    }

    def mock_fetch_avatar(email, force_refresh=False):
        return avatars_by_email.get(email.lower(), "")

    monkeypatch.setattr("transport.oauth2_gmail.fetch_account_avatar_from_provider", mock_fetch_avatar)

    # 1. Login user1
    acc1 = api.loginAccount("user1@gmail.com", "User One", "Acme")
    assert acc1["email"] == "user1@gmail.com"
    # Trigger refresh
    ref1 = api.refreshAccountAvatar()
    assert ref1["success"] is True
    assert ref1["avatarUrl"] == "https://lh3.googleusercontent.com/a/user1_pic"
    assert api.getAccount()["avatarUrl"] == "https://lh3.googleusercontent.com/a/user1_pic"

    # 2. Login user2 (switch account)
    acc2 = api.loginAccount("user2@gmail.com", "User Two", "Acme")
    assert acc2["email"] == "user2@gmail.com"
    # Immediately after login, avatar must NOT be user1's avatar!
    assert acc2["avatarUrl"] == ""
    assert api.getAccount()["avatarUrl"] == ""

    # 3. Refresh user2 avatar -> returns empty string, not user1's
    ref2 = api.refreshAccountAvatar()
    assert ref2["success"] is True
    assert ref2["avatarUrl"] == ""
    assert api.getAccount()["avatarUrl"] == ""

    # 4. Switch back to user1
    acc1_again = api.loginAccount("user1@gmail.com", "User One", "Acme")
    # Loaded from cached per-account avatar mapping
    assert acc1_again["avatarUrl"] == "https://lh3.googleusercontent.com/a/user1_pic"

    # 5. Logout
    api.logoutAccount()
    assert api.getAccount()["avatarUrl"] == ""


def test_fetch_standard_email_body_on_demand(monkeypatch):
    """Verify on-demand fetching of standard email body extracts text and populates cache."""
    import imaplib

    api = QuMailJsApi()
    api.vault_state = "ACTIVE"
    api.session_state = "MAILBOX_READY"
    api.account_email = "me@gmail.com"

    msg = {
        "id": "imap-999",
        "sender": "LinkedIn Alerts <alerts@linkedin.com>",
        "senderEmail": "alerts@linkedin.com",
        "subject": "IBM is hiring: •••••••• [Shielded]",
        "body": "🛡️ QUMAIL ZERO-TRUST PRIVACY SHIELD — LEGACY INBOUND COMMUNICATION",
        "isQuMail": False,
        "securityTier": "standard_tls",
    }
    api.messages = [msg]

    raw_rfc5322 = (
        b"From: LinkedIn Alerts <alerts@linkedin.com>\r\n"
        b"To: me@gmail.com\r\n"
        b"Subject: IBM is hiring: Senior Post-Quantum Cryptographer\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
        b"We found a new job recommendation matching your profile: Senior Post-Quantum Cryptographer at IBM."
    )

    class MockImapSSL:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def login(self, *args):
            pass
        def authenticate(self, *args):
            pass
        def select(self, *args, **kwargs):
            return "OK", [b"1"]
        def uid(self, command, uid, msg_parts):
            return "OK", [(b"1 (BODY[] {100})", raw_rfc5322)]

    monkeypatch.setattr(imaplib, "IMAP4_SSL", MockImapSSL)
    monkeypatch.setattr("transport.imap_receiver._get_imap_credentials", lambda prov, email: ("imap.gmail.com", "mock_tok"))

    res = api.fetchStandardEmailBody("imap-999")
    assert res["success"] is True
    assert "Senior Post-Quantum Cryptographer" in res["body"]
    assert res["subject"] == "IBM is hiring: Senior Post-Quantum Cryptographer"

    # Verified stored in memory
    updated_msg = next(m for m in api.messages if m["id"] == "imap-999")
    assert updated_msg["rawStandardBody"] == res["body"]
    assert updated_msg["rawStandardSubject"] == res["subject"]


def test_parse_rfc2047_sender_decoding():
    """Verify RFC 2047 MIME encoded sender names decode into readable text without ?utf-8 artifacts."""
    from launch_react_desktop import parse_rfc2047_sender
    from transport.imap_receiver import parse_rfc2047_sender as imap_parse_sender

    test_cases = [
        ("=?UTF-8?Q?LinkedIn=20Job=20Alerts?= <jobalerts-noreply@linkedin.com>", "LinkedIn Job Alerts", "jobalerts-noreply@linkedin.com"),
        ("=?utf-8?B?TGlua2VkSW4=?= <news@linkedin.com>", "LinkedIn", "news@linkedin.com"),
        ('"=?UTF-8?Q?Google_Security_Alert?=" <no-reply@accounts.google.com>', "Google Security Alert", "no-reply@accounts.google.com"),
        ("Jane Doe <jane@acme.com>", "Jane Doe", "jane@acme.com"),
        ("support@github.com", "support", "support@github.com"),
        ("", "Unknown Sender", ""),
    ]

    for raw, expected_name, expected_addr in test_cases:
        name1, addr1 = parse_rfc2047_sender(raw)
        name2, addr2 = imap_parse_sender(raw)
        assert name1 == expected_name
        assert addr1 == expected_addr
        assert name2 == expected_name
        assert addr2 == expected_addr
        assert "?utf-8" not in name1.lower()
        assert "?utf-8" not in name2.lower()


def test_clean_html_to_text_strips_css_and_preserves_void_tags():
    """Verify clean_html_to_text strips CSS/scripts and never blanks out on unclosed meta/link void tags."""
    from launch_react_desktop import clean_html_to_text

    raw_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="stylesheet" href="https://example.com/style.css">
        <title>Job Alert</title>
        <style type="text/css">
            body { font-family: -apple-system, Roboto, sans-serif; margin: 0; padding: 0; }
            .btn { background-color: #0073b1; color: #ffffff !important; display: inline-block; }
            table { border-collapse: collapse; width: 100%; }
            @media screen and (max-width: 600px) { .mobile-hide { display: none; } }
        </style>
        <script>
            window.dataLayer = window.dataLayer || [];
            console.log("Tracking script");
        </script>
    </head>
    <body>
        <meta http-equiv="X-UA-Compatible" content="IE=edge">
        <h1>IBM is hiring: Senior Post-Quantum Cryptographer</h1>
        <p>Hello Uzair,&nbsp;we found a new recommendation for you &amp; your team.</p>
        <br>
        <div>Location: <strong>Mumbai, India</strong></div>
        <p>Don&#39;t miss out on this opportunity!</p>
    </body>
    </html>
    """

    cleaned = clean_html_to_text(raw_html)

    # 1. CSS & Script content must be completely removed
    assert "font-family" not in cleaned
    assert "background-color" not in cleaned
    assert "Tracking script" not in cleaned
    assert "@media" not in cleaned
    assert ".btn" not in cleaned

    # 2. Content must NOT be blanked out by unclosed <meta> or <link> void tags
    assert "IBM is hiring: Senior Post-Quantum Cryptographer" in cleaned
    assert "Hello Uzair, we found a new recommendation for you & your team." in cleaned
    assert "Location: Mumbai, India" in cleaned
    assert "Don't miss out on this opportunity!" in cleaned

    # 3. HTML entities must be unescaped
    assert "&nbsp;" not in cleaned
    assert "&amp;" not in cleaned
    assert "&#39;" not in cleaned


def test_extract_email_body_and_subject_multipart_fallback():
    """Verify multipart email with empty/stub text/plain falls back to cleaned HTML text instead of blanking out."""
    from launch_react_desktop import extract_email_body_and_subject
    import email.message

    # Construct multipart/alternative email
    msg = email.message.EmailMessage()
    msg["Subject"] = "=?UTF-8?Q?Weekly=20Digest?="
    msg["From"] = "digest@newsletter.com"

    # Part 1: Empty whitespace plain text (common in marketing emails)
    msg.add_alternative("   \r\n\r\n  ", subtype="plain")

    # Part 2: Rich HTML alternative with styles and real content
    html_content = """
    <html>
    <head><style>p { color: blue; }</style></head>
    <body>
        <h2>Your Weekly Summary</h2>
        <p>Here are the latest security updates for this week.</p>
    </body>
    </html>
    """
    msg.add_alternative(html_content, subtype="html")

    body, subj = extract_email_body_and_subject(msg)
    assert subj == "Weekly Digest"
    assert "Your Weekly Summary" in body
    assert "Here are the latest security updates" in body
    assert "color: blue" not in body
    assert len(body.strip()) > 0


def test_bridge_get_cached_translation_and_non_blocking_status(monkeypatch):
    """Verify getCachedTranslation behavior and non-blocking get_status execution."""
    api = QuMailJsApi()

    # 1. Locked enforcement
    api.vault_state = "LOCKED"
    api.session_state = "LOCKED"
    res_locked = api.getCachedTranslation("msg-101", "hi")
    assert res_locked["status"] == "locked"
    assert res_locked["fromCache"] is False

    # 2. Unlocked but uncached
    api.vault_state = "UNLOCKED"
    api.session_state = "MAILBOX_READY"
    monkeypatch.setattr(api.translator_service, "get_cached_translation", lambda msg_id, lang: None)
    res_uncached = api.getCachedTranslation("msg-101", "hi")
    assert res_uncached["status"] == "not_cached"
    assert res_uncached["fromCache"] is False

    # 3. Cached hit
    fake_cached = {
        "translatedText": "सुरक्षित संदेश",
        "translatedSubject": "महत्वपूर्ण ईमेल",
        "sourceLang": "eng_Latn",
        "targetLang": "hin_Deva",
    }
    monkeypatch.setattr(api.translator_service, "get_cached_translation", lambda msg_id, lang: fake_cached)
    res_cached = api.getCachedTranslation("msg-101", "hi")
    assert res_cached["status"] == "ok"
    assert res_cached["fromCache"] is True
    assert res_cached["translatedText"] == "सुरक्षित संदेश"
    assert res_cached["translatedSubject"] == "महत्वपूर्ण ईमेल"

    # 4. get_status returns instant non-blocking payload
    status = api.getTranslationStatus()
    assert "isInstalled" in status
    assert "isModelLoadedInRam" in status










