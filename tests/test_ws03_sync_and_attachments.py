"""
Tests for QuMail M7 — Module 1.6 WS-03:
Event-Driven Mailbox Synchronization, Background Inbox & Practical Attachment Pipeline.

Covers:
- WS-03A: Background synchronization engine lifecycle, IMAP IDLE, periodic refresh,
          fallback polling, reconnection with backoff/jitter, cancellation, shutdown.
- WS-03B: Persistent synchronization cursor, UIDVALIDITY change/reset, UIDNEXT,
          expunge reconciliation, race condition handling, idempotency, crash rollback.
- WS-03C: Metadata-first encrypted mailbox index, vault storage, schema migration from M6,
          non-mutating BODY.PEEK[], on-demand body retrieval without setting \\Seen.
- WS-03D: Authoritative unread counts, total counts, new-message events, privacy in notifications.
- WS-03E: Practical attachment pipeline, measured 15–25 MiB limits, streaming MIME parsing,
          filename sanitization, path traversal defense, encrypted disk cache, atomic export,
          and protection against decompression/expansion attacks.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
from email.message import EmailMessage
from email.utils import formatdate
import hashlib
import os
from pathlib import Path
import re
import secrets
import tempfile
import threading
import time
from typing import Any
import unittest.mock

import pytest

from core.mailbox_cursor import MailboxCursor
from core.mailbox_index import MailboxIndex, IndexedMessage, sanitize_snippet
from core.attachment_pipeline import (
    AttachmentPipeline,
    EncryptedAttachmentCache,
    ProcessedAttachment,
    ParsedMessageContent,
    sanitize_attachment_filename,
    validate_export_destination,
    safe_decode_transfer_encoding,
    MAX_WIRE_SIZE,
    MAX_BODY_SIZE,
    MAX_INDIVIDUAL_ATTACHMENT_SIZE,
    MAX_AGGREGATE_ATTACHMENT_SIZE,
    MAX_ATTACHMENT_COUNT,
    MAX_MIME_DEPTH,
    MAX_MIME_PARTS,
    MAX_HEADER_SIZE,
    ResourceLimitExceededError,
    MalformedMIMEError,
    PathTraversalSecurityError,
)
from core.mailbox_sync import (
    SyncState,
    SyncStats,
    IdleCapableIMAPClient,
    MailboxSyncEngine,
)


# =============================================================================
# In-Memory Deterministic Test Fixtures (Zero Real Network)
# =============================================================================

class MockVault:
    """In-memory encrypted vault mock for unit testing cursor and index persistence."""

    def __init__(self, initial_data: dict[str, Any] | None = None) -> None:
        self.data: dict[str, Any] = initial_data or {}
        self.commit_history: list[dict[str, Any]] = []
        self.should_fail_commit: bool = False

    def get_account_context(self, account_id: str) -> str:
        return account_id

    def _read(self, ctx: Any) -> dict[str, Any]:
        import copy
        return copy.deepcopy(self.data)

    @contextmanager
    def transaction(self, ctx: Any):
        import copy
        snapshot = copy.deepcopy(self.data)
        try:
            yield snapshot
            if self.should_fail_commit:
                raise RuntimeError("Simulated vault disk/commit failure during transaction.")
            self.data = snapshot
            self.commit_history.append(copy.deepcopy(snapshot))
        except Exception:
            raise


class MockIdleClient(IdleCapableIMAPClient):
    """
    Deterministic in-memory IMAP IDLE client protocol mock.

    Simulates server conversations entirely in memory without touching OS network sockets,
    complying with QuMail's strict zero-network test contracts and sandbox isolation.
    """

    def __init__(
        self,
        host: str = "mock.imap.gmail.com",
        port: int = 993,
        use_ssl: bool = True,
        timeout: float = 5.0,
        supports_idle: bool = True,
        uidvalidity: int = 123456,
        uidnext: int = 10,
        initial_uids: list[int] | None = None,
        auth_should_succeed: bool = True,
    ) -> None:
        super().__init__(host, port, use_ssl, timeout)
        self.supports_idle_flag = supports_idle
        self.uidvalidity_val = uidvalidity
        self.uidnext_val = uidnext
        self.uids = sorted(initial_uids if initial_uids is not None else [1, 2, 3])
        self.auth_should_succeed = auth_should_succeed
        self.connected = False
        self.is_idling = False
        self.command_log: list[str] = []
        self.messages: dict[int, dict[str, Any]] = {}
        self.flags_map: dict[int, list[str]] = {u: [] for u in self.uids}
        self.drop_connection_on_next_op: bool = False
        self.idle_event = threading.Event()
        self.idle_terminated_event = threading.Event()
        self.unsolicited_notifications: list[bytes] = []

        # Seed initial messages
        for uid in self.uids:
            self._seed_message(uid, f"Test Message {uid}", f"Sender {uid} <sender{uid}@example.com>")

    def _seed_message(
        self,
        uid: int,
        subject: str,
        sender: str,
        is_seen: bool = False,
        attachments: list[tuple[str, bytes]] | None = None,
    ) -> None:
        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = "recipient@example.com"
        msg["Subject"] = subject
        msg["Date"] = formatdate()
        msg["Message-ID"] = f"<msg-{uid}@example.com>"
        msg.set_content(f"Body text for message {uid}.")
        if attachments:
            for fname, content in attachments:
                msg.add_attachment(content, maintype="application", subtype="octet-stream", filename=fname)
        raw = msg.as_bytes()
        raw_headers = raw.split(b"\r\n\r\n")[0] + b"\r\n\r\n"
        self.messages[uid] = {
            "subject": subject,
            "sender": sender,
            "raw": raw,
            "raw_headers": raw_headers,
            "size": len(raw),
        }
        if is_seen:
            self.flags_map[uid] = [r"\Seen"]
        elif uid not in self.flags_map:
            self.flags_map[uid] = []

    def connect(self) -> None:
        if self.drop_connection_on_next_op:
            raise ConnectionError("Simulated connection error on connect")
        self.connected = True
        self.command_log.append("CONNECT")
        self._capabilities = {"IMAP4REV1", "IDLE"} if self.supports_idle_flag else {"IMAP4REV1"}

    def close(self) -> None:
        self.connected = False
        self.is_idling = False
        self.command_log.append("CLOSE")

    def update_capabilities(self) -> set[str]:
        self.command_log.append("CAPABILITY")
        self._capabilities = {"IMAP4REV1", "IDLE"} if self.supports_idle_flag else {"IMAP4REV1"}
        return self._capabilities

    def supports_idle(self) -> bool:
        return self.supports_idle_flag

    def authenticate_xoauth2(self, email_address: str, access_token: str) -> bool:
        self.command_log.append(f"AUTHENTICATE XOAUTH2 user={email_address}")
        return self.auth_should_succeed

    def authenticate_plain(self, username: str, password: str) -> bool:
        self.command_log.append(f"LOGIN user={username}")
        return self.auth_should_succeed

    def select_readonly(self, mailbox: str = "INBOX") -> int:
        if self.drop_connection_on_next_op:
            raise ConnectionError("Simulated connection drop on select")
        self.command_log.append(f'EXAMINE "{mailbox}"')
        self._selected_mailbox = mailbox
        return self.uidvalidity_val

    def get_uidnext(self) -> int:
        self.command_log.append("STATUS UIDNEXT")
        return self.uidnext_val

    def search_all_uids(self) -> set[int]:
        if self.drop_connection_on_next_op:
            raise ConnectionError("Simulated connection drop on search")
        self.command_log.append("UID SEARCH ALL")
        return set(self.uids)

    def fetch_headers_peek(self, uids: list[int]) -> list[tuple[int, list[str], int, bytes]]:
        if self.drop_connection_on_next_op:
            raise ConnectionError("Simulated connection drop on fetch")
        uid_query = ",".join(str(u) for u in sorted(uids))
        self.command_log.append(f"UID FETCH {uid_query} BODY.PEEK[HEADER.FIELDS...]")
        res = []
        for u in uids:
            if u in self.messages:
                res.append((u, list(self.flags_map.get(u, [])), self.messages[u]["size"], self.messages[u]["raw_headers"]))
        return res

    def fetch_body_peek(self, uid: int) -> bytes:
        self.command_log.append(f"UID FETCH {uid} BODY.PEEK[]")
        if uid in self.messages:
            return self.messages[uid]["raw"]
        raise ValueError(f"No message body found for UID {uid}")

    def start_idle(self) -> None:
        if not self.supports_idle_flag:
            raise RuntimeError("Server does not support IMAP IDLE.")
        self.command_log.append("IDLE")
        self.is_idling = True
        self.idle_event.set()

    def wait_for_idle_notification(self, timeout_seconds: float) -> list[bytes]:
        if self.drop_connection_on_next_op:
            raise ConnectionError("Simulated socket drop during IDLE")
        if self.unsolicited_notifications:
            notifs = list(self.unsolicited_notifications)
            self.unsolicited_notifications.clear()
            return notifs

        # Sleep in small slices checking for notifications
        end_time = time.time() + timeout_seconds
        while time.time() < end_time and not self.unsolicited_notifications:
            time.sleep(0.02)

        if self.unsolicited_notifications:
            notifs = list(self.unsolicited_notifications)
            self.unsolicited_notifications.clear()
            return notifs
        return []

    def stop_idle(self) -> None:
        self.command_log.append("DONE")
        self.is_idling = False
        self.idle_terminated_event.set()


# =============================================================================
# 1. Synchronization Cursor & State Management Tests (WS-03B)
# =============================================================================

def test_cursor_initial_adoption_and_record_synced():
    cursor = MailboxCursor(account_id="acc-01", mailbox="INBOX")
    assert cursor.uidvalidity == 0
    assert cursor.check_uidvalidity(998877) is True
    assert cursor.uidvalidity == 998877

    cursor.record_synced([10, 11, 12], new_uidnext=15)
    assert cursor.synced_uids == {10, 11, 12}
    assert cursor.last_sync_uid == 12
    assert cursor.uidnext == 15
    assert cursor.last_sync_time > 0


def test_cursor_uidvalidity_preservation_and_reset():
    cursor = MailboxCursor(account_id="acc-01", mailbox="INBOX", uidvalidity=5555)
    cursor.record_synced([1, 2, 3], new_uidnext=5)

    # Same UIDVALIDITY evaluates True
    assert cursor.check_uidvalidity(5555) is True
    assert cursor.synced_uids == {1, 2, 3}

    # Changed UIDVALIDITY evaluates False and triggers reset
    assert cursor.check_uidvalidity(6666) is False
    assert cursor.uidvalidity == 6666
    assert cursor.synced_uids == set()
    assert cursor.last_sync_uid == 0
    assert cursor.uidnext == 1


def test_cursor_expunge_reconciliation():
    cursor = MailboxCursor(account_id="acc-01", mailbox="INBOX", uidvalidity=100)
    cursor.record_synced([1, 2, 3, 4, 5])

    # Server now only has UIDs 1, 3, 5 (2 and 4 were expunged)
    server_uids = {1, 3, 5}
    expunged = cursor.reconcile_expunges(server_uids)
    assert expunged == [2, 4]
    assert cursor.synced_uids == {1, 3, 5}
    assert cursor.last_sync_uid == 5


def test_cursor_vault_persistence_and_m6_migration():
    cursor = MailboxCursor(account_id="acc-01", mailbox="INBOX", uidvalidity=777)
    cursor.record_synced([101, 102], new_uidnext=105)

    vault_data: dict[str, Any] = {}
    cursor.save_to_vault(vault_data)
    assert "m7_sync_cursor_v1" in vault_data
    assert "INBOX" in vault_data["m7_sync_cursor_v1"]

    # Reload from vault
    loaded = MailboxCursor.load_from_vault(vault_data, "acc-01", "INBOX")
    assert loaded.uidvalidity == 777
    assert loaded.synced_uids == {101, 102}
    assert loaded.last_sync_uid == 102

    # Backward compatibility with legacy m6_mailbox_v1
    legacy_vault_data = {
        "m6_mailbox_v1": {
            "mailbox": "INBOX",
            "uidvalidity": 888,
            "rows": [{"uid": 50}, {"uid": 51}],
        }
    }
    migrated = MailboxCursor.load_from_vault(legacy_vault_data, "acc-02", "INBOX")
    assert migrated.uidvalidity == 888
    assert migrated.synced_uids == {50, 51}
    assert migrated.last_sync_uid == 51


# =============================================================================
# 2. Metadata-First Encrypted Mailbox Index Tests (WS-03C & WS-03D)
# =============================================================================

def test_index_upsert_removal_and_unread_counts():
    idx = MailboxIndex(account_id="acc-01", mailbox="INBOX", uidvalidity=1000)

    msg1 = IndexedMessage(
        uid=1, uidvalidity=1000, mailbox="INBOX", account_id="acc-01",
        sender_display="Alice", sender_address="alice@example.com", subject="Meeting",
        seen=False
    )
    msg2 = IndexedMessage(
        uid=2, uidvalidity=1000, mailbox="INBOX", account_id="acc-01",
        sender_display="Bob", sender_address="bob@example.com", subject="Project Update",
        seen=True, flags=(r"\Seen",)
    )

    assert idx.upsert_message(msg1) is True
    assert idx.upsert_message(msg2) is True
    assert idx.get_total_count() == 2
    assert idx.get_unread_count() == 1

    # Mark msg1 as read
    assert idx.set_seen(1, True) is True
    assert idx.get_unread_count() == 0

    # Remove msg2
    removed = idx.remove_message(2)
    assert removed == msg2
    assert idx.get_total_count() == 1


def test_index_query_filtering_and_pagination():
    idx = MailboxIndex(account_id="acc-01", mailbox="INBOX", uidvalidity=1000)
    for i in range(1, 11):
        idx.upsert_message(
            IndexedMessage(
                uid=i, uidvalidity=1000, mailbox="INBOX", account_id="acc-01",
                sender_display=f"User {i}", sender_address=f"user{i}@example.com",
                subject=f"Quarterly Report {i}" if i % 2 == 0 else f"General Note {i}",
                seen=(i % 3 == 0)
            )
        )

    # Total 10 messages, ordered newest-first by UID
    all_msgs = idx.list_messages(limit=20)
    assert len(all_msgs) == 10
    assert all_msgs[0].uid == 10
    assert all_msgs[-1].uid == 1

    # Pagination: before_uid=6
    page = idx.list_messages(limit=3, before_uid=6)
    assert [m.uid for m in page] == [5, 4, 3]

    # Unread-only filter
    unread = idx.list_messages(unread_only=True)
    assert all(not m.seen for m in unread)

    # Query search
    reports = idx.list_messages(query="Quarterly")
    assert len(reports) == 5
    assert all("Quarterly" in m.subject for m in reports)


def test_index_snippet_sanitization():
    raw_snippet = "Hello <script>alert(1)</script> \u202eRTL\x00\x01\x1f World!"
    cleaned = sanitize_snippet(raw_snippet, max_length=50)
    assert "<script>" not in cleaned
    assert "\u202e" not in cleaned
    assert "\x00" not in cleaned
    assert "Hello" in cleaned
    assert "World!" in cleaned


def test_index_vault_schema_migration_and_dual_save():
    legacy_data = {
        "m6_mailbox_v1": {
            "mailbox": "INBOX",
            "uidvalidity": 2000,
            "rows": [
                {"uid": 10, "sender": "Charlie <charlie@example.com>", "subject": "Hello", "date": formatdate(), "size": 1200, "seen": False},
                {"uid": 11, "sender": "Dana <dana@example.com>", "subject": "Contract", "date": formatdate(), "size": 3400, "seen": True},
            ]
        }
    }

    # Automatically migrates into MailboxIndex
    idx = MailboxIndex.load_from_vault(legacy_data, "acc-charlie", "INBOX")
    assert idx.get_total_count() == 2
    assert idx.get_unread_count() == 1

    msg10 = idx.get_message(10)
    assert msg10 is not None
    assert msg10.sender_display == "Charlie"
    assert msg10.sender_address == "charlie@example.com"
    assert msg10.seen is False

    # Save to vault maintains both modern m7_mailbox_index_v1 and legacy m6_mailbox_v1
    vault_out: dict[str, Any] = {}
    idx.save_to_vault(vault_out)
    assert "m7_mailbox_index_v1" in vault_out
    assert "m6_mailbox_v1" in vault_out
    assert len(vault_out["m6_mailbox_v1"]["rows"]) == 2


# =============================================================================
# 3. Practical Attachment Pipeline & Resource Limits Tests (WS-03E)
# =============================================================================

def test_attachment_filename_sanitization_traversal_and_reserved_names():
    # Path traversal stripped
    assert sanitize_attachment_filename("../../etc/passwd") == "passwd"
    assert sanitize_attachment_filename("..\\..\\Windows\\System32\\cmd.exe") == "cmd.exe"

    # Reserved Windows device names prefixed
    assert sanitize_attachment_filename("CON.txt") == "safe_CON.txt"
    assert sanitize_attachment_filename("prn") == "safe_prn"
    assert sanitize_attachment_filename("aux.pdf") == "safe_aux.pdf"
    assert sanitize_attachment_filename("NUL.tar.gz") == "safe_NUL.tar.gz"

    # Trailing dots and spaces stripped
    assert sanitize_attachment_filename("document.pdf. . ") == "document.pdf"

    # Alternate data streams stripped
    assert sanitize_attachment_filename("secret.txt:hidden_stream") == "secret.txt"

    # Fallback name for empty or dangerous names
    assert sanitize_attachment_filename("", fallback_id="123") == "attachment_123.bin"
    assert sanitize_attachment_filename("...", fallback_id="456") == "attachment_456.bin"


def test_export_attachment_destination_validation(tmp_path: Path):
    valid_file = tmp_path / "valid_export.pdf"
    assert validate_export_destination(valid_file) == valid_file.resolve()

    # Relative path rejected
    with pytest.raises(PathTraversalSecurityError):
        validate_export_destination("relative/path.pdf")

    # UNC path rejected
    with pytest.raises(PathTraversalSecurityError):
        validate_export_destination(r"\\remote-server\share\file.pdf")

    # Reserved Windows device name in path rejected
    with pytest.raises(PathTraversalSecurityError):
        validate_export_destination(tmp_path / "CON" / "file.pdf")


def test_export_attachment_atomic_no_clobber(tmp_path: Path):
    target = tmp_path / "export_test.pdf"
    sample_data = b"%PDF-1.4 sample PDF content"

    # First export succeeds atomically
    exported = AttachmentPipeline.export_attachment(sample_data, target)
    assert exported.is_file()
    assert exported.read_bytes() == sample_data

    # Overwrite attempt fails closed (atomic no-clobber)
    with pytest.raises(FileExistsError):
        AttachmentPipeline.export_attachment(b"overwriting bytes", target)


def test_encrypted_attachment_cache(tmp_path: Path):
    key = secrets.token_bytes(32)
    cache = EncryptedAttachmentCache(tmp_path / "cache", key)

    payload = b"Top secret corporate financial report in PDF format"
    stored_path = cache.store(payload)
    assert stored_path.is_file()
    assert stored_path.suffix == ".enc"
    assert stored_path.read_bytes() != payload  # Encrypted at rest

    chash = hashlib.sha256(payload).hexdigest()
    decrypted = cache.retrieve(chash)
    assert decrypted == payload


def test_attachment_pipeline_pdf_and_office_documents():
    pipeline = AttachmentPipeline()

    msg = EmailMessage()
    msg["From"] = "boss@example.com"
    msg["To"] = "employee@example.com"
    msg["Subject"] = "Quarterly Reports & Presentation"
    msg.set_content("Please find attached the financial spreadsheet and briefing slides.")

    pdf_bytes = b"%PDF-1.7 500KB fake PDF content " * 15000
    xlsx_bytes = b"PK\x03\x04 fake Excel workbook " * 10000
    pptx_bytes = b"PK\x03\x04 fake PowerPoint presentation " * 12000

    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename="Finance_Q3.pdf")
    msg.add_attachment(xlsx_bytes, maintype="application", subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename="BalanceSheet.xlsx")
    msg.add_attachment(pptx_bytes, maintype="application", subtype="vnd.openxmlformats-officedocument.presentationml.presentation", filename="BoardDeck.pptx")

    raw_wire = msg.as_bytes()
    assert len(raw_wire) < MAX_WIRE_SIZE

    parsed = pipeline.parse_message(raw_wire)
    assert parsed.has_attachments is True
    assert len(parsed.attachments) == 3

    filenames = [a.filename for a in parsed.attachments]
    assert "Finance_Q3.pdf" in filenames
    assert "BalanceSheet.xlsx" in filenames
    assert "BoardDeck.pptx" in filenames

    # Verify decoded bytes match
    pdf_att = next(a for a in parsed.attachments if a.filename == "Finance_Q3.pdf")
    assert pdf_att.data == pdf_bytes


def test_attachment_pipeline_oversized_limits_rejected():
    # 1. Wire size exceeding 25 MiB
    pipeline = AttachmentPipeline(max_wire_size=1024 * 1024)
    oversized_raw = b"A" * (1024 * 1024 + 10)
    with pytest.raises(ResourceLimitExceededError):
        pipeline.parse_message(oversized_raw)

    # 2. Individual attachment exceeding limit
    pipeline2 = AttachmentPipeline(max_individual_attachment_size=5000)
    msg = EmailMessage()
    msg["Subject"] = "Oversized Attachment"
    msg.set_content("Body")
    msg.add_attachment(b"X" * 6000, maintype="application", subtype="octet-stream", filename="big.bin")
    with pytest.raises(ResourceLimitExceededError):
        pipeline2.parse_message(msg.as_bytes())

    # 3. Aggregate attachment size exceeding limit
    pipeline3 = AttachmentPipeline(max_individual_attachment_size=5000, max_aggregate_attachment_size=8000)
    msg2 = EmailMessage()
    msg2["Subject"] = "Two Attachments"
    msg2.set_content("Body")
    msg2.add_attachment(b"X" * 4500, maintype="application", subtype="octet-stream", filename="a1.bin")
    msg2.add_attachment(b"Y" * 4500, maintype="application", subtype="octet-stream", filename="a2.bin")
    with pytest.raises(ResourceLimitExceededError):
        pipeline3.parse_message(msg2.as_bytes())

    # 4. Excessive attachment count
    pipeline4 = AttachmentPipeline(max_attachment_count=2)
    msg3 = EmailMessage()
    msg3["Subject"] = "Three Attachments"
    msg3.set_content("Body")
    for i in range(3):
        msg3.add_attachment(b"test", maintype="application", subtype="octet-stream", filename=f"f{i}.bin")
    with pytest.raises(ResourceLimitExceededError):
        pipeline4.parse_message(msg3.as_bytes())


def test_attachment_pipeline_excessive_mime_nesting_rejected():
    pipeline = AttachmentPipeline()
    # Craft multipart nested beyond MAX_MIME_DEPTH (8)
    inner = b"Content-Type: text/plain\r\n\r\nDeep content"
    for i in range(MAX_MIME_DEPTH + 2):
        inner = (
            f"Content-Type: multipart/mixed; boundary=bound{i}\r\n\r\n"
            f"--bound{i}\r\n".encode("ascii")
            + inner
            + f"\r\n--bound{i}--\r\n".encode("ascii")
        )

    with pytest.raises(ResourceLimitExceededError):
        pipeline.parse_message(inner)


def test_safe_decode_transfer_encoding_malformed():
    # Valid base64
    assert safe_decode_transfer_encoding(b"SGVsbG8=", "base64", 100) == b"Hello"

    # Malformed base64 rejected
    with pytest.raises(MalformedMIMEError):
        safe_decode_transfer_encoding(b"Not valid base64!@#$%", "base64", 100)

    # Valid quoted-printable
    assert safe_decode_transfer_encoding(b"Hello=20World", "quoted-printable", 100) == b"Hello World"


# =============================================================================
# 4. Background Synchronization Engine & Protocol Tests (WS-03A, WS-03B, WS-03D)
# =============================================================================

def test_sync_engine_initial_synchronization():
    client = MockIdleClient(supports_idle=True, initial_uids=[10, 20, 30])
    vault = MockVault()

    events_received: list[str] = []
    new_msgs_received: list[IndexedMessage] = []

    engine = MailboxSyncEngine(
        account_id="acc-user1",
        account_email="user1@example.com",
        token_or_password_provider=lambda: "secret",
        client_factory=lambda: client,
        vault=vault,
        mailbox="INBOX",
        is_oauth=False,
        poll_interval_seconds=1.0,
        idle_timeout_seconds=2.0,
    )

    engine.on_sync_started = lambda acc, mbox: events_received.append("started")
    engine.on_sync_completed = lambda acc, mbox, stats: events_received.append(f"completed:{stats.new_messages_count}")
    engine.on_new_messages = lambda acc, mbox, msgs: new_msgs_received.extend(msgs)

    engine.start()

    # Wait until sync completes and IDLE is active
    assert client.idle_event.wait(timeout=5.0) is True
    engine.stop(timeout=2.0)

    assert "started" in events_received
    assert any("completed:3" in e for e in events_received)
    assert len(new_msgs_received) == 3
    assert {m.uid for m in new_msgs_received} == {10, 20, 30}

    # Verify vault contains committed cursor and index
    assert "m7_sync_cursor_v1" in vault.data
    assert "m7_mailbox_index_v1" in vault.data
    assert vault.data["m7_sync_cursor_v1"]["INBOX"]["synced_uids"] == [10, 20, 30]


def test_sync_engine_idle_notification_event_driven():
    client = MockIdleClient(supports_idle=True, initial_uids=[1, 2])
    vault = MockVault()

    new_messages_arrived: list[IndexedMessage] = []

    engine = MailboxSyncEngine(
        account_id="acc-idle",
        account_email="idle@example.com",
        token_or_password_provider=lambda: "secret",
        client_factory=lambda: client,
        vault=vault,
        is_oauth=False,
        idle_timeout_seconds=10.0,
    )
    engine.on_new_messages = lambda acc, mbox, msgs: new_messages_arrived.extend(msgs)

    engine.start()
    assert client.idle_event.wait(timeout=5.0) is True

    # Initial 2 messages synced
    assert len(new_messages_arrived) == 2

    # Simulate arrival of message 3 on server while idling
    client.idle_terminated_event.clear()
    client._seed_message(3, "Urgent Notice", "Boss <boss@example.com>")
    client.uids.append(3)

    # Push untagged server event * 3 EXISTS
    client.unsolicited_notifications.append(b"* 3 EXISTS")

    # Verify client woke up from IDLE, sent DONE, and synced message 3
    assert client.idle_terminated_event.wait(timeout=5.0) is True

    # Give small window for sync loop to process and re-idle
    time.sleep(0.3)
    engine.stop(timeout=2.0)

    assert len(new_messages_arrived) == 3
    assert new_messages_arrived[-1].uid == 3
    assert new_messages_arrived[-1].subject == "Urgent Notice"


def test_sync_engine_idle_unsupported_fallback_to_degraded_polling():
    client = MockIdleClient(supports_idle=False, initial_uids=[100])
    vault = MockVault()

    states_observed: list[SyncState] = []

    engine = MailboxSyncEngine(
        account_id="acc-noidle",
        account_email="noidle@example.com",
        token_or_password_provider=lambda: "secret",
        client_factory=lambda: client,
        vault=vault,
        is_oauth=False,
        poll_interval_seconds=1.0,
    )
    engine.on_state_changed = lambda old, new, d: states_observed.append(new)

    engine.start()
    time.sleep(0.5)
    engine.stop(timeout=2.0)

    assert SyncState.DEGRADED_POLLING in states_observed
    assert vault.data["m7_sync_cursor_v1"]["INBOX"]["synced_uids"] == [100]


def test_sync_engine_network_interruption_and_reconnection():
    client = MockIdleClient(supports_idle=True, initial_uids=[1])
    vault = MockVault()

    states_observed: list[SyncState] = []

    engine = MailboxSyncEngine(
        account_id="acc-drop",
        account_email="drop@example.com",
        token_or_password_provider=lambda: "secret",
        client_factory=lambda: client,
        vault=vault,
        is_oauth=False,
        backoff_initial=0.1,
        backoff_multiplier=1.5,
        idle_timeout_seconds=5.0,
    )
    engine.on_state_changed = lambda old, new, d: states_observed.append(new)

    engine.start()
    assert client.idle_event.wait(timeout=5.0) is True

    # Drop connection abruptly
    client.drop_connection_on_next_op = True
    client.unsolicited_notifications.append(b"* 1 EXISTS")

    # Engine should transition to RECONNECTING and then CONNECTING again
    time.sleep(0.4)
    engine.stop(timeout=2.0)

    assert SyncState.RECONNECTING in states_observed


def test_sync_engine_authentication_failure():
    client = MockIdleClient(supports_idle=True, initial_uids=[1], auth_should_succeed=False)
    vault = MockVault()

    auth_failed_called = threading.Event()

    engine = MailboxSyncEngine(
        account_id="acc-authfail",
        account_email="authfail@example.com",
        token_or_password_provider=lambda: "bad_token",
        client_factory=lambda: client,
        vault=vault,
        is_oauth=False,
    )
    engine.on_auth_required = lambda acc, err: auth_failed_called.set()

    engine.start()
    assert auth_failed_called.wait(timeout=5.0) is True
    engine.stop(timeout=2.0)

    assert engine.state == SyncState.STOPPED
    # No cursor or index should be saved
    assert "m7_sync_cursor_v1" not in vault.data


def test_sync_engine_cancellation_during_fetch_and_shutdown():
    client = MockIdleClient(supports_idle=True, initial_uids=[1, 2, 3])
    vault = MockVault()

    engine = MailboxSyncEngine(
        account_id="acc-cancel",
        account_email="cancel@example.com",
        token_or_password_provider=lambda: "secret",
        client_factory=lambda: client,
        vault=vault,
        is_oauth=False,
    )

    engine.start()
    time.sleep(0.05)
    engine.stop(timeout=2.0)

    assert engine.state == SyncState.STOPPED
    assert not engine._worker_thread.is_alive()


def test_sync_engine_prevents_duplicate_workers():
    client = MockIdleClient(supports_idle=True, initial_uids=[1])
    vault = MockVault()

    engine = MailboxSyncEngine(
        account_id="acc-dup",
        account_email="dup@example.com",
        token_or_password_provider=lambda: "secret",
        client_factory=lambda: client,
        vault=vault,
        is_oauth=False,
    )

    engine.start()
    first_thread = engine._worker_thread

    # Secondary start call does not spawn a second thread
    engine.start()
    assert engine._worker_thread is first_thread

    engine.stop(timeout=2.0)


def test_sync_engine_uidvalidity_change_triggers_index_reset():
    # Initial sync with UIDVALIDITY = 1111
    client1 = MockIdleClient(supports_idle=True, uidvalidity=1111, initial_uids=[1, 2])
    vault = MockVault()

    engine = MailboxSyncEngine(
        account_id="acc-rollover",
        account_email="rollover@example.com",
        token_or_password_provider=lambda: "secret",
        client_factory=lambda: client1,
        vault=vault,
        is_oauth=False,
    )

    engine.start()
    assert client1.idle_event.wait(timeout=5.0) is True
    engine.stop(timeout=2.0)

    assert vault.data["m7_sync_cursor_v1"]["INBOX"]["uidvalidity"] == 1111
    assert len(vault.data["m7_mailbox_index_v1"]["INBOX"]["messages"]) == 2

    # Now server reconstructs mailbox with new UIDVALIDITY = 2222 and only UID 10
    client2 = MockIdleClient(supports_idle=True, uidvalidity=2222, initial_uids=[10])

    engine2 = MailboxSyncEngine(
        account_id="acc-rollover",
        account_email="rollover@example.com",
        token_or_password_provider=lambda: "secret",
        client_factory=lambda: client2,
        vault=vault,
        is_oauth=False,
    )

    engine2.start()
    assert client2.idle_event.wait(timeout=5.0) is True
    engine2.stop(timeout=2.0)

    # Stale UIDs 1 and 2 must be gone; new UID 10 present
    assert vault.data["m7_sync_cursor_v1"]["INBOX"]["uidvalidity"] == 2222
    assert vault.data["m7_sync_cursor_v1"]["INBOX"]["synced_uids"] == [10]
    indexed_uids = [m["uid"] for m in vault.data["m7_mailbox_index_v1"]["INBOX"]["messages"]]
    assert indexed_uids == [10]


def test_sync_engine_preserves_seen_flag_on_background_peek():
    """Prove that background metadata synchronization does NOT mark messages as \\Seen."""
    client = MockIdleClient(supports_idle=True, initial_uids=[1])
    assert client.flags_map[1] == []
    vault = MockVault()

    engine = MailboxSyncEngine(
        account_id="acc-peek",
        account_email="peek@example.com",
        token_or_password_provider=lambda: "secret",
        client_factory=lambda: client,
        vault=vault,
        is_oauth=False,
    )

    engine.start()
    assert client.idle_event.wait(timeout=5.0) is True
    engine.stop(timeout=2.0)

    # Verify command log used BODY.PEEK and EXAMINE
    assert any("EXAMINE" in cmd for cmd in client.command_log)
    assert any("BODY.PEEK" in cmd for cmd in client.command_log)

    # Invariant: Server flag remains UNREAD
    assert client.flags_map[1] == []

    # Vault reflects unread message
    assert vault.data["m7_mailbox_index_v1"]["INBOX"]["messages"][0]["seen"] is False


def test_sync_engine_crash_rollback_safety():
    """Verify transactional safety: failure during commit rolls back cleanly."""
    client = MockIdleClient(supports_idle=True, initial_uids=[1, 2])
    vault = MockVault()
    vault.should_fail_commit = True  # Inject commit failure

    engine = MailboxSyncEngine(
        account_id="acc-crash",
        account_email="crash@example.com",
        token_or_password_provider=lambda: "secret",
        client_factory=lambda: client,
        vault=vault,
        is_oauth=False,
        backoff_initial=0.1,
    )

    engine.start()
    time.sleep(0.2)
    engine.stop(timeout=2.0)

    # Database rolled back; no corrupted partial records committed
    assert "m7_sync_cursor_v1" not in vault.data
    assert "m7_mailbox_index_v1" not in vault.data


# =============================================================================
# 5. MailboxService WS-05 Application-Level API Integration Tests
# =============================================================================

def test_mailbox_service_application_apis():
    from mailbox_client.service import MailboxService
    from experiments.m4.model import AccountAccess
    from experiments.m5.model import Budget
    from mailbox_client.model import MessageKey
    from experiments.m3.types import AccountContext, AccountId, DeviceId

    # Create dummy account context
    ctx = AccountContext(AccountId.new(), DeviceId.new(), "https://accounts.google.com", "user_sub")
    access = AccountAccess()
    lease = access.select(ctx)

    vault_data = {
        "m7_mailbox_index_v1": {
            "INBOX": {
                "account_id": ctx.account.value,
                "mailbox": "INBOX",
                "uidvalidity": 9000,
                "messages": [
                    {
                        "uid": 10, "uidvalidity": 9000, "mailbox": "INBOX", "account_id": ctx.account.value,
                        "sender_display": "Boss", "sender_address": "boss@example.com", "subject": "Review Plan",
                        "date": formatdate(), "date_ts": 1000.0, "size": 2048, "seen": False, "flags": []
                    },
                    {
                        "uid": 11, "uidvalidity": 9000, "mailbox": "INBOX", "account_id": ctx.account.value,
                        "sender_display": "Alice", "sender_address": "alice@example.com", "subject": "Quarterly Budget",
                        "date": formatdate(), "date_ts": 2000.0, "size": 4096, "seen": True, "flags": [r"\Seen"]
                    }
                ]
            }
        }
    }
    vault = MockVault(vault_data)

    service = MailboxService(vault=vault, access=access, google=None, mailbox=unittest.mock.MagicMock(), provider=unittest.mock.MagicMock())
    budget = Budget(threading.Event(), time.monotonic() + 10)

    # 1. get_indexed_messages
    msgs = service.get_indexed_messages(lease, budget)
    assert len(msgs) == 2
    assert msgs[0].uid == 11
    assert msgs[1].uid == 10

    # 2. Query filtering via API
    budget_msgs = service.get_indexed_messages(lease, budget, query="Budget")
    assert len(budget_msgs) == 1
    assert budget_msgs[0].subject == "Quarterly Budget"

    # 3. get_unread_counts
    unread, total = service.get_unread_counts(lease, budget)
    assert unread == 1
    assert total == 2
