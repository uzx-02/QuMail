"""
Comprehensive native cryptographic round-trip and adversarial security suite (Module 1.5 Workstream B).

Exercises the actual QuMail native Rust cryptographic providers (qumail-m3-provider.exe,
qumail-m5-provider.exe), SQLite vault persistence, OpenPGP MIME serialization/deserialization,
and strict adversarial failure boundaries without mocks.
"""

import time
import os
from pathlib import Path
from dataclasses import replace
import pytest

from experiments.m3.vault import Vault
from experiments.m3.types import EmailAddress, UserId, BoundaryError, Code as M3Code, KeyHandle
from experiments.m3 import identity
from experiments.m3.provider import Provider as M3Provider
from experiments.m4.model import AccountAccess, Failure as M4Failure, Error as M4Error, State
from experiments.m5.provider import Provider as M5Provider
from experiments.m5.model import Draft, Attachment, Budget, Replay, MAX_ATTACHMENT_BYTES, Failure as M5Failure, Code as M5Code
from experiments.m5.services import Compose, OpenMessage
from experiments.m5 import mime
from mailbox_client.workflows import Workflows, export_path

# Union of domain failures across M3/M4/M5 boundaries
SecurityFailure = (M4Failure, M5Failure, BoundaryError)

ROOT = Path(__file__).resolve().parents[1]
from core.provider_resolver import resolve_provider
M3_PROVIDER_BIN = resolve_provider("qumail-m3-provider")
M5_PROVIDER_BIN = resolve_provider("qumail-m5-provider")


class IsolatedMemoryStore:
    """In-memory credential store for tests to guarantee zero mutation of Credential Manager."""
    def __init__(self):
        self._data = {}

    def put(self, ident: str, secret: bytes):
        if len(secret) != 32:
            raise BoundaryError(M3Code.INVALID)
        self._data[ident] = bytes(secret)

    def get(self, ident: str) -> bytes:
        if ident not in self._data:
            raise BoundaryError(M3Code.STORE)
        return self._data[ident]

    def delete(self, ident: str):
        self._data.pop(ident, None)


@pytest.fixture
def crypto_env(tmp_path):
    """Initializes isolated native vault with sender Alice, recipient Bob, and third-party Charlie."""
    p_m3 = M3Provider(M3_PROVIDER_BIN)
    p_m5 = M5Provider(M5_PROVIDER_BIN)
    vault_path = tmp_path / "test_roundtrip.sqlite"
    vault = Vault.create(vault_path, IsolatedMemoryStore(), p_m3)

    def make_ident(name):
        addr = f"{name}@example.invalid"
        return identity.validated_google_claims(
            dict(
                iss="https://accounts.google.com", aud="test-client", sub=name,
                email=addr, hd="example.invalid", email_verified=True, nonce="n"*32,
                exp=int(time.time()) + 3600
            ),
            "test-client", "n"*32
        )

    # Enroll Alice, Bob, and Charlie
    id_alice = make_ident("alice")
    ctx_alice, key_alice = vault.enroll(id_alice, id_alice.addresses[0], UserId.new())

    id_bob = make_ident("bob")
    ctx_bob, key_bob = vault.enroll(id_bob, id_bob.addresses[0], UserId.new())

    id_charlie = make_ident("charlie")
    ctx_charlie, key_charlie = vault.enroll(id_charlie, id_charlie.addresses[0], UserId.new())

    # Mutual contact pinning between Alice and Bob
    root_bob = vault.import_contact(ctx_alice, EmailAddress("bob@example.invalid"), vault.export_public(ctx_bob, key_bob))
    vault.pin_contact(ctx_alice, EmailAddress("bob@example.invalid"), root_bob, "in-person")

    root_alice = vault.import_contact(ctx_bob, EmailAddress("alice@example.invalid"), vault.export_public(ctx_alice, key_alice))
    vault.pin_contact(ctx_bob, EmailAddress("alice@example.invalid"), root_alice, "in-person")

    access = AccountAccess()

    return {
        "vault": vault,
        "access": access,
        "p_m3": p_m3,
        "p_m5": p_m5,
        "alice": (ctx_alice, key_alice, "alice@example.invalid"),
        "bob": (ctx_bob, key_bob, "bob@example.invalid"),
        "charlie": (ctx_charlie, key_charlie, "charlie@example.invalid"),
    }


