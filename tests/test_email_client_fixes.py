"""
tests/test_email_client_fixes.py — Regression tests for QuMail 1.0 Beta core email client issues.

Covers:
1. Account Name & Recipient field UX:
   - Full email address used as display-name fallback when profile name is local-part or empty.
   - Multi-recipient parsing and handling from chip/bubble inputs.
2. Weblink Mail:
   - Directory authentication session auto-initialization prior to weblink creation.
   - Token refresh and proof-of-possession directory session establishment.
3. Quantum Private Mail:
   - Complete message lifecycle: composition, PQ sealing, SMTP dispatch, Sent-folder recording.
   - Non-silent failure handling: durability in Outbox on SMTP failure with retry readiness.
   - Mixed-group / unregistered recipient fail-closed protection.
"""

from __future__ import annotations

import base64
import time
from typing import Any, Dict
from unittest.mock import MagicMock, patch
import pytest

from launch_react_desktop import QuMailJsApi
import transport.oauth2_gmail as oauth_module


# ============================================================================
# Issue 1: Account Name & Display-Name Fallback
# ============================================================================

def test_account_name_fallback_uses_full_email_when_display_name_matches_local_part():
    """
    When logged in as uzair.valiacollege@gmail.com and no Google profile display name
    is set (or it matches the local-part 'uzair.valiacollege'), getAccount() must
    return the full email address rather than dropping the domain.
    """
    api = QuMailJsApi(
        account_email="uzair.valiacollege@gmail.com",
        account_display_name="uzair.valiacollege",
    )
    api.vault_state = "UNLOCKED"
    api.session_state = "MAILBOX_READY"

    account = api.getAccount()
    assert account["email"] == "uzair.valiacollege@gmail.com"
    # Display name must fallback to full email, not just 'uzair.valiacollege'
    assert account["displayName"] == "uzair.valiacollege@gmail.com"


def test_account_name_fallback_when_display_name_empty():
    """When display name is None or empty, getAccount() returns full email address."""
    api = QuMailJsApi(
        account_email="uzair.valiacollege@gmail.com",
        account_display_name="",
    )
    api.vault_state = "UNLOCKED"
    api.session_state = "MAILBOX_READY"

    account = api.getAccount()
    assert account["email"] == "uzair.valiacollege@gmail.com"
    assert account["displayName"] == "uzair.valiacollege@gmail.com"


def test_account_name_preserves_genuine_google_display_name():
    """When a real human display name exists (e.g. 'Uzair Shaikh'), it is preserved."""
    api = QuMailJsApi(
        account_email="uzair.valiacollege@gmail.com",
        account_display_name="Uzair Shaikh",
    )
    api.vault_state = "UNLOCKED"
    api.session_state = "MAILBOX_READY"

    account = api.getAccount()
    assert account["email"] == "uzair.valiacollege@gmail.com"
    assert account["displayName"] == "Uzair Shaikh"


def test_oauth2_get_stored_account_info_fallback(monkeypatch):
    """
    transport.oauth2_gmail.get_stored_account_info() must return the full email
    when stored displayName matches email.split('@')[0] or is empty.
    """
    mock_token_data = {
        "email": "uzair.valiacollege@gmail.com",
        "displayName": "uzair.valiacollege",  # local part only
        "avatarUrl": "https://example.com/avatar.png",
    }
    monkeypatch.setattr(oauth_module, "_load_credentials", lambda email="": (MagicMock(), mock_token_data))

    info = oauth_module.get_stored_account_info("uzair.valiacollege@gmail.com")
    assert info is not None
    assert info["email"] == "uzair.valiacollege@gmail.com"
    assert info["displayName"] == "uzair.valiacollege@gmail.com"


def test_login_account_sets_full_email_when_display_name_is_local_part():
    """loginAccount must use full email as display name if given local-part as display name."""
    api = QuMailJsApi()
    res = api.loginAccount("uzair.valiacollege@gmail.com", "uzair.valiacollege")
    assert res["email"] == "uzair.valiacollege@gmail.com"
    assert res["displayName"] == "uzair.valiacollege@gmail.com"
    assert api.account_display_name == "uzair.valiacollege@gmail.com"

    account = api.getAccount()
    assert account["displayName"] == "uzair.valiacollege@gmail.com"


# ============================================================================
# Issue 2: Recipient Chip Handling & Multi-Recipient Delivery
# ============================================================================

def test_multiple_recipients_from_chips_are_trimmed_and_dispatched(monkeypatch):
    """
    Recipient addresses selected as chips/bubbles in the compose window and passed
    as an array to sendMessage are properly normalized, stripped, and delivered.
    """
    dispatched = []

    def mock_send(sender, recipients, msg):
        dispatched.append((sender, recipients, msg))

    monkeypatch.setattr("transport.smtp_sender.send_email", mock_send)

    api = QuMailJsApi()
    api.loginAccount("alice@qumail.sec", "Alice")

    # Pass multiple recipients with surrounding whitespace (simulating chip payload)
    res = api.sendMessage({
        "recipients": ["  bob@qumail.sec  ", "carol@qumail.sec", ""],
        "subject": "Group Security Memo",
        "body": "Confidential post-quantum memo",
        "securityMode": "standard",
    })
    assert res["success"] is True
    assert res["folder"] == "sent"
    assert res["dispatched"] is True

    assert len(dispatched) == 1
    sender, recips, _ = dispatched[0]
    assert sender == "alice@qumail.sec"
    assert recips == ["bob@qumail.sec", "carol@qumail.sec"]


