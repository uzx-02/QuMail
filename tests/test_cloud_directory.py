"""
tests/test_cloud_directory.py — Unit and integration tests for Cloud Directory & WebLink client.

Validates:
1. Exact email normalization (Gmail dots/+tags vs non-Gmail preservation).
2. Sender-side full device-set pinning (TOFU) and unexpected change warnings.
3. POST-body directory lookup with metadata minimization.
4. Client-side WebLink key derivation, passcode gating, and URL fragment delivery.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from core.cloud_directory import (
    CloudDirectoryClient,
    ContactPinningStore,
    normalize_email,
)


def test_email_normalization_domain_rules():
    """Verify Gmail dots and +tags are stripped, while other domains preserve them."""
    # 1. Gmail & Googlemail
    assert normalize_email("Jane.Doe+newsletter@googlemail.com") == "janedoe@gmail.com"
    assert normalize_email("Alice.Smith@GMAIL.COM") == "alicesmith@gmail.com"
    assert normalize_email("bob.middle.name+tag1+tag2@gmail.com") == "bobmiddlename@gmail.com"
    assert normalize_email("  carol+work@gmail.com  ") == "carol@gmail.com"

    # 2. Non-Gmail Domains: Preserve dots and +tags, lowercase only
    assert normalize_email("John.Doe+sec@Corporate.org") == "john.doe+sec@corporate.org"
    assert normalize_email("User.Name@OUTLOOK.COM") == "user.name@outlook.com"
    assert normalize_email("  finance.audit+2026@fastmail.com  ") == "finance.audit+2026@fastmail.com"
    assert normalize_email("admin@qumail.sec") == "admin@qumail.sec"


def test_contact_device_set_pinning_tofu(tmp_path, monkeypatch):
    """Verify sender pins full device set on first contact and detects additions/mismatches."""
    monkeypatch.setenv("QUMAIL_DATA_DIR", str(tmp_path))
    store = ContactPinningStore()

    dev1 = {"device_id": "d-1", "fingerprint": "fp-1111", "device_label": "Workstation"}
    dev2 = {"device_id": "d-2", "fingerprint": "fp-2222", "device_label": "Laptop"}

    # 1. First interaction: Pinned (TOFU)
    ok, warn = store.check_and_update_device_set("bob@corporate.org", [dev1, dev2])
    assert ok is True
    assert warn == ""

    # 2. Second interaction: Exact match -> OK
    ok, warn = store.check_and_update_device_set("bob@corporate.org", [dev1, dev2])
    assert ok is True
    assert warn == ""

    # 3. Third interaction: Bob adds a third device (subset expansion)
    dev3 = {"device_id": "d-3", "fingerprint": "fp-3333", "device_label": "Tablet"}
    ok, warn = store.check_and_update_device_set("bob@corporate.org", [dev1, dev2, dev3])
    assert ok is True
    assert "added 1 new device" in warn

    # 4. Fourth interaction: Device 1 key changed unexpectedly (Potential MitM)
    dev1_tampered = {"device_id": "d-1", "fingerprint": "fp-attacker", "device_label": "Workstation"}
    ok, warn = store.check_and_update_device_set("bob@corporate.org", [dev1_tampered, dev2, dev3])
    assert ok is False
    assert "SECURITY WARNING" in warn
    assert "Potential Man-In-The-Middle" in warn


def test_directory_client_lookup_post_body(tmp_path, monkeypatch):
    """Verify lookup sends email in POST body rather than URL query (metadata minimization)."""
    monkeypatch.setenv("QUMAIL_DATA_DIR", str(tmp_path))
    client = CloudDirectoryClient(base_url="https://directory.qumail.test", session_token="mock-token-xyz")

    captured_req = {}

    def mock_urlopen(req, timeout):
        captured_req["url"] = req.full_url
        captured_req["method"] = req.get_method()
        captured_req["headers"] = dict(req.headers)
        captured_req["body"] = json.loads(req.data.decode("utf-8"))

        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = json.dumps({
            "found": True,
            "devices": [
                {
                    "device_id": "dev-01",
                    "fingerprint": "fp-abc",
                    "device_label": "Desktop",
                    "public_key_bundle": {
                        "kem_public_base64": base64.b64encode(b"dummy-kem-key").decode("ascii"),
                        "dsa_public_base64": base64.b64encode(b"dummy-dsa-key").decode("ascii"),
                    },
                }
            ],
        }).encode("utf-8")
        return mock_resp

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    res = client.lookup("Alice.Smith+test@gmail.com")
    assert res["found"] is True
    assert len(res["devices"]) == 1
    assert res["email"] == "alicesmith@gmail.com"

    # Verify metadata minimization:
    assert captured_req["url"] == "https://directory.qumail.test/api/v1/directory/lookup"
    assert "?" not in captured_req["url"], "Recipient email leaked in query string!"
    assert captured_req["method"] == "POST"
    assert captured_req["headers"]["Authorization"] == "Bearer mock-token-xyz"
    assert captured_req["body"]["email"] == "alicesmith@gmail.com"


def test_client_weblink_creation_and_fragment_key_delivery(tmp_path, monkeypatch):
    """Verify WebLink client encrypts locally, isolates #key in URL fragment, and supports passcode."""
    monkeypatch.setenv("QUMAIL_DATA_DIR", str(tmp_path))
    client = CloudDirectoryClient(base_url="https://directory.qumail.test", session_token="mock-token-xyz")

    captured_payload = {}

    def mock_urlopen(req, timeout):
        captured_payload.update(json.loads(req.data.decode("utf-8")))
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = json.dumps({
            "success": True,
            "link_id": "link-9999",
            "access_url": "https://directory.qumail.test/v/link-9999",
            "expires_at": 1800000000,
        }).encode("utf-8")
        return mock_resp

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    # 1. Plain WebLink (no passcode)
    secret_text = "CONFIDENTIAL: Post-Quantum Financial Audit Record"
    weblink = client.create_weblink(
        plaintext_body=secret_text,
        sender_email="alice@qumail.sec",
        recipient_email="bob@external.com",
        max_views=3,
        burn_after_read=True,
    )

    assert "link-9999" in weblink["access_url"]
    assert "#key=" in weblink["access_url"]
    assert weblink["has_passcode"] is False

    # Ensure key is NOT in payload uploaded to server
    raw_key_hex = weblink["access_url"].split("#key=")[1]
    assert raw_key_hex not in captured_payload["encrypted_payload"]
    assert captured_payload["has_passcode"] is False
    assert captured_payload["max_views"] == 3
    assert captured_payload["burn_after_read"] is True

    # 2. Passcode-Protected WebLink
    weblink_passcode = client.create_weblink(
        plaintext_body=secret_text,
        sender_email="alice@qumail.sec",
        recipient_email="bob@external.com",
        passcode="Secret123!",
    )
    assert weblink_passcode["has_passcode"] is True
    assert captured_payload["has_passcode"] is True
    assert captured_payload["passcode_tag"] is not None
    assert captured_payload["passcode_salt_hex"] is not None


