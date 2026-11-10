"""
tests/test_react_desktop_bridge.py — Acceptance and contract tests for the React 19 + WebView2 bridge.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from launch_react_desktop import (
    FRONTEND_DIST,
    DistHTTPRequestHandler,
    QuMailJsApi,
)


def test_frontend_dist_bundle_exists():
    """Verify production Vite build artifacts exist and have required structure."""
    assert FRONTEND_DIST.exists(), f"Frontend dist directory does not exist at {FRONTEND_DIST}"
    index_html = FRONTEND_DIST / "index.html"
    assert index_html.exists(), "frontend/dist/index.html is missing"
    
    content = index_html.read_text(encoding="utf-8")
    assert '<div id="root"' in content, "Root element missing in index.html"
    assert "assets/index-" in content, "Vite hashed assets not linked in index.html"


def test_http_request_handler_mime_types():
    """Verify DistHTTPRequestHandler resolves correct MIME types for modern ES modules."""
    handler = DistHTTPRequestHandler.__new__(DistHTTPRequestHandler)
    assert handler.guess_type("bundle.js") == "application/javascript"
    assert handler.guess_type("module.mjs") == "application/javascript"
    assert handler.guess_type("styles.css") == "text/css"
    assert handler.guess_type("logo.svg") == "image/svg+xml"
    assert handler.guess_type("manifest.json") == "application/json"


def test_qumail_js_api_messages_roundtrip():
    """Verify QuMailJsApi message queries, creation, starring, and deletion."""
    api = QuMailJsApi(account_email="dr.sharma@drdo.res.in")
    msgs = api.getMessages()
    assert len(msgs) >= 3
    assert any("ML-KEM-768" in m.get("indicator", {}).get("description", "") for m in msgs)

    # Send a new message
    result = api.sendMessage({
        "recipients": ["security@cert-in.org.in"],
        "subject": "Post-Quantum Handshake Test",
        "body": "Validating ML-KEM-768 encapsulation across live nodes.",
        "attachments": [],
    })
    assert result["success"] is True
    msg_id = result["id"]

    updated_msgs = api.getMessages()
    new_msg = next((m for m in updated_msgs if m["id"] == msg_id), None)
    assert new_msg is not None
    assert new_msg["subject"] == "Post-Quantum Handshake Test"
    assert new_msg["indicator"]["badgeLevel"] == "SECURE"

    # Toggle star
    assert api.toggleStar(msg_id) is True
    assert next(m for m in api.getMessages() if m["id"] == msg_id)["starred"] is True

    # Mark read / unread
    assert api.markRead(msg_id, False) is True
    assert next(m for m in api.getMessages() if m["id"] == msg_id)["seen"] is False

    # Delete message (moves to trash first)
    assert api.deleteMessage(msg_id) is True
    assert next(m for m in api.getMessages() if m["id"] == msg_id)["folder"] == "trash"

    # Delete again (purges from trash)
    assert api.deleteMessage(msg_id) is True
    assert not any(m["id"] == msg_id for m in api.getMessages())


def test_qumail_js_api_hsm_and_entropy():
    """Verify QuMailJsApi queries live hardware TRNG coordinator and extracts entropy."""
    api = QuMailJsApi(account_email="dr.sharma@drdo.res.in")
    status = api.getHSMStatus()

    assert "mode" in status
    assert "isHardwareActive" in status
    assert "shannonEntropy" in status
    assert status["shannonEntropy"] > 7.0
    assert "activePort" in status
    assert "baudRate" in status

    # Sample entropy
    sample = api.sampleEntropy()
    assert sample["success"] is True
    assert len(sample["hex"]) == 64  # 32 bytes hex encoded
    assert sample["rate"] == 115200


def test_qumail_js_api_account_and_ports():
    """Verify account session info and COM port detection."""
    api = QuMailJsApi(account_email="dr.sharma@drdo.res.in")
    acc = api.getAccount()
    assert acc["email"] == "dr.sharma@drdo.res.in"
    assert acc["kemAlgorithm"] == "ML-KEM-768 (NIST FIPS 203)"
    assert acc["dsaAlgorithm"] == "ML-DSA-65 (NIST FIPS 204)"

    # List ports
    ports = api.listPorts()
    assert isinstance(ports, list)

    # Vault lock
    assert api.lockVault() is True