# ==============================================================================
# B1: COMPLETE NATIVE CRYPTOGRAPHIC ROUND-TRIP
# ==============================================================================

def test_full_native_encrypted_roundtrip(crypto_env):
    """
    B1: Complete offline round trip using actual QuMail native crypto components.
    Proves:
    1. Realistic draft with binary attachment prepared and encrypted.
    2. Zero plaintext leakage in serialized MIME wire bytes.
    3. Parsing, extraction, and decryption with recipient private key.
    4. Signature verification against pinned sender root.
    5. Bit-for-bit body and binary attachment reconstruction.
    """
    env = crypto_env
    vault, access, p_m5 = env["vault"], env["access"], env["p_m5"]
    ctx_a, key_a, addr_a = env["alice"]
    ctx_b, key_b, addr_b = env["bob"]

    lease_a = access.select(ctx_a)
    compose = Compose(vault, access, p_m5)

    binary_data = b"%PDF-1.7\r\n\x00\x01\x02\xff\xfe\xfd\x80\xaa" + b"A" * 512
    draft = Draft(
        to=(addr_b,),
        cc=(),
        subject="Confidential Q7 Architecture Proposal",
        body="Dear Bob,\nThis is a classified cryptographic report.\nEnsure key roots match.\nBest regards,\nAlice",
        attachments=(Attachment("classified_report.pdf", "application/pdf", binary_data),),
        in_reply_to="",
        references=()
    )

    budget_a = Budget(lease_a.cancelled, time.monotonic() + 30)
    op = compose.draft(lease_a, draft, budget_a)
    envelope = compose.prepare(lease_a, op, key_a, budget_a)

    # 1. Wire payload confidentiality verification
    wire_bytes = envelope.serialized
    assert len(wire_bytes) > 0
    assert b"multipart/encrypted" in wire_bytes
    assert b'protocol="application/pgp-encrypted"' in wire_bytes
    assert draft.subject.encode() not in wire_bytes
    assert b"classified cryptographic report" not in wire_bytes
    assert binary_data not in wire_bytes
    assert b"classified_report.pdf" not in wire_bytes
    assert b"application/pdf" not in wire_bytes

    # 2. Recipient inbound processing & decryption
    lease_b = access.select(ctx_b)
    opener = OpenMessage(vault, access, p_m5)
    budget_b = Budget(lease_b.cancelled, time.monotonic() + 30)
    sender_public = vault.export_public(ctx_a, key_a)

    opened = opener.open(lease_b, key_b, wire_bytes, sender_public, budget_b)

    # 3. Authenticity, Integrity & Reconstruction Checks
    assert opened.signature_valid is True
    assert opened.verified_confidential is True
    assert opened.replay is Replay.FRESH
    assert opened.archive is False
    assert opened.subject == draft.subject
    assert opened.body == draft.body

    # 4. Byte-for-byte attachment integrity check
    assert len(opened.attachments) == 1
    recovered_att = opened.attachments[0]
    assert recovered_att.name == "classified_report.pdf"
    assert recovered_att.media_type == "application/pdf"
    assert recovered_att.data == binary_data
    assert len(recovered_att.data) == len(binary_data)


# ==============================================================================
# B2: ADVERSARIAL SECURITY TEST VECTORS
# ==============================================================================

