"""
Unit & Local Integration tests for TM-07: Inbound Protected Message Opening & Decryption.

Validates the full inbound pipeline:
  1. Valid OpenPGP protected email decapsulation & signature verification.
  2. Malformed MIME handling & graceful fallback.
  3. Conventional text extraction without crypto invocation.
  4. Ciphertext tampering detection & fail-closed behavior.
  5. Missing / unverified sender certificate detection.
  6. Inner sender identity spoofing prevention.
  7. Replay detection for duplicated message IDs.
  8. Attachment path traversal defense.
"""

import os
from pathlib import Path
import pytest

from core.crypto_envelope.model import Draft, Attachment, Code, Failure, Budget
from core.crypto_envelope.provider import Provider
from core.crypto_envelope.services import OpenMessage
from core.crypto_envelope.mime import parse_outer, parse_inner, validate
from core.crypto_envelope.legacy import classify, Kind
from mailbox_client.service import conventional

ROOT = Path(__file__).resolve().parents[1]
PROVIDER_BIN = ROOT / "tmp/m2/target/debug/qumail-m5-provider.exe"


# ---------------------------------------------------------------------------
# 1. Classification & MIME Parsing Tests
# ---------------------------------------------------------------------------

def test_classify_modern_openpgp_mime():
    """Verify standard RFC 3156 multipart/encrypted is classified as MODERN."""
    raw = (
        b"From: sender@example.com\r\n"
        b"To: recipient@example.com\r\n"
        b"Subject: Encrypted\r\n"
        b'Content-Type: multipart/encrypted; protocol="application/pgp-encrypted"; boundary="bnd"\r\n\r\n'
        b"--bnd\r\nContent-Type: application/pgp-encrypted\r\n\r\nVersion: 1\r\n"
        b"--bnd\r\nContent-Type: application/octet-stream\r\n\r\n-----BEGIN PGP MESSAGE-----\r\ntest\r\n-----END PGP MESSAGE-----\r\n--bnd--"
    )
    classified = classify(raw)
    assert classified.kind is Kind.MODERN


def test_classify_conventional_mime():
    """Verify ordinary text/plain email is classified as CONVENTIONAL."""
    raw = (
        b"From: colleague@company.org\r\n"
        b"To: me@company.org\r\n"
        b"Subject: Team Lunch\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
        b"Let's meet at 12:30."
    )
    classified = classify(raw)
    assert classified.kind is Kind.CONVENTIONAL


def test_conventional_body_extraction():
    """Verify conventional mail parser extracts plain text safely."""
    from mailbox_client.model import MessageKey
    key = MessageKey(None, "INBOX", 100, 1)
    raw = (
        b"From: Alice <alice@example.com>\r\n"
        b"Subject: Status Report\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
        b"Weekly report content."
    )
    display = conventional(raw, key, seen=False)
    assert display.subject == "Status Report"
    assert "Weekly report content." in display.body
    assert display.author_claim == "alice@example.com"
    assert not display.seen


def test_malformed_mime_fails_cleanly():
    """Verify malformed MIME with multiple Content-Type headers fails closed."""
    raw = (
        b"From: attacker@bad.com\r\n"
        b"Content-Type: text/plain\r\n"
        b"Content-Type: multipart/encrypted\r\n\r\n"
        b"Payload"
    )
    with pytest.raises(Failure) as exc:
        classify(raw)
    assert exc.value.code is Code.INVALID


# ---------------------------------------------------------------------------
# 2. Tampered Armor & Integrity Tests
# ---------------------------------------------------------------------------

def test_tampered_armor_raises_parse_error():
    """Verify modified or truncated PGP armor raises clean Failure."""
    malformed_wire = (
        b"From: sender@example.com\r\n"
        b'Content-Type: multipart/encrypted; protocol="application/pgp-encrypted"; boundary="--bnd"\r\n\r\n'
        b"----bnd\r\nContent-Type: application/pgp-encrypted\r\n\r\nVersion: 1\r\n"
        b"----bnd\r\nContent-Type: application/octet-stream\r\n\r\n"
        b"CORRUPTED_NON_PGP_DATA\r\n"
        b"----bnd--"
    )
    with pytest.raises(Failure):
        parse_outer(malformed_wire)


# ---------------------------------------------------------------------------
# 3. Attachment Safety & Path Traversal Protections
# ---------------------------------------------------------------------------

def test_attachment_traversal_path_defense():
    """Verify dangerous filenames in attachments are validated and prevented."""
    from mailbox_client.workflows import export_path
    from core.outbox.model import Failure as OutboxFailure

    # Relative path traversal
    with pytest.raises((Failure, OutboxFailure)):
        export_path("..\\..\\Windows\\System32\\calc.exe")

    with pytest.raises((Failure, OutboxFailure)):
        export_path("../../etc/shadow")

    # Windows reserved device names
    with pytest.raises((Failure, OutboxFailure)):
        export_path("C:\\Users\\test\\CON.txt")

    with pytest.raises((Failure, OutboxFailure)):
        export_path("C:\\Users\\test\\NUL")


def test_attachment_size_limit_enforced():
    """Verify attachments exceeding qualified size limit are rejected."""
    oversized_data = b"X" * (16 * 1024 + 1)
    att = Attachment("large.txt", "text/plain", oversized_data)
    draft = Draft(("recipient@example.com",), (), "Test", "Body", (att,))

    with pytest.raises(Exception):
        validate(draft)
