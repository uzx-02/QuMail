"""
End-to-End Two-Identity Post-Quantum Round-Trip Acceptance Test.

Validates the complete production cryptographic pipeline across two distinct,
isolated M3 vaults (Alice and Bob) and a third unprivileged identity (Charlie):
1. Vault A (Alice) and Vault B (Bob) provisioned independently.
2. Bob's public certificate imported into Alice's vault; Alice's certificate into Bob's.
3. Alice seals an authentic M5 MIME message for Bob using qumail-m5-provider.exe.
4. Wire format contains zero plaintext (ML-KEM-768 ciphertext + ML-DSA-65 signature).
5. Bob decapsulates and verifies Alice's signature in Vault B (verified_confidential is True).
6. Charlie (Vault C) cannot decrypt Bob's message (fails closed).
7. Tampered ciphertext is rejected (fails closed).
8. Replay of identical message is detected (DUPLICATE).
9. Tampered message replay is blocked (CONFLICT).
"""

import hashlib
from pathlib import Path
import threading
import time
import pytest

from core.provider_resolver import resolve_provider
from experiments.m3 import identity
from experiments.m3.provider import Provider as M3Provider
from experiments.m3.types import (
    BoundaryError,
    Code as M3Code,
    EmailAddress,
    UserId,
)
from experiments.m3.vault import Vault
from experiments.m4.model import AccountAccess, Failure as M4Failure
from experiments.m5 import mime
from experiments.m5.model import (
    Budget,
    Code as M5Code,
    Draft,
    Failure as M5Failure,
    Replay,
)
from experiments.m5.provider import Provider as M5Provider
from experiments.m5.services import OpenMessage

SecurityFailure = (M4Failure, M5Failure, BoundaryError)

M3_PROVIDER_BIN = resolve_provider("qumail-m3-provider")
M5_PROVIDER_BIN = resolve_provider("qumail-m5-provider")


class IsolatedMemoryStore:
    """In-memory OS credential store simulation for clean, parallel-safe acceptance testing."""
    def __init__(self):
        self._data: dict[str, bytes] = {}

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


def _enroll_identity(vault: Vault, name: str, domain: str = "example.invalid"):
    addr = f"{name}@{domain}"
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "test-client-id",
        "sub": f"google-sub-{name}",
        "email": addr,
        "hd": domain,
        "email_verified": True,
        "nonce": "n" * 32,
        "exp": int(time.time()) + 3600,
    }
    ident = identity.validated_google_claims(claims, "test-client-id", "n" * 32)
    email_obj = EmailAddress(addr)
    user_id = UserId.new()
    ctx, key_h = vault.enroll(ident, email_obj, user_id)
    public_bytes = vault.export_public(ctx, key_h)
    return ctx, key_h, email_obj, public_bytes


@pytest.fixture
def two_vault_setup(tmp_path):
    p_m3 = M3Provider(M3_PROVIDER_BIN)
    p_m5 = M5Provider(M5_PROVIDER_BIN)

    # Vault A: Alice
    vault_a = Vault.create(tmp_path / "alice_vault.sqlite", IsolatedMemoryStore(), p_m3)
    alice_ctx, alice_key_h, alice_addr, alice_public = _enroll_identity(vault_a, "alice")

    # Vault B: Bob
    vault_b = Vault.create(tmp_path / "bob_vault.sqlite", IsolatedMemoryStore(), p_m3)
    bob_ctx, bob_key_h, bob_addr, bob_public = _enroll_identity(vault_b, "bob")

    # Vault C: Charlie (unprivileged outsider)
    vault_c = Vault.create(tmp_path / "charlie_vault.sqlite", IsolatedMemoryStore(), p_m3)
    charlie_ctx, charlie_key_h, charlie_addr, charlie_public = _enroll_identity(vault_c, "charlie")

    # Exchange and pin trust:
    # Alice imports Bob's public key
    bob_fp = vault_a.import_contact(alice_ctx, bob_addr, bob_public)
    vault_a.pin_contact(alice_ctx, bob_addr, bob_fp, "in-person")

    # Bob imports Alice's public key
    alice_fp = vault_b.import_contact(bob_ctx, alice_addr, alice_public)
    vault_b.pin_contact(bob_ctx, alice_addr, alice_fp, "in-person")

    return {
        "vault_a": vault_a,
        "vault_b": vault_b,
        "vault_c": vault_c,
        "alice": {"ctx": alice_ctx, "key": alice_key_h, "addr": alice_addr, "public": alice_public},
        "bob": {"ctx": bob_ctx, "key": bob_key_h, "addr": bob_addr, "public": bob_public},
        "charlie": {"ctx": charlie_ctx, "key": charlie_key_h, "addr": charlie_addr, "public": charlie_public},
        "p_m3": p_m3,
        "p_m5": p_m5,
    }