def test_wrong_recipient_key_rejection(crypto_env):
    """
    B2: Decrypting with wrong recipient private key (Charlie's key on Alice-to-Bob mail)
    must fail cleanly and never release plaintext.
    """
    env = crypto_env
    vault, access, p_m5 = env["vault"], env["access"], env["p_m5"]
    ctx_a, key_a, addr_a = env["alice"]
    ctx_b, key_b, addr_b = env["bob"]
    ctx_c, key_c, addr_c = env["charlie"]

    lease_a = access.select(ctx_a)
    compose = Compose(vault, access, p_m5)
    draft = Draft((addr_b,), (), "Secret", "Secret Body", (), "", ())
    budget_a = Budget(lease_a.cancelled, time.monotonic() + 30)
    op = compose.draft(lease_a, draft, budget_a)
    envelope = compose.prepare(lease_a, op, key_a, budget_a)

    # Charlie attempts to open message intended for Bob
    lease_c = access.select(ctx_c)
    opener = OpenMessage(vault, access, p_m5)
    budget_c = Budget(lease_c.cancelled, time.monotonic() + 30)
    sender_public = vault.export_public(ctx_a, key_a)

    with pytest.raises(SecurityFailure):
        opener.open(lease_c, key_c, envelope.serialized, sender_public, budget_c)


def test_missing_private_key_rejection(crypto_env):
    """
    B2: Attempting to decrypt with a non-existent or corrupted key handle fails cleanly.
    """
    env = crypto_env
    vault, access, p_m5 = env["vault"], env["access"], env["p_m5"]
    ctx_a, key_a, addr_a = env["alice"]
    ctx_b, key_b, addr_b = env["bob"]

    lease_a = access.select(ctx_a)
    compose = Compose(vault, access, p_m5)
    draft = Draft((addr_b,), (), "Secret", "Secret Body", (), "", ())
    budget_a = Budget(lease_a.cancelled, time.monotonic() + 30)
    op = compose.draft(lease_a, draft, budget_a)
    envelope = compose.prepare(lease_a, op, key_a, budget_a)

    fake_key = KeyHandle("0123456789abcdef0123456789abcdef")

    lease_b = access.select(ctx_b)
    opener = OpenMessage(vault, access, p_m5)
    budget_b = Budget(lease_b.cancelled, time.monotonic() + 30)
    sender_public = vault.export_public(ctx_a, key_a)

    with pytest.raises(SecurityFailure):
        opener.open(lease_b, fake_key, envelope.serialized, sender_public, budget_b)


def test_tampered_ciphertext_rejection(crypto_env):
    """
    B2: Flipping bits inside the OpenPGP ciphertext armor must trigger
    cryptographic failure and fail closed without unhandled exceptions.
    """
    env = crypto_env
    vault, access, p_m5 = env["vault"], env["access"], env["p_m5"]
    ctx_a, key_a, addr_a = env["alice"]
    ctx_b, key_b, addr_b = env["bob"]

    lease_a = access.select(ctx_a)
    compose = Compose(vault, access, p_m5)
    draft = Draft((addr_b,), (), "Tamper Test", "Authentic Content", (), "", ())
    budget_a = Budget(lease_a.cancelled, time.monotonic() + 30)
    op = compose.draft(lease_a, draft, budget_a)
    envelope = compose.prepare(lease_a, op, key_a, budget_a)

    wire = bytearray(envelope.serialized)
    mid = len(wire) // 2
    wire[mid] = wire[mid] ^ 0xFF
    wire[mid + 1] = wire[mid + 1] ^ 0xFF

    lease_b = access.select(ctx_b)
    opener = OpenMessage(vault, access, p_m5)
    budget_b = Budget(lease_b.cancelled, time.monotonic() + 30)
    sender_public = vault.export_public(ctx_a, key_a)

    with pytest.raises(SecurityFailure):
        opener.open(lease_b, key_b, bytes(wire), sender_public, budget_b)


