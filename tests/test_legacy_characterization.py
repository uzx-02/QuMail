"""Unsafe behavior intentionally recorded for later milestones; never security gates."""
from unittest.mock import patch

import pytest

from crypto import level1_otp, level2_aes, tqr
from kme.key_models import QuantumKey

pytestmark = pytest.mark.characterization


def test_f04_legacy_xor_accepts_altered_content():
    key = QuantumKey("fixture", b"A" * 32, "fixture-sae", "fixture-time")
    plaintext = b"pay 100 units".ljust(32, b" ")
    result = level1_otp.encrypt(plaintext, key)
    forged = bytes([result["ciphertext"][0] ^ 1]) + result["ciphertext"][1:]
    assert level1_otp.decrypt(forged, key) != plaintext


def test_f05_dispatch_metadata_can_bypass_gcm_verification():
    key = QuantumKey("fixture", b"A" * 32, "fixture-sae", "fixture-time")
    result = level2_aes.encrypt(b"x" * 32, key)
    metadata = dict(result["metadata"], tqr_level=1, tag="invalid", pad_length=0)
    with patch.object(tqr.kme_client, "retrieve_key", return_value=key):
        assert len(tqr.decrypt(result["ciphertext"], metadata)) == 32


def test_f03_simulator_releases_keys_without_caller_authentication():
    from kme.virtual_node import app
    sender = app.test_client()
    other = app.test_client()
    issued = sender.post("/api/v1/keys", json={"sae_id": "unregistered", "key_size": 256})
    assert issued.status_code == 200
    fetched = other.get("/api/v1/keys/" + issued.json["key_id"])
    assert fetched.json["key_value"] == issued.json["key_value"]


def test_f07_smtp_precedes_failed_durable_prerequisites():
    from ui.compose_window import _SendPayload, _SendWorker
    events = []
    payload = _SendPayload("alice@gmail.com", "bob@example.invalid", "subject", "body", 3, True, "")

    def fail_record(**kwargs):
        events.append("record-failed")
        raise OSError("fixture disk failure")

    with (
        patch("crypto.tqr.encrypt", return_value=({"ciphertext": b"c", "metadata": {"tqr_level": 3, "key_id": "fixture"}}, b"fixture-private")),
        patch("transport.smtp_sender.send_email", side_effect=lambda *a: events.append("smtp-accepted")),
        patch("certificates.cert_generator.generate", side_effect=fail_record),
        patch("portal.portal_server.store_session") as store,
        patch("ui.compose_window._persist_send_key") as persist,
    ):
        with pytest.raises(OSError, match="fixture disk failure"):
            _SendWorker(payload)._execute()
    assert events == ["smtp-accepted", "record-failed"]
    store.assert_not_called()
    persist.assert_not_called()


def test_f10_cloud_initialization_failure_selects_volatile_memory(monkeypatch):
    from portal import portal_server as portal
    monkeypatch.setattr(portal, "_PORTAL_MODE", "cloud")
    monkeypatch.setattr(portal, "_firestore_available", True)
    with patch("google.cloud.firestore.Client", side_effect=RuntimeError("fixture backend failure")):
        assert portal._get_firestore() is None
        url = portal.store_session(b"ciphertext", {"tqr_level": 3}, b"fixture-private")
    assert portal._memory_store[url.rsplit("/", 1)[-1]]["private_key"] == b"fixture-private"


def test_f11_consumption_does_not_destroy_backend_key():
    from portal import portal_server as portal
    url = portal.store_session(b"ciphertext", {"tqr_level": 3}, b"fixture-private")
    session_id = url.rsplit("/", 1)[-1]
    portal._mark_consumed(session_id)
    assert portal.retrieve_private_key(session_id) == b"fixture-private"
    with pytest.raises(portal.PortalSessionError):
        portal._get_session_for_portal(session_id)


def test_f15_legacy_parser_accepts_duplicate_control_part():
    from mime.encapsulator import encapsulate
    from mime.decapsulator import decapsulate
    message = encapsulate("a@example.invalid", "b@example.invalid", "visible", b"c", {"tqr_level": 2})
    message.attach(message.get_payload()[0])
    assert decapsulate(message) == (b"c", {"tqr_level": 2})
    assert message["Subject"] == "visible"
    assert message.get_param("protocol") == "application/qumail-pgp"