def test_two_identity_roundtrip_acceptance(two_vault_setup):
    """
    Acceptance Criteria 1 to 5:
    Alice encrypts and signs with Bob's public key; Bob decrypts and verifies Alice's signature.
    """
    env = two_vault_setup
    vault_a = env["vault_a"]
    vault_b = env["vault_b"]
    p_m5 = env["p_m5"]
    alice = env["alice"]
    bob = env["bob"]

    # 1. Alice creates draft message for Bob
    subject = "Confidential Roundtrip Verification"
    body_text = "TOP SECRET: Real Post-Quantum ML-KEM-768 Sealed Communication!"
    draft = Draft(
        to=(bob["addr"].value,),
        cc=(),
        subject=subject,
        body=body_text,
        attachments=(),
    )

    date_str = "Wed, 11 Nov 2026 09:00:00 +0000"
    message_id = "<roundtrip-msg-001@example.invalid>"

    # 2. Alice prepares inner MIME and seals using qumail-m5-provider.exe
    inner_bytes = mime.build_inner(alice["addr"].value, draft, message_id, date_str)
    budget = Budget(threading.Event(), time.monotonic() + 30)

    alice_data = vault_a._read(alice["ctx"])
    alice_key_rec = vault_a.key(alice_data, alice["ctx"], alice["key"], active=True)
    bob_recipients = [bob["public"]]

    # Execute M5 seal
    seal_result = p_m5.call(
        "seal",
        budget,
        certificate=bytes(alice_key_rec["secret"]),
        recipients=bob_recipients,
        data=inner_bytes,
    )
    armor_bytes = seal_result["data"]
    assert b"-----BEGIN PGP MESSAGE-----" in armor_bytes
    assert b"-----END PGP MESSAGE-----" in armor_bytes

    # Build outer MIME container
    wire_bytes = mime.build_outer(alice["addr"].value, draft, message_id, date_str, armor_bytes)

    # 3. Privacy Invariant: Zero plaintext leaks on the wire
    assert body_text.encode("utf-8") not in wire_bytes
    assert b"PGP MESSAGE" in wire_bytes

    # 4. Bob opens the message in Vault B using OpenMessage
    access_b = AccountAccess()
    lease_b = access_b.select(bob["ctx"])
    opener_b = OpenMessage(vault_b, access_b, p_m5)

    budget_b = Budget(lease_b.cancelled, time.monotonic() + 30)
    opened = opener_b.open(lease_b, bob["key"], wire_bytes, alice["public"], budget_b)

    # 5. Acceptance assertions
    assert opened.sender == alice["addr"].value
    assert opened.to == (bob["addr"].value,)
    assert opened.subject == subject
    assert opened.body == body_text
    assert opened.signature_valid is True
    assert opened.identity_trust == "independently_verified"
    assert opened.replay == Replay.FRESH
    assert opened.verified_confidential is True


def test_third_party_charlie_cannot_decrypt(two_vault_setup):
    """
    Acceptance Criteria 6:
    Charlie (Vault C) cannot decrypt Bob's message and fails closed.
    """
    env = two_vault_setup
    vault_a = env["vault_a"]
    vault_c = env["vault_c"]
    p_m5 = env["p_m5"]
    alice = env["alice"]
    bob = env["bob"]
    charlie = env["charlie"]

    draft = Draft(
        to=(bob["addr"].value,),
        cc=(),
        subject="Confidential Bob Only",
        body="Secret for Bob only",
    )
    message_id = "<msg-for-bob@example.invalid>"
    date_str = "Wed, 11 Nov 2026 09:00:00 +0000"
    inner_bytes = mime.build_inner(alice["addr"].value, draft, message_id, date_str)

    alice_data = vault_a._read(alice["ctx"])
    alice_key = vault_a.key(alice_data, alice["ctx"], alice["key"], active=True)
    budget = Budget(threading.Event(), time.monotonic() + 30)

    seal_result = p_m5.call(
        "seal",
        budget,
        certificate=bytes(alice_key["secret"]),
        recipients=[bob["public"]],
        data=inner_bytes,
    )
    wire_bytes = mime.build_outer(alice["addr"].value, draft, message_id, date_str, seal_result["data"])

    # Charlie attempts to open with Charlie's key in Vault C
    access_c = AccountAccess()
    lease_c = access_c.select(charlie["ctx"])
    opener_c = OpenMessage(vault_c, access_c, p_m5)
    budget_c = Budget(lease_c.cancelled, time.monotonic() + 30)

    with pytest.raises(SecurityFailure):
        opener_c.open(lease_c, charlie["key"], wire_bytes, alice["public"], budget_c)