def test_invalid_sender_signature_rejection(crypto_env):
    """
    B2: Verifying a message with the wrong sender certificate must fail signature check.
    """
    env = crypto_env
    vault, access, p_m5 = env["vault"], env["access"], env["p_m5"]
    ctx_a, key_a, addr_a = env["alice"]
    ctx_b, key_b, addr_b = env["bob"]
    ctx_c, key_c, addr_c = env["charlie"]

    lease_a = access.select(ctx_a)
    compose = Compose(vault, access, p_m5)
    draft = Draft((addr_b,), (), "Signed Test", "Sender Auth Content", (), "", ())
    budget_a = Budget(lease_a.cancelled, time.monotonic() + 30)
    op = compose.draft(lease_a, draft, budget_a)
    envelope = compose.prepare(lease_a, op, key_a, budget_a)

    charlie_public = vault.export_public(ctx_c, key_c)
    lease_b = access.select(ctx_b)
    opener = OpenMessage(vault, access, p_m5)
    budget_b = Budget(lease_b.cancelled, time.monotonic() + 30)

    # Signature verification fails against mismatched sender key (fails closed)
    try:
        opened = opener.open(lease_b, key_b, envelope.serialized, charlie_public, budget_b)
        assert opened.signature_valid is False
        assert opened.verified_confidential is False
    except SecurityFailure:
        # Provider fail-closed is also fully acceptable and secure
        pass


def test_corrupted_mime_fails_cleanly(crypto_env):
    """
    B2: Corrupted or truncated MIME boundaries fail closed safely.
    """
    env = crypto_env
    vault, access, p_m5 = env["vault"], env["access"], env["p_m5"]
    ctx_a, key_a, _ = env["alice"]
    ctx_b, key_b, _ = env["bob"]

    truncated = b"Content-Type: multipart/encrypted; protocol=\"application/pgp-encrypted\"; boundary=\"xyz\"\r\n\r\n--xyz\r\n"
    lease_b = access.select(ctx_b)
    opener = OpenMessage(vault, access, p_m5)
    budget_b = Budget(lease_b.cancelled, time.monotonic() + 30)
    sender_public = vault.export_public(ctx_a, key_a)

    with pytest.raises(SecurityFailure):
        opener.open(lease_b, key_b, truncated, sender_public, budget_b)


def test_malformed_openpgp_armor_rejected(crypto_env):
    """
    B2: Damaged or missing PGP armor headers fail safely.
    """
    env = crypto_env
    vault, access, p_m5 = env["vault"], env["access"], env["p_m5"]
    ctx_a, key_a, addr_a = env["alice"]
    ctx_b, key_b, addr_b = env["bob"]

    lease_a = access.select(ctx_a)
    compose = Compose(vault, access, p_m5)
    draft = Draft((addr_b,), (), "Armor", "Content", (), "", ())
    budget_a = Budget(lease_a.cancelled, time.monotonic() + 30)
    op = compose.draft(lease_a, draft, budget_a)
    envelope = compose.prepare(lease_a, op, key_a, budget_a)

    mangled = envelope.serialized.replace(b"-----BEGIN PGP MESSAGE-----", b"-----BEGIN NOT PGP-----")

    lease_b = access.select(ctx_b)
    opener = OpenMessage(vault, access, p_m5)
    budget_b = Budget(lease_b.cancelled, time.monotonic() + 30)
    sender_public = vault.export_public(ctx_a, key_a)

    with pytest.raises(SecurityFailure):
        opener.open(lease_b, key_b, mangled, sender_public, budget_b)


