"""Unverified metadata must not be presented as cryptographic assurance."""
from unittest.mock import patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_unverified_inbox_metadata_shows_legacy_status(qt_app):
    from ui.inbox_view import InboxView, _DisplayMessage
    view = InboxView()
    message = _DisplayMessage(uid="1", subject="s", sender="forged@example.invalid", date="d",
                              is_qumail=True, decrypted_body=None, tqr_level=3,
                              error_notice="Decryption failed")
    view._on_message_loaded(message)
    assert "identity unverified" in view._reader_badge.text()
    assert "Decryption failed" == view._reader_body.text()
    view.close()


def test_simulator_http_success_is_not_a_qkd_badge(qt_app):
    from ui.key_status_widget import KeyStatusWidget
    with patch("ui.key_status_widget.kme_client.is_online", return_value=True):
        widget = KeyStatusWidget()
    assert "simulator" in widget._network_pill.text()
    assert "no real QKD" in widget._network_pill.text()
    widget._timer.stop()
    widget.close()
