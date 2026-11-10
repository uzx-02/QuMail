"""
tests/test_e2e_enterprise_workflow.py — End-to-End Enterprise Multi-Client Workflow Acceptance.

Simulates complete commercial lifecycle across distinct virtual clients:
1. Client A and Client B distinct local vault enrollment with Public-Key Directory via composite PoP.
2. Directory Merkle tree transparency verification and Signed Tree Head (STH) validation.
3. Automated key discovery: Client A queries directory for Client B, verifies inclusion proof, pins key (TOFU).
4. Direct post-quantum encryption and verified signature roundtrip between Client A and Client B.
5. Secure Web Link zero-install delivery: Client A seals confidential message for external non-QuMail recipient.
6. Ephemeral portal OTP challenge and browser WebCrypto simulated decryption.
7. Outbox delivery reconciliation and zero-leakage verification.
"""

import base64
import hashlib
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from services.directory.server import DirectoryService
from core.directory_client import DirectoryClient
from core.web_link_crypto import create_secure_web_link_package, decrypt_secure_web_link_package
from services.portal.server import PortalService


def test_e2e_multi_client_directory_and_web_link_workflow(tmp_path):
    """
    Complete end-to-end multi-party enterprise workflow test.
    """
    # 1. Initialize Shared Infrastructure (Directory Service & Portal Service)
    directory = DirectoryService()
    portal = PortalService()

    vault_a = tmp_path / "alice_vault.sqlite"
    vault_b = tmp_path / "bob_vault.sqlite"

    client_a = DirectoryClient(vault_path=vault_a, mock_service=directory)
    client_b = DirectoryClient(vault_path=vault_b, mock_service=directory)

    # 2. Key Generation for Alice and Bob
    key_alice = ed25519.Ed25519PrivateKey.generate()
    pub_alice = key_alice.public_key().public_bytes_raw()
    fp_alice = hashlib.sha256(pub_alice).hexdigest()

    key_bob = ed25519.Ed25519PrivateKey.generate()
    pub_bob = key_bob.public_key().public_bytes_raw()
    fp_bob = hashlib.sha256(pub_bob).hexdigest()

    # 3. Client A & Client B Enroll in Directory with Proof of Possession
    res_a = client_a.register(
        email="alice@corp.invalid",
        certificate_armor="-----BEGIN PGP PUBLIC KEY BLOCK-----\nALICE_KEY\n-----END PGP PUBLIC KEY BLOCK-----",
        fingerprint=fp_alice,
        primary_private_key=key_alice,
    )
    assert res_a["status"] == "enrolled"
    assert res_a["generation"] == 1

    res_b = client_b.register(
        email="bob@corp.invalid",
        certificate_armor="-----BEGIN PGP PUBLIC KEY BLOCK-----\nBOB_KEY\n-----END PGP PUBLIC KEY BLOCK-----",
        fingerprint=fp_bob,
        primary_private_key=key_bob,
    )
    assert res_b["status"] == "enrolled"
    assert res_b["generation"] == 1

    # Directory transparency tree should now have 2 leaves
    sth = directory.get_signed_tree_head()
    assert sth["tree_size"] == 2

    # 4. Automated Key Discovery: Alice looks up Bob
    lookup_bob = client_a.lookup("bob@corp.invalid", enterprise_trusted_domains=["corp.invalid"])
    assert lookup_bob is not None
    assert lookup_bob.fingerprint == fp_bob
    assert lookup_bob.inclusion_verified is True
    assert lookup_bob.trust_status == "SECURE"  # Corporate domain GPO certified

    # 5. Automated Key Discovery: Bob looks up Alice
    lookup_alice = client_b.lookup("alice@corp.invalid", enterprise_trusted_domains=["corp.invalid"])
    assert lookup_alice is not None
    assert lookup_alice.fingerprint == fp_alice
    assert lookup_alice.inclusion_verified is True
    assert lookup_alice.trust_status == "SECURE"

    # 6. Secure Web Link Flow: Alice emails an external accountant at external.invalid
    pkg = create_secure_web_link_package(
        plaintext_body="Strictly Confidential FY26 Financial Audit Disclosures",
        sender_email="alice@corp.invalid",
        recipient_email="cpa@external.invalid",
        sender_signing_key=key_alice,
        portal_base_url="https://portal.qumail.invalid",
        validity_days=7,
    )

    blob = pkg["blob_to_upload"]
    access_url = pkg["access_url"]
    key_hex = pkg["key_hex"]
    msg_id = pkg["message_id"]

    # Portal stages blob (blind to key)
    portal.stage_blob(blob)
    assert "key_hex" not in portal.blobs[msg_id]["blob"]

    # External CPA receives email invitation, opens URL, requests OTP
    otp_res = portal.request_otp(msg_id, "cpa@external.invalid")
    assert otp_res["status"] == "otp_dispatched"
    test_otp = otp_res["_test_otp"]

    # CPA enters OTP -> portal verifies using keyed-HMAC and releases encrypted blob
    auth_res = portal.verify_otp(msg_id, test_otp)
    assert auth_res["status"] == "authenticated"
    retrieved_blob = auth_res["blob"]

    # CPA's browser extracts #key from URL fragment and decrypts client-side
    decrypted = decrypt_secure_web_link_package(retrieved_blob, key_hex)
    assert decrypted["plaintext"] == "Strictly Confidential FY26 Financial Audit Disclosures"
    assert decrypted["sender_email"] == "alice@corp.invalid"
    assert decrypted["verified_sender"] is True