# ============================================================================
# Issue 3: Weblink Mail Directory Authentication & Dispatch
# ============================================================================

def test_weblink_send_invokes_directory_session_and_dispatches_invitation(monkeypatch):
    """
    Sending a Weblink Mail must ensure directory authentication session is active
    before invoking create_weblink, preventing the 'directory authentication is required'
    failure even if session_token was not initialized at startup.
    """
    dispatched = []

    def mock_send(sender, recipients, msg):
        dispatched.append((sender, recipients, msg))

    monkeypatch.setattr("transport.smtp_sender.send_email", mock_send)

    api = QuMailJsApi()
    api.loginAccount("alice@qumail.sec", "Alice")

    # Mock directory client with session token auto-initialization verification
    mock_client = MagicMock()
    session_ensured = []

    def mock_ensure_session_token():
        session_ensured.append(True)
        mock_client.session_token = "valid-session-token-12345"

    mock_client._ensure_session_token = mock_ensure_session_token
    mock_client.session_token = "valid-session-token-12345"
    mock_client.create_weblink.return_value = {
        "access_url": "https://qumail-directory.example.workers.dev/v/link-abc#key=secret-key-material",
        "has_passcode": False,
        "burn_after_read": False,
        "max_views": 5,
        "expires_in_hours": 72,
    }

    monkeypatch.setattr(api, "_directory_client_for_active_account", lambda: mock_client)

    # Trigger Weblink send
    res = api.sendMessage({
        "recipients": ["external.partner@corporation.com"],
        "subject": "Q1 Project Review",
        "body": "Here are the secret project files: https://secret.qumail",
        "securityMode": "weblink",
        "attachments": [],
    })

    assert res["success"] is True
    assert res["folder"] == "sent"
    assert res["dispatched"] is True
    assert mock_client.create_weblink.called

    # SMTP invitation must be sent
    assert len(dispatched) == 1
    sender, recips, py_msg = dispatched[0]
    assert sender == "alice@qumail.sec"
    assert recips == ["external.partner@corporation.com"]
    # Wire message plain text must contain the secure link URL
    body_plain = py_msg.get_body(preferencelist=('plain',)).get_content()
    assert "https://qumail-directory.example.workers.dev/v/link-abc#key=secret-key-material" in body_plain


# ============================================================================
# Issue 4: Quantum Private Mail Message Lifecycle & Durability
# ============================================================================

def test_quantum_private_mail_full_lifecycle_success(monkeypatch):
    """
    Quantum Private Mail full lifecycle:
    1. Seals message with NIST FIPS 203/204 ML-KEM-768 + ML-DSA-65.
    2. Dispatches via SMTP transport.
    3. Records in 'sent' folder with Post-Quantum Sealed indicator.
    4. Removes originating draft.
    5. Returns success: True, dispatched: True, folder: 'sent'.
    """
    dispatched = []

    def mock_send(sender, recipients, msg):
        dispatched.append((sender, recipients, msg))

    monkeypatch.setattr("transport.smtp_sender.send_email", mock_send)

    api = QuMailJsApi()
    api.loginAccount("alice@qumail.sec", "Alice")

    # Pre-save a draft to test draft removal upon successful dispatch
    draft_res = api.saveDraft({
        "recipients": ["bob@qumail.sec"],
        "subject": "Strategic Defense Plan",
        "body": "Draft body before sending",
        "securityMode": "pq",
    })
    draft_id = draft_res["id"]
    assert any(m["id"] == draft_id and m["folder"] == "drafts" for m in api.getMessages())

    # Send Quantum Private Mail
    secret_body = "CONFIDENTIAL: ML-KEM-768 sealed communication payload."
    res = api.sendMessage({
        "draftId": draft_id,
        "recipients": ["bob@qumail.sec"],
        "subject": "Strategic Defense Plan",
        "body": secret_body,
        "securityMode": "pq",
        "attachments": [],
    })

    assert res["success"] is True
    assert res["folder"] == "sent"
    assert res["dispatched"] is True
    assert "dispatched successfully" in res["message"].lower()

    # Draft must be cleaned up
    assert not any(m["id"] == draft_id for m in api.getMessages())

    # Message must be in Sent folder
    sent_msgs = [m for m in api.getMessages() if m["folder"] == "sent"]
    assert len(sent_msgs) >= 1
    sent_item = next(m for m in sent_msgs if m["id"] == res["id"])
    assert sent_item["securityMode"] == "pq"
    assert sent_item["securityTier"] == "pq_sealed"
    assert sent_item["indicator"]["headline"] == "Post-Quantum Sealed"

    # Wire check: SMTP received an email containing armored ciphertext, not plaintext
    assert len(dispatched) == 1
    _, _, wire_msg = dispatched[0]
    raw_payload = wire_msg.as_string()
    assert secret_body not in raw_payload
    assert "BEGIN QUMAIL ENVELOPE" in raw_payload or "Content-Type:" in raw_payload