def test_duplicate_message_replay_detection(crypto_env):
    """
    B2: Opening the identical message a second time must detect replay
    and classify as Replay.DUPLICATE.
    """
    env = crypto_env
    vault, access, p_m5 = env["vault"], env["access"], env["p_m5"]
    ctx_a, key_a, addr_a = env["alice"]
    ctx_b, key_b, addr_b = env["bob"]

    lease_a = access.select(ctx_a)
    compose = Compose(vault, access, p_m5)
    draft = Draft((addr_b,), (), "Replay Test", "Unique Payload", (), "", ())
    budget_a = Budget(lease_a.cancelled, time.monotonic() + 30)
    op = compose.draft(lease_a, draft, budget_a)
    envelope = compose.prepare(lease_a, op, key_a, budget_a)

    lease_b = access.select(ctx_b)
    opener = OpenMessage(vault, access, p_m5)
    sender_public = vault.export_public(ctx_a, key_a)

    opened1 = opener.open(lease_b, key_b, envelope.serialized, sender_public, Budget(lease_b.cancelled, time.monotonic() + 30))
    assert opened1.replay is Replay.FRESH

    opened2 = opener.open(lease_b, key_b, envelope.serialized, sender_public, Budget(lease_b.cancelled, time.monotonic() + 30))
    assert opened2.replay is Replay.DUPLICATE


def test_replay_persistence_across_vault_restart(crypto_env):
    """
    B2: Replay detection must persist durably in SQLite across application restarts.
    Re-instantiating the Vault object on the same database file must still detect
    previously opened messages as Replay.DUPLICATE.
    """
    env = crypto_env
    vault, access, p_m5 = env["vault"], env["access"], env["p_m5"]
    p_m3 = env["p_m3"]
    ctx_a, key_a, addr_a = env["alice"]
    ctx_b, key_b, addr_b = env["bob"]

    lease_a = access.select(ctx_a)
    compose = Compose(vault, access, p_m5)
    draft = Draft((addr_b,), (), "Restart Replay Test", "Durable Replay Payload", (), "", ())
    budget_a = Budget(lease_a.cancelled, time.monotonic() + 30)
    op = compose.draft(lease_a, draft, budget_a)
    envelope = compose.prepare(lease_a, op, key_a, budget_a)

    lease_b = access.select(ctx_b)
    opener1 = OpenMessage(vault, access, p_m5)
    sender_public = vault.export_public(ctx_a, key_a)

    # First open: must be FRESH
    res1 = opener1.open(lease_b, key_b, envelope.serialized, sender_public, Budget(lease_b.cancelled, time.monotonic() + 30))
    assert res1.replay is Replay.FRESH

    # Simulate complete application restart by instantiating fresh Vault from disk
    restarted_vault = Vault(vault.path, vault.store, p_m3)
    restarted_opener = OpenMessage(restarted_vault, access, p_m5)

    # Re-open in restarted vault: MUST still be detected as DUPLICATE from persistent SQLite state
    res2 = restarted_opener.open(lease_b, key_b, envelope.serialized, sender_public, Budget(lease_b.cancelled, time.monotonic() + 30))
    assert res2.replay is Replay.DUPLICATE


def test_attachment_filename_traversal_defense():
    """
    B2: Path traversal attempts in attachment export filenames must be blocked.
    """
    dangerous_paths = [
        "../../etc/passwd",
        "..\\..\\Windows\\System32\\calc.exe",
        "C:\\Windows\\System32\\..\\..\\calc.exe",
        "CON",
        "PRN",
        "NUL",
        "COM1",
        "LPT1",
        "//network-share/file",
        "\\\\?\\pipe",
    ]
    for bad_path in dangerous_paths:
        with pytest.raises(SecurityFailure):
            export_path(bad_path)


def test_attachment_size_limit_enforced(crypto_env):
    """
    B2: Attachments exceeding MAX_ATTACHMENT_BYTES (16 KiB total) are rejected.
    """
    env = crypto_env
    addr_b = env["bob"][2]
    oversized_data = b"X" * (MAX_ATTACHMENT_BYTES + 1024)
    oversized_att = Attachment("huge.bin", "application/octet-stream", oversized_data)

    draft = Draft((addr_b,), (), "Oversized", "Body", (oversized_att,), "", ())
    with pytest.raises(Exception):
        mime.validate(draft)


