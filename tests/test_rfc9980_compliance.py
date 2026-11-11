"""
RFC 9980 (IETF Standards Track, June 2026) Official Test Vector Verification.

Validates that QuMail's dual native cryptographic engines (Sequoia OpenPGP + rPGP)
fully conform to RFC 9980 Appendix A.3:
- Primary key: ML-DSA-65 + Ed25519 (Pubkey algo 30)
- Subkey: ML-KEM-768 + X25519 (Pubkey algo 35)
- Cipher: AES-256-GCM / OCB with SEIPD v2
- Signatures: Composite lattice signatures verified before plaintext release
"""

import base64
import time
import threading
from pathlib import Path
import pytest
from core.provider_resolver import resolve_provider
from core.crypto_envelope.provider import Provider as M5Provider
from core.crypto_envelope.model import Budget
from core.vault.provider import Provider as M3Provider

A3_FINGERPRINT = "A3E2E14B6A493FF930FB27321F125E9A6880338BE9FB7DA3AE065EA65793242F"
DATA_DIR = Path(__file__).parent / "data" / "rfc9980"


def make_budget(seconds=30.0):
    return Budget(cancel=threading.Event(), deadline=time.monotonic() + seconds)


def armor_pgp_message(data: bytes) -> bytes:
    b64 = base64.b64encode(data).decode("ascii")
    lines = [b64[i:i+64] for i in range(0, len(b64), 64)]
    return ("-----BEGIN PGP MESSAGE-----\n\n" + "\n".join(lines) + "\n-----END PGP MESSAGE-----\n").encode("ascii")


@pytest.fixture(scope="module")
def rfc9980_keys():
    sec_bytes = (DATA_DIR / "a3_sec.bin").read_bytes()
    pub_bytes = (DATA_DIR / "a3_pub.bin").read_bytes()
    msg_bytes = (DATA_DIR / "a3_msg.bin").read_bytes()
    return sec_bytes, pub_bytes, msg_bytes


def test_rfc9980_appendix_a3_public_key_inspection(rfc9980_keys):
    """Verify that M3 provider accurately parses the RFC 9980 A.3 public key."""
    m3_bin = resolve_provider("qumail-m3-provider")
    m3 = M3Provider(m3_bin)
    _, pub_bytes, _ = rfc9980_keys

    info = m3.call("inspect", certificate=pub_bytes)
    assert info["fingerprint"].upper() == A3_FINGERPRINT.upper()
    assert info["profile"] == "M2-EXPERIMENT-RFC9980-AES256-GCM"
    assert "encryption" in info
    assert "signing" in info


def test_rfc9980_appendix_a3_message_decryption_sequoia(rfc9980_keys):
    """Verify Sequoia OpenPGP engine decrypts and verifies RFC 9980 A.3 encrypted message."""
    m5_bin = resolve_provider("qumail-crypto-provider")
    m5 = M5Provider(m5_bin)
    sec_bytes, pub_bytes, msg_bytes = rfc9980_keys

    armored_msg = armor_pgp_message(msg_bytes)
    result = m5.call("open", make_budget(),
                     certificate=sec_bytes,
                     sender=pub_bytes,
                     data=armored_msg)

    assert result["verified"] is True
    assert result["signer"].upper() == A3_FINGERPRINT.upper()
    assert result["data"] == b"Testing\n"


def test_rfc9980_appendix_a3_message_decryption_rpgp(rfc9980_keys):
    """Verify independent rPGP engine decrypts and verifies RFC 9980 A.3 encrypted message."""
    m5_bin = resolve_provider("qumail-crypto-provider")
    m5 = M5Provider(m5_bin)
    sec_bytes, pub_bytes, msg_bytes = rfc9980_keys

    armored_msg = armor_pgp_message(msg_bytes)
    result = m5.call("peer_open", make_budget(),
                     certificate=sec_bytes,
                     sender=pub_bytes,
                     data=armored_msg)

    assert result["verified"] is True
    assert result["signer"].upper() == A3_FINGERPRINT.upper()
    assert result["data"] == b"Testing\n"


def test_rfc9980_dual_engine_cross_seal_and_open(rfc9980_keys):
    """
    Verify complete cross-engine cryptographic interoperability:
    1. rPGP engine seals with RFC 9980 A.3 key.
    2. Sequoia engine opens and verifies the composite ML-DSA-65 signature.
    3. rPGP engine opens and verifies the composite ML-DSA-65 signature.
    """
    m5_bin = resolve_provider("qumail-crypto-provider")
    m5 = M5Provider(m5_bin)
    sec_bytes, pub_bytes, _ = rfc9980_keys

    payload = b"RFC 9980 full cross-engine seal-and-open test!"

    # 1. Seal with rPGP
    sealed = m5.call("peer_seal", make_budget(),
                     certificate=sec_bytes,
                     recipients=[pub_bytes],
                     data=payload)
    armored_ciphertext = sealed["data"]

    # 2. Open with Sequoia
    opened_sq = m5.call("open", make_budget(),
                        certificate=sec_bytes,
                        sender=pub_bytes,
                        data=armored_ciphertext)
    assert opened_sq["verified"] is True
    assert opened_sq["data"] == payload

    # 3. Open with rPGP
    opened_rp = m5.call("peer_open", make_budget(),
                        certificate=sec_bytes,
                        sender=pub_bytes,
                        data=armored_ciphertext)
    assert opened_rp["verified"] is True
    assert opened_rp["data"] == payload


def test_fresh_generated_pqc_keypair_roundtrip():
    """
    Generate a brand-new composite PQC keypair via generate() in vault provider:
    - Primary key: ML-DSA-65 + Ed25519 (certification)
    - Subkey 0: ML-DSA-65 + Ed25519 (signing)
    - Subkey 1: ML-KEM-768 + X25519 (transport encryption)
    Verify that fresh generated keys successfully seal and open messages across both engines.
    """
    m3_bin = resolve_provider("qumail-m3-provider")
    m5_bin = resolve_provider("qumail-crypto-provider")
    m3 = M3Provider(m3_bin)
    m5 = M5Provider(m5_bin)

    generated = m3.call("generate", address="pqc-user@test.invalid")
    pub_bytes = bytes(generated["public"])
    sec_bytes = bytes(generated["secret"])

    payload = b"Freshly generated ML-KEM-768 + ML-DSA-65 message payload!"

    # 1. Seal with Sequoia
    sealed = m5.call("seal", make_budget(),
                     certificate=sec_bytes,
                     recipients=[pub_bytes],
                     data=payload)
    armored_ciphertext = sealed["data"]

    # 2. Open with Sequoia
    opened_sq = m5.call("open", make_budget(),
                        certificate=sec_bytes,
                        sender=pub_bytes,
                        data=armored_ciphertext)
    assert opened_sq["verified"] is True
    assert opened_sq["data"] == payload

    # 3. Open with rPGP
    opened_rp = m5.call("peer_open", make_budget(),
                        certificate=sec_bytes,
                        sender=pub_bytes,
                        data=armored_ciphertext)
    assert opened_rp["verified"] is True
    assert opened_rp["data"] == payload

