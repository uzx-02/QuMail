"""Offline tests for verified-Google identity binding of existing vault rows."""

import time

import pytest

from core.provider_resolver import resolve_provider
from core.vault.identity import validated_google_claims
from core.vault.provider import Provider
from core.vault.types import BoundaryError, Code, UserId
from core.vault.vault import Vault


class MemoryStore:
    def __init__(self):
        self.values = {}

    def put(self, ident, secret):
        self.values[ident] = bytes(secret)

    def get(self, ident):
        if ident not in self.values:
            raise BoundaryError(Code.STORE)
        return self.values[ident]

    def delete(self, ident):
        self.values.pop(ident, None)


def _identity(subject: str, email: str):
    return validated_google_claims(
        {
            "iss": "https://accounts.google.com",
            "aud": "test-desktop-client",
            "azp": "test-desktop-client",
            "sub": subject,
            "email": email,
            "email_verified": True,
            "nonce": "n" * 32,
            "exp": int(time.time()) + 3600,
        },
        "test-desktop-client",
        "n" * 32,
    )


def test_binding_verified_subject_preserves_existing_key_material(tmp_path):
    provider = Provider(resolve_provider("qumail-vault-provider"))
    vault = Vault.create(tmp_path / "identity-binding.sqlite", MemoryStore(), provider)
    original = _identity("stable-google-subject", "before@gmail.com")
    ctx, handle = vault.enroll(original, original.addresses[0], UserId.new())
    root_before = vault._read(ctx)["root"]

    renamed = _identity("stable-google-subject", "after@gmail.com")
    bound = vault.bind_provider_identity(ctx, renamed)
    migrated = vault._read(bound)

    assert bound.account == ctx.account
    assert bound.device == ctx.device
    assert migrated["root"] == root_before
    assert migrated["active_key"] == handle.value
    assert migrated["address"] == "after@gmail.com"
    assert migrated["subject"] == "stable-google-subject"


def test_binding_rejects_subject_already_owned_by_another_row(tmp_path):
    provider = Provider(resolve_provider("qumail-vault-provider"))
    vault = Vault.create(tmp_path / "identity-conflict.sqlite", MemoryStore(), provider)
    first = _identity("first-subject", "first@gmail.com")
    second = _identity("second-subject", "second@gmail.com")
    vault.enroll(first, first.addresses[0], UserId.new())
    ctx_second, _ = vault.enroll(second, second.addresses[0], UserId.new())

    with pytest.raises(BoundaryError) as raised:
        vault.bind_provider_identity(ctx_second, _identity("first-subject", "second@gmail.com"))

    assert raised.value.code == Code.CONFLICT