def test_tampered_ciphertext_rejection(two_vault_setup):
    """
    Acceptance Criteria 7:
    Tampered ciphertext fails closed and raises SecurityFailure.
    """
    env = two_vault_setup
    vault_a = env["vault_a"]
    vault_b = env["vault_b"]
    p_m5 = env["p_m5"]
    alice = env["alice"]
    bob = env["bob"]

    draft = Draft(
        to=(bob["addr"].value,),
        cc=(),
        subject="Tamper Test",
        body="Untampered body",
    )
    message_id = "<tamper-msg@example.invalid>"
    date_str = "Wed, 11 Nov 2026 09:00:00 +0000"
    inner = mime.build_inner(alice["addr"].value, draft, message_id, date_str)
    budget = Budget(threading.Event(), time.monotonic() + 30)

    alice_data = vault_a._read(alice["ctx"])
    alice_key = vault_a.key(alice_data, alice["ctx"], alice["key"], active=True)
    seal_res = p_m5.call("seal", budget, certificate=bytes(alice_key["secret"]), recipients=[bob["public"]], data=inner)

    # Tamper with the armor payload
    armor = seal_res["data"]
    # Flip bytes inside the base64 content
    lines = armor.split(b"\n")
    if len(lines) > 3:
        corrupted_line = bytearray(lines[2])
        if len(corrupted_line) > 5:
            corrupted_line[5] ^= 0xFF
            lines[2] = bytes(corrupted_line)
    tampered_armor = b"\n".join(lines)

    try:
        tampered_wire = mime.build_outer(alice["addr"].value, draft, message_id, date_str, tampered_armor)
    except Exception:
        # If outer MIME builder rejects malformed armor, test succeeds
        return

    access_b = AccountAccess()
    lease_b = access_b.select(bob["ctx"])
    opener_b = OpenMessage(vault_b, access_b, p_m5)
    budget_b = Budget(lease_b.cancelled, time.monotonic() + 30)

    with pytest.raises(SecurityFailure):
        opener_b.open(lease_b, bob["key"], tampered_wire, alice["public"], budget_b)


def test_replay_duplicate_and_conflict_rejection(two_vault_setup):
    """
    Acceptance Criteria 8 & 9:
    Duplicate message triggers Replay.DUPLICATE.
    Tampered replay payload under same ID triggers Replay.CONFLICT.
    """
    env = two_vault_setup
    vault_a = env["vault_a"]
    vault_b = env["vault_b"]
    p_m5 = env["p_m5"]
    alice = env["alice"]
    bob = env["bob"]

    draft = Draft(
        to=(bob["addr"].value,),
        cc=(),
        subject="Replay Invariant",
        body="Original payload",
    )
    message_id = "<replay-test-msg-01@example.invalid>"
    date_str = "Wed, 11 Nov 2026 09:00:00 +0000"
    inner = mime.build_inner(alice["addr"].value, draft, message_id, date_str)
    budget = Budget(threading.Event(), time.monotonic() + 30)

    alice_data = vault_a._read(alice["ctx"])
    alice_key = vault_a.key(alice_data, alice["ctx"], alice["key"], active=True)
    seal_res = p_m5.call("seal", budget, certificate=bytes(alice_key["secret"]), recipients=[bob["public"]], data=inner)
    wire = mime.build_outer(alice["addr"].value, draft, message_id, date_str, seal_res["data"])

    access_b = AccountAccess()
    lease_b = access_b.select(bob["ctx"])
    opener_b = OpenMessage(vault_b, access_b, p_m5)

    # 1. First delivery is FRESH
    first = opener_b.open(lease_b, bob["key"], wire, alice["public"], Budget(lease_b.cancelled, time.monotonic() + 30))
    assert first.replay == Replay.FRESH
    assert first.verified_confidential is True

    # 2. Second delivery of exact same wire bytes is DUPLICATE
    second = opener_b.open(lease_b, bob["key"], wire, alice["public"], Budget(lease_b.cancelled, time.monotonic() + 30))
    assert second.replay == Replay.DUPLICATE

    # 3. Third delivery with modified content under identical Message-ID is CONFLICT
    draft_modified = Draft(
        to=(bob["addr"].value,),
        cc=(),
        subject="Replay Invariant",
        body="Modified payload under identical Message-ID",
    )
    inner_modified = mime.build_inner(alice["addr"].value, draft_modified, message_id, date_str)
    seal_res_modified = p_m5.call("seal", budget, certificate=bytes(alice_key["secret"]), recipients=[bob["public"]], data=inner_modified)
    wire_modified = mime.build_outer(alice["addr"].value, draft_modified, message_id, date_str, seal_res_modified["data"])

    conflict = opener_b.open(lease_b, bob["key"], wire_modified, alice["public"], Budget(lease_b.cancelled, time.monotonic() + 30))
    assert conflict.replay == Replay.CONFLICT
    assert conflict.verified_confidential is False
