"""
tests/test_offline_translator.py — Unit tests for the QuMail Offline Translator subsystem.
"""

from __future__ import annotations

import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from core.offline_translator import (
    OfflineTranslatorService,
    check_hardware_compatibility,
    _dpapi_protect,
    _dpapi_unprotect,
    FLORES_MAP,
)


@pytest.fixture
def temp_service():
    temp_dir = Path(tempfile.mkdtemp())
    svc = OfflineTranslatorService(base_data_dir=temp_dir)
    yield svc
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_hardware_compatibility_scanner(temp_service):
    """Verify hardware scanner returns expected keys and reasonable bounds."""
    res = check_hardware_compatibility(temp_service.base_data_dir)
    assert res["status"] == "ok"
    assert res["total_ram_gb"] > 0
    assert res["free_ram_gb"] > 0
    assert res["free_disk_gb"] >= 0
    assert res["cpu_cores"] >= 1
    assert res["verdict"] in ("optimal", "compatible", "limited")
    assert "estimated_speed" in res


def test_dpapi_encryption_roundtrip():
    """Verify that DPAPI encrypt/decrypt round-trip produces exact original bytes."""
    secret = b"Post-Quantum Encrypted Translation Content \xf0\x9f\x94\x90"
    encrypted = _dpapi_protect(secret)
    assert encrypted != secret
    decrypted = _dpapi_unprotect(encrypted)
    assert decrypted == secret


def test_script_detection():
    """Verify script detection between Devanagari (Hindi/Marathi) and Latin (English)."""
    assert OfflineTranslatorService.detect_script("Hello world, this is a secret mail.", "hin_Deva") == "eng_Latn"
    assert OfflineTranslatorService.detect_script("नमस्ते, यह एक गोपनीय संदेश है।", "eng_Latn") == "hin_Deva"
    assert OfflineTranslatorService.detect_script("नमस्कार, हा एक सुरक्षित संदेश आहे.", "hin_Deva") == "mar_Deva"


def test_translation_vault_crud(temp_service):
    """Verify saving, caching, retrieving audit logs, and deleting translation records."""
    assert temp_service.get_translation_logs() == []
    assert temp_service.get_cached_translation("msg-1", "hi") is None

    # Save translation with subject
    temp_service.save_translation_log(
        message_id="msg-1",
        subject="Confidential Report",
        original_text="Client-side post-quantum security active.",
        translated_text="क्लाइंट-साइड पोस्ट-क्वांटम सुरक्षा सक्रिय है।",
        source_lang="eng_Latn",
        target_lang="hi",
        translated_subject="गोपनीय रिपोर्ट",
    )

    # Cached lookup
    cached = temp_service.get_cached_translation("msg-1", "hi")
    assert cached is not None
    assert cached["translatedText"] == "क्लाइंट-साइड पोस्ट-क्वांटम सुरक्षा सक्रिय है।"
    assert cached["subject"] == "Confidential Report"
    assert cached["translatedSubject"] == "गोपनीय रिपोर्ट"

    # Audit logs list
    logs = temp_service.get_translation_logs()
    assert len(logs) == 1
    assert logs[0]["messageId"] == "msg-1"
    assert logs[0]["targetLang"] == "hin_Deva"
    assert logs[0]["charCount"] > 0

    # Delete single log
    del_res = temp_service.delete_translation_log("msg-1")
    assert del_res["status"] == "ok"
    assert del_res["remaining"] == 0
    assert temp_service.get_cached_translation("msg-1", "hi") is None


def test_translation_status_uninstalled(temp_service):
    """Verify status reporting when model is not installed."""
    status = temp_service.get_status()
    assert status["isInstalled"] is False
    assert status["isDownloading"] is False
    assert status["progress"] == 0
    assert status["modelSizeMB"] == 0.0


def test_translation_model_auto_unload(temp_service):
    """Verify unload_model cleans up memory, reports state, and cancels timers."""
    temp_service._translator = "mock_translator"
    temp_service._sp_processor = "mock_sp"
    temp_service._reset_unload_timer()
    assert temp_service._unload_timer is not None
    assert temp_service.get_status()["isModelLoadedInRam"] is True

    res = temp_service.unload_model()
    assert res["status"] == "ok"
    assert res["wasLoaded"] is True
    assert res["isModelLoadedInRam"] is False
    assert temp_service._translator is None
    assert temp_service._sp_processor is None
    assert temp_service._unload_timer is None
    assert temp_service.get_status()["isModelLoadedInRam"] is False

    # Second unload when already idle
    res2 = temp_service.unload_model()
    assert res2["status"] == "ok"
    assert res2["wasLoaded"] is False
    assert res2["isModelLoadedInRam"] is False


def test_cancel_translation_in_mid_progress(temp_service):
    """Verify cancelling translation mid-progress halts inference cleanly."""
    temp_service._translator = MagicMock()
    temp_service._sp_processor = MagicMock()
    temp_service._sp_processor.encode.return_value = ["mock_tok"]
    temp_service._sp_processor.decode.return_value = "translated_sample"

    mock_res = MagicMock()
    mock_res.hypotheses = [["mock_out"]]

    def side_effect(*args, **kwargs):
        # Trigger cancellation while translating first paragraph
        temp_service.cancel_translation()
        return [mock_res]

    temp_service._translator.translate_batch.side_effect = side_effect

    # translate_text should abort on paragraph 2 because cancellation was signaled
    res = temp_service.translate_text("Paragraph 1\nParagraph 2", "hi")
    assert res["status"] == "cancelled"
    assert "cancelled" in res["error"].lower()


def test_status_reporting_clears_is_downloading_when_installed(temp_service, monkeypatch):
    """Verify get_status clears isDownloading if the model is verified to be installed on disk."""
    monkeypatch.setattr(temp_service, "is_model_installed", lambda: True)
    temp_service._download_state["isDownloading"] = True
    temp_service._download_state["progress"] = 0

    status = temp_service.get_status()
    assert status["isInstalled"] is True
    assert status["isDownloading"] is False
    assert status["progress"] == 100
    assert status["error"] is None


def test_model_integrity_rejects_tampered_artifact(temp_service, monkeypatch):
    """Presence and size alone must never make a model artifact trusted."""
    import hashlib
    import core.offline_translator as translator_module

    contents = b"known-good-test-model"
    monkeypatch.setattr(
        translator_module,
        "MODEL_FILES",
        [("model.bin", len(contents), hashlib.sha256(contents).hexdigest())],
    )
    temp_service.model_dir.mkdir(parents=True)
    model_path = temp_service.model_dir / "model.bin"
    model_path.write_bytes(b"X" * len(contents))

    ok, message = temp_service.verify_model_integrity()
    assert ok is False
    assert "SHA-256" in message

    model_path.write_bytes(contents)
    ok, message = temp_service.verify_model_integrity()
    assert ok is True
    assert message == "Model integrity verified."