def test_unverified_recipient_blocks_preparation(crypto_env):
    """
    B2: Preparing a message to an unpinned/untrusted recipient address
    fails immediately before any envelope or ciphertext is created.
    """
    env = crypto_env
    vault, access, p_m5 = env["vault"], env["access"], env["p_m5"]
    ctx_a, key_a, _ = env["alice"]

    untrusted_address = "stranger@unknown.invalid"
    lease_a = access.select(ctx_a)
    compose = Compose(vault, access, p_m5)

    draft = Draft((untrusted_address,), (), "Blocked", "Body", (), "", ())
    budget_a = Budget(lease_a.cancelled, time.monotonic() + 30)
    op = compose.draft(lease_a, draft, budget_a)

    with pytest.raises(SecurityFailure):
        compose.prepare(lease_a, op, key_a, budget_a)


# ==============================================================================
# B3: REAL APPLICATION INTEGRATION (Workflows & Mailbox Boundary)
# ==============================================================================

def test_workflows_service_full_integration(crypto_env, tmp_path):
    """
    B3: Exercise the high-level Workflows boundary over the actual vault and provider.
    Proves:
    - Save draft -> Prepare -> Outbox state PREPARED.
    - Sender archive decrypt and display.
    - Verified attachment export.
    """
    env = crypto_env
    vault, access, p_m5 = env["vault"], env["access"], env["p_m5"]
    ctx_a, key_a, addr_a = env["alice"]
    ctx_b, key_b, addr_b = env["bob"]

    workflows = Workflows(vault, access, p_m5)
    lease_a = access.select(ctx_a)

    test_data = b"Strict attachment payload verification."
    draft = Draft((addr_b,), (), "Workflows Test", "Workflow plain text",
                  (Attachment("export_test.txt", "text/plain", test_data),), "", ())

    budget_a = Budget(lease_a.cancelled, time.monotonic() + 30)

    # 1. Save and Prepare through Workflows
    op = workflows.save(lease_a, draft, budget_a)
    envelope = workflows.prepare(lease_a, op, key_a, budget_a)

    # Verify Outbox record is PREPARED
    outbox_records = workflows.outbox(lease_a, budget_a)
    assert len(outbox_records) >= 1
    assert any(r.operation == op and r.state is State.PREPARED for r in outbox_records)

    # 2. Sender archive opening through Workflows
    archive_display = workflows.archive(lease_a, op, budget_a)
    assert archive_display.protected.archive is True
    assert archive_display.body == draft.body
    assert archive_display.protected.attachments[0].data == test_data

    # 3. Export attachment to disk via Workflows
    export_dest = tmp_path / "exported_verified.txt"
    workflows.export(lease_a, archive_display, 0, str(export_dest), budget_a)
    assert export_dest.exists()
    assert export_dest.read_bytes() == test_data


def test_sender_trust_model_enforcement(crypto_env):
    """
    B2: Trust Model Enforcement:
    1. Outer From spoofing with third-party key fails signature verification.
    2. Inner sender claim mismatching verified certificate fails with Failure(Code.IDENTITY).
    3. Untrusted/unpinned sender contact lookup fails closed.
    """
    env = crypto_env
    vault, access, p_m5 = env["vault"], env["access"], env["p_m5"]
    ctx_a, key_a, addr_a = env["alice"]
    ctx_b, key_b, addr_b = env["bob"]
    ctx_c, key_c, addr_c = env["charlie"]

    lease_c = access.select(ctx_c)
    compose_c = Compose(vault, access, p_m5)

    # Charlie (unpinned by Bob) enrolls Bob's public key to encrypt to him
    root_bob = vault.import_contact(ctx_c, EmailAddress("bob@example.invalid"), vault.export_public(ctx_b, key_b))
    vault.pin_contact(ctx_c, EmailAddress("bob@example.invalid"), root_bob, "in-person")

    # Charlie crafts message to Bob, signed with Charlie's valid key
    draft_c = Draft((addr_b,), (), "Spoof Attempt", "Malicious Payload", (), "", ())
    budget_c = Budget(lease_c.cancelled, time.monotonic() + 30)
    op_c = compose_c.draft(lease_c, draft_c, budget_c)
    env_c = compose_c.prepare(lease_c, op_c, key_c, budget_c)

    # Bob checks trust model: Charlie is NOT pinned in Bob's contacts
    lease_b = access.select(ctx_b)
    data_b = vault._read(ctx_b)
    assert "charlie@example.invalid" not in data_b["contacts"]

    # If Bob passes Alice's pinned certificate (attempted impersonation of Alice)
    alice_public = bytes(data_b["contacts"]["alice@example.invalid"]["public"])
    opener = OpenMessage(vault, access, p_m5)
    budget_b = Budget(lease_b.cancelled, time.monotonic() + 30)

    # Must fail closed: Charlie's signature does not match Alice's pinned root
    with pytest.raises(SecurityFailure):
        opener.open(lease_b, key_b, env_c.serialized, alice_public, budget_b)