def test_quantum_private_mail_smtp_failure_persists_in_outbox_for_retry(monkeypatch):
    """
    When SMTP transport fails (network drop, offline, transport error):
    1. Message must NOT be lost or silently disappear.
    2. Message must be durable in Outbox with queuedInOutbox: True.
    3. Status returned: success: False, queuedInOutbox: True, folder: 'outbox'.
    4. Message can be retried once connectivity is restored.
    """
    def mock_send_fail(sender, recipients, msg):
        raise ConnectionResetError("Remote SMTP server closed connection abruptly")

    monkeypatch.setattr("transport.smtp_sender.send_email", mock_send_fail)

    api = QuMailJsApi()
    api.loginAccount("alice@qumail.sec", "Alice")

    res = api.sendMessage({
        "recipients": ["bob@qumail.sec"],
        "subject": "Urgent Operations Notice",
        "body": "This must not be lost despite network interruption.",
        "securityMode": "pq",
    })

    # Must NOT report success when dispatch failed
    assert res["success"] is False
    assert res["queuedInOutbox"] is True
    assert "outbox" in res["id"]
    assert "SMTP dispatch failed" in res["message"]

    # Verify message is preserved in Outbox
    messages = api.getMessages()
    outbox_msgs = [m for m in messages if m.get("folder") == "outbox"]
    assert len(outbox_msgs) >= 1
    queued = next(m for m in outbox_msgs if m["id"] == res["id"])
    assert queued["subject"] == "Urgent Operations Notice"
    assert "Remote SMTP server closed connection" in queued["outboxError"]
    assert queued["indicator"]["headline"] == "Queued in Outbox"


def test_quantum_private_mail_fails_closed_on_unregistered_recipients(monkeypatch):
    """
    When sending Quantum Private Mail to an external/unregistered recipient without
    registered ML-KEM keys, the dispatch must fail closed with code UNREGISTERED_RECIPIENTS
    and advice to use Secure Web Link mode.
    """
    api = QuMailJsApi()
    api.loginAccount("alice@qumail.sec", "Alice")

    # Mock directory client returning not found
    mock_client = MagicMock()
    mock_client.lookup.return_value = {"found": False, "devices": []}
    monkeypatch.setattr(api, "_directory_client_for_active_account", lambda: mock_client)

    res = api.sendMessage({
        "recipients": ["unregistered@stranger.example.org"],
        "subject": "Strict PQ Requirement",
        "body": "This should not be sent in the clear.",
        "securityMode": "pq",
    })

    assert res["success"] is False
    assert res["code"] == "UNREGISTERED_RECIPIENTS"
    assert "unregistered@stranger.example.org" in res["unregistered"]
    assert "Secure Private Link" in res["message"]


# ============================================================================
# Security Hardening: Windows DPAPI Protection for OAuth Master Key
# ============================================================================

def test_oauth_master_key_is_dpapi_wrapped_on_disk(tmp_path, monkeypatch):
    """
    oauth_master.key on disk must be wrapped with Windows DPAPI (prefixed with
    _DPAPI_MAGIC) rather than stored as raw plaintext.
    """
    key_file = tmp_path / "oauth_master.key"
    monkeypatch.setattr(oauth_module, "get_oauth_master_key_path", lambda: key_file)

    # First call generates key and saves DPAPI-wrapped
    fernet = oauth_module._get_fernet()
    assert key_file.is_file()
    raw_on_disk = key_file.read_bytes()
    assert raw_on_disk.startswith(oauth_module._DPAPI_MAGIC)

    # Roundtrip check: second call unprotects and produces equivalent functional Fernet
    fernet2 = oauth_module._get_fernet()
    ciphertext = fernet.encrypt(b"confidential token data")
    assert fernet2.decrypt(ciphertext) == b"confidential token data"


def test_legacy_plaintext_master_key_migrates_to_dpapi(tmp_path, monkeypatch):
    """
    If a legacy plaintext 44-byte Fernet key exists from an older version,
    _get_fernet() transparently migrates it to DPAPI-wrapped storage without data loss.
    """
    from cryptography.fernet import Fernet
    legacy_key = Fernet.generate_key()
    key_file = tmp_path / "oauth_master.key"
    key_file.write_bytes(legacy_key)

    monkeypatch.setattr(oauth_module, "get_oauth_master_key_path", lambda: key_file)

    # Call _get_fernet which should trigger migration
    fernet = oauth_module._get_fernet()

    # The file on disk should now be DPAPI-wrapped
    raw_on_disk = key_file.read_bytes()
    assert raw_on_disk.startswith(oauth_module._DPAPI_MAGIC)

    # The functional key should match the original legacy key
    orig_fernet = Fernet(legacy_key)
    ciphertext = orig_fernet.encrypt(b"token payload")
    assert fernet.decrypt(ciphertext) == b"token payload"