def test_qumail_bridge_check_recipient(tmp_path, monkeypatch):
    """Verify QuMailJsApi.checkRecipient identifies cloud directory registration and TOFU."""
    monkeypatch.setenv("QUMAIL_DATA_DIR", str(tmp_path))
    from launch_react_desktop import QuMailJsApi
    api = QuMailJsApi(vault_path=tmp_path / "test_vault.db")

    # 1. Unregistered recipient -> defaults to weblink recommendation
    with patch("core.cloud_directory.CloudDirectoryClient.lookup") as mock_lookup:
        mock_lookup.return_value = {"found": False, "devices": []}
        res = api.checkRecipient("stranger@external.com")
        assert res["registered"] is False
        assert res["securityMode"] == "weblink"
        assert "not registered" in res["message"]

    # 2. Registered recipient with 2 devices
    with patch("core.cloud_directory.CloudDirectoryClient.lookup") as mock_lookup:
        mock_lookup.return_value = {
            "found": True,
            "email": "partner@secure.org",
            "devices": [{"device_id": "d1"}, {"device_id": "d2"}],
            "warning": "",
        }
        res = api.checkRecipient("Partner@Secure.org")
        assert res["registered"] is True
        assert res["deviceCount"] == 2
        assert res["securityMode"] == "pq"
        assert "Found 2 active QuMail device(s)" in res["message"]

    # 3. Registered recipient with TOFU warning
    with patch("core.cloud_directory.CloudDirectoryClient.lookup") as mock_lookup:
        mock_lookup.return_value = {
            "found": True,
            "email": "compromised@secure.org",
            "devices": [{"device_id": "d1"}],
            "warning": "SECURITY WARNING: Recipient public key has changed unexpectedly!",
        }
        res = api.checkRecipient("compromised@secure.org")
        assert res["registered"] is True
        assert "SECURITY WARNING" in res["warning"]