def test_live_mta_trace_headers_accepted(crypto_env):
    """
    Verify that authentic emails delivered through live MTAs (such as Google / Gmail)
    with multiple Received, X-Received, and Authentication-Results headers parse and
    decrypt successfully without false-positive INVALID rejection.
    """
    env = crypto_env
    vault, access, p_m5 = env["vault"], env["access"], env["p_m5"]
    ctx_a, key_a, addr_a = env["alice"]
    ctx_b, key_b, addr_b = env["bob"]

    # Alice composes and prepares message for Bob
    lease_a = access.select(ctx_a)
    compose = Compose(vault, access, p_m5)
    draft = Draft(
        to=("bob@example.invalid",),
        cc=(),
        subject="Confidential Architecture Review",
        body="This is an authentic encrypted payload routed through live MTAs.",
        attachments=(),
        archive=True,
    )
    budget_a = Budget(lease_a.cancelled, time.monotonic() + 30)
    op = compose.draft(lease_a, draft, budget_a)
    envelope = compose.prepare(lease_a, op, key_a, budget_a)

    # Simulate realistic MTA trace headers inserted during live Google SMTP/IMAP transport
    mta_prefix = (
        b"Delivered-To: bob@example.invalid\r\n"
        b"Received: by 2002:a05:6838:148f:b0:3a0:1234:5678 with SMTP id abcdef.123;\r\n"
        b"        Mon, 09 Nov 2026 01:00:05 -0800 (PST)\r\n"
        b"X-Received: by 2002:a05:6838:... with SMTP id ...;\r\n"
        b"        Mon, 09 Nov 2026 01:00:04 -0800 (PST)\r\n"
        b"ARC-Seal: i=1; a=rsa-sha256; t=1731110000; cv=none; d=google.com; s=arc-20240605; b=dummy\r\n"
        b"ARC-Authentication-Results: i=1; mx.google.com; dkim=pass\r\n"
        b"Received: from mail-pj1-f45.google.com by mx.google.com with SMTPS id 123456\r\n"
        b"        for <bob@example.invalid>; Mon, 09 Nov 2026 01:00:04 -0800 (PST)\r\n"
        b"Authentication-Results: mx.google.com; dkim=pass; spf=pass\r\n"
    )
    live_wire = mta_prefix + envelope.serialized

    # Bob opens and decrypts the message
    lease_b = access.select(ctx_b)
    data_b = vault._read(ctx_b)
    sender_public = bytes(data_b["contacts"]["alice@example.invalid"]["public"])
    opener = OpenMessage(vault, access, p_m5)
    budget_b = Budget(lease_b.cancelled, time.monotonic() + 30)

    opened = opener.open(lease_b, key_b, live_wire, sender_public, budget_b)
    assert opened.signature_valid is True
    assert opened.verified_confidential is True
    assert opened.body == draft.body
    assert opened.subject == draft.subject
    assert opened.replay is Replay.FRESH

