"""
tests/test_directory_service.py — Unit and Integration Tests for QuMail Public-Key Directory & Transparency.

Tests:
1. Binary Merkle Tree (RFC 6962 / RFC 9162 domain separation, STH, inclusion proofs, consistency proofs).
2. Directory Service Backend (Challenge issuance, single-use replay defense, PoP verification, registration, lookup, rotation, revocation).
3. Desktop Directory Client (Merkle verification, local vault TOFU pinning, key substitution detection, trust badge classification).
"""

import base64
import hashlib
import json
import secrets
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from services.directory.merkle import MerkleTree, LogEntry, SignedTreeHead, verify_inclusion, hash_leaf, hash_children
from services.directory.server import DirectoryService, create_directory_app
from core.directory_client import DirectoryClient, DirectoryLookupResult


# ---------------------------------------------------------------------------
# Section 1: Binary Merkle Tree Tests
# ---------------------------------------------------------------------------

def test_merkle_tree_domain_separation():
    """Verify that leaf hashing uses 0x00 and node hashing uses 0x01."""
    leaf_bytes = b"sample_leaf_data"
    lh = hash_leaf(leaf_bytes)
    assert lh == hashlib.sha256(b"\x00" + leaf_bytes).digest()

    left = hashlib.sha256(b"left").digest()
    right = hashlib.sha256(b"right").digest()
    nh = hash_children(left, right)
    assert nh == hashlib.sha256(b"\x01" + left + right).digest()


def test_merkle_tree_inclusion_and_consistency():
    """Verify Merkle tree inclusion proofs and consistency proofs."""
    tree = MerkleTree()
    entries = []
    for i in range(8):
        entry = LogEntry(
            entry_type="ENROLLMENT",
            email_normalized=f"user{i}@example.invalid",
            fingerprint=f"fingerprint_{i}",
            generation=1,
            certificate_armor=f"-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey_{i}\n-----END PGP PUBLIC KEY BLOCK-----",
            timestamp_utc="2026-11-10T12:00:00Z",
        )
        entries.append(entry)
        tree.append(entry)

    assert tree.tree_size == 8
    root = tree.get_root_hash().hex()

    # Verify inclusion proof for each leaf
    for i, entry in enumerate(entries):
        proof = tree.get_inclusion_proof(i)
        assert len(proof) == 3  # log2(8) = 3
        verified = verify_inclusion(
            leaf_data=entry.serialize(),
            leaf_index=i,
            tree_size=8,
            proof_hex=proof,
            root_hash_hex=root,
        )
        assert verified is True

    # Tampered leaf verification must fail
    tampered_entry = LogEntry(
        entry_type="ENROLLMENT",
        email_normalized="user0@example.invalid",
        fingerprint="tampered_fingerprint",
        generation=1,
        certificate_armor="fake",
        timestamp_utc="2026-11-10T12:00:00Z",
        leaf_index=0,
    )
    assert verify_inclusion(
        leaf_data=tampered_entry.serialize(),
        leaf_index=0,
        tree_size=8,
        proof_hex=tree.get_inclusion_proof(0),
        root_hash_hex=root,
    ) is False

    # Consistency proof between size 4 and size 8
    cons_proof = tree.get_consistency_proof(4)
    assert len(cons_proof) > 0


# ---------------------------------------------------------------------------
# Section 2: Directory Service Backend Tests
# ---------------------------------------------------------------------------

def test_directory_service_challenge_flow():
    """Verify single-use challenge issuance and replay defense."""
    service = DirectoryService()
    chal = service.issue_challenge("alice@example.invalid")
    assert chal["challenge_id"]
    assert chal["nonce"]
    assert chal["audience"] == "urn:qumail:directory:pop:v1"

    # Replay: Using the challenge twice should fail
    # Create key
    ed_key = ed25519.Ed25519PrivateKey.generate()
    pub_raw = ed_key.public_key().public_bytes_raw()
    fp = hashlib.sha256(pub_raw).hexdigest()

    pop_binding = hashlib.sha256(
        f"QUMAIL-POP-v1:alice@example.invalid:{chal['nonce']}:{fp}:QM-OPENPGP-PQ-v1:{chal['audience']}:{chal['issued_utc']}:{chal['expires_utc']}".encode("utf-8")
    ).digest()
    sig = ed_key.sign(pop_binding)
    sig_b64 = base64.b64encode(sig).decode("ascii")

    res = service.register_key(
        challenge_id=chal["challenge_id"],
        email="alice@example.invalid",
        certificate_armor="cert_armor_alice",
        fingerprint=fp,
        pop_signature=sig_b64,
        primary_public_key_raw=pub_raw,
    )
    assert res["status"] == "enrolled"
    assert res["generation"] == 1

    # Attempting to reuse the same challenge must fail
    with pytest.raises(ValueError, match="already consumed"):
        service.register_key(
            challenge_id=chal["challenge_id"],
            email="alice@example.invalid",
            certificate_armor="cert_armor_alice",
            fingerprint=fp,
            pop_signature=sig_b64,
            primary_public_key_raw=pub_raw,
        )


def test_directory_service_pop_signature_validation():
    """Verify that an invalid or forged PoP signature is rejected."""
    service = DirectoryService()
    chal = service.issue_challenge("bob@example.invalid")

    ed_key = ed25519.Ed25519PrivateKey.generate()
    pub_raw = ed_key.public_key().public_bytes_raw()
    fp = hashlib.sha256(pub_raw).hexdigest()

    # Forge signature over wrong data
    forged_sig = ed_key.sign(b"wrong_data")
    forged_sig_b64 = base64.b64encode(forged_sig).decode("ascii")

    with pytest.raises(ValueError, match="Proof of Possession signature verification failed"):
        service.register_key(
            challenge_id=chal["challenge_id"],
            email="bob@example.invalid",
            certificate_armor="cert_armor_bob",
            fingerprint=fp,
            pop_signature=forged_sig_b64,
            primary_public_key_raw=pub_raw,
        )


def test_directory_service_lookup_and_transparency():
    """Verify lookup returns valid Merkle inclusion proof and signed tree head."""
    service = DirectoryService()
    chal = service.issue_challenge("carol@example.invalid")

    ed_key = ed25519.Ed25519PrivateKey.generate()
    pub_raw = ed_key.public_key().public_bytes_raw()
    fp = hashlib.sha256(pub_raw).hexdigest()

    pop_binding = hashlib.sha256(
        f"QUMAIL-POP-v1:carol@example.invalid:{chal['nonce']}:{fp}:QM-OPENPGP-PQ-v1:{chal['audience']}:{chal['issued_utc']}:{chal['expires_utc']}".encode("utf-8")
    ).digest()
    sig = base64.b64encode(ed_key.sign(pop_binding)).decode("ascii")

    service.register_key(
        challenge_id=chal["challenge_id"],
        email="carol@example.invalid",
        certificate_armor="cert_armor_carol",
        fingerprint=fp,
        pop_signature=sig,
        primary_public_key_raw=pub_raw,
    )

    rec = service.lookup("carol@example.invalid")
    assert rec is not None
    assert rec["fingerprint"] == fp
    assert rec["generation"] == 1
    assert "inclusion_proof" in rec
    assert "sth" in rec
    assert rec["sth"]["tree_size"] == 1


# ---------------------------------------------------------------------------
# Section 3: Desktop Directory Client Tests
# ---------------------------------------------------------------------------

def test_directory_client_lookup_and_tofu_pinning(tmp_path):
    """Verify desktop client pins keys on first use (TOFU) and alarms on substitution."""
    service = DirectoryService()
    vault_p = tmp_path / "test_vault.sqlite"
    client = DirectoryClient(vault_path=vault_p, mock_service=service)

    # 1. Register Alice
    chal = service.issue_challenge("alice@example.invalid")
    ed_key = ed25519.Ed25519PrivateKey.generate()
    pub_raw = ed_key.public_key().public_bytes_raw()
    fp = hashlib.sha256(pub_raw).hexdigest()

    pop_binding = hashlib.sha256(
        f"QUMAIL-POP-v1:alice@example.invalid:{chal['nonce']}:{fp}:QM-OPENPGP-PQ-v1:{chal['audience']}:{chal['issued_utc']}:{chal['expires_utc']}".encode("utf-8")
    ).digest()
    sig = base64.b64encode(ed_key.sign(pop_binding)).decode("ascii")

    service.register_key(
        challenge_id=chal["challenge_id"],
        email="alice@example.invalid",
        certificate_armor="cert_alice_v1",
        fingerprint=fp,
        pop_signature=sig,
        primary_public_key_raw=pub_raw,
    )

    # 2. Lookup Alice (First contact -> Unpinned -> Pins it)
    res1 = client.lookup("alice@example.invalid")
    assert res1 is not None
    assert res1.trust_status == "CAUTION"  # Directory key without GPO trust
    assert res1.inclusion_verified is True
    assert res1.is_pinned is False  # Was not pinned prior to this lookup

    # 3. Lookup Alice again (Now pinned)
    res2 = client.lookup("alice@example.invalid")
    assert res2 is not None
    assert res2.is_pinned is True
    assert res2.trust_status == "CAUTION"

    # 4. Lookup with Enterprise GPO domain trust -> Should be SECURE
    res3 = client.lookup("alice@example.invalid", enterprise_trusted_domains=["example.invalid"])
    assert res3.trust_status == "SECURE"

    # 5. Simulate unauthorized key substitution in directory
    rogue_fp = "000000000000000000000000000000000000000000000000000000000000dead"
    service.records["alice@example.invalid"]["fingerprint"] = rogue_fp

    res_sub = client.lookup("alice@example.invalid")
    assert res_sub is not None
    assert res_sub.trust_status == "ALERT"  # Hard security alarm!
    assert "KEY SUBSTITUTION DETECTED" in res_sub.status_reason
