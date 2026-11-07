from unittest.mock import Mock, patch

import pytest
import main


def test_default_startup_does_not_start_simulator():
    with patch.object(main, "_launch_desktop", return_value=0) as launch, patch.object(main, "threading") as threading:
        assert main.main([]) == 0
    launch.assert_called_once()
    threading.Thread.assert_not_called()


def test_development_simulator_requires_explicit_switch():
    with patch.object(main, "_launch_desktop", return_value=0), patch.object(main, "threading") as threading:
        assert main.main(["--dev-simulator"]) == 0
    threading.Thread.assert_called_once_with(target=main._start_kme_server, daemon=True, name="qumail-dev-simulator")
    threading.Thread.return_value.start.assert_called_once()


def test_simulator_status_does_not_claim_real_qkd():
    from kme.virtual_node import app
    response = app.test_client().get("/api/v1/status")
    assert response.json["provenance"] == "simulated-csprng"
    assert response.json["production_ready"] is False
    assert "simulator" in response.json["node"].lower()


def test_dev_mailbox_defaults_to_submission_disabled():
    with patch.object(main, "_launch_mailbox", return_value=0) as launch_mailbox:
        assert main.main(["--dev-mailbox", "--dev-vault", "dummy.sqlite"]) == 0
    launch_mailbox.assert_called_once_with("dummy.sqlite", None)


def test_dev_mailbox_submission_requires_explicit_flag():
    with patch.object(main, "_launch_mailbox", return_value=0) as launch_mailbox:
        assert main.main(["--dev-mailbox", "--dev-vault", "dummy.sqlite", "--dev-gmail-submit"]) == 0
    launch_mailbox.assert_called_once_with("dummy.sqlite", None, True)


def test_dev_gmail_submit_requires_dev_mailbox():
    import pytest
    with pytest.raises(SystemExit):
        main.main(["--dev-gmail-submit"])
    with pytest.raises(SystemExit):
        main.main(["--dev-identity", "--dev-vault", "dummy.sqlite", "--dev-gmail-submit"])


def test_dev_modes_mutually_exclusive_with_simulator():
    import pytest
    with pytest.raises(SystemExit):
        main.main(["--dev-mailbox", "--dev-vault", "dummy.sqlite", "--dev-simulator"])
    with pytest.raises(SystemExit):
        main.main(["--dev-identity", "--dev-vault", "dummy.sqlite", "--dev-simulator"])


@pytest.fixture(scope="session")
def qt_app():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_dryrun_network_isolation_and_disabled_controls(qt_app, monkeypatch):
    import socket

    connections = []
    orig_connect = socket.socket.connect
    def mock_connect(self, *args, **kwargs):
        connections.append(args)
        return orig_connect(self, *args, **kwargs)
    monkeypatch.setattr(socket.socket, "connect", mock_connect)

    from core.account_session import DevelopmentSession
    from ui.mailbox_window import MailboxWindow

    mock_identity = Mock()
    mock_identity.session = DevelopmentSession()
    mock_identity.google = None

    window = MailboxWindow(mock_identity, gmail_enabled=False)
    try:
        window.show()
        qt_app.processEvents()
        assert len(connections) == 0
        assert not window.buttons["Refresh headers"].isEnabled()
        assert not window.actions.buttons["Submit once"].isEnabled()
        assert not window.settings.buttons["Connect Google"].isEnabled()
    finally:
        window.timer.stop()
        window.settings.timer.stop()
        window.actions.timer.stop()
        window.close()
        window.settings.close()
        window.actions.close()
        window.pool.shutdown(wait=True)
        window.settings.pool.shutdown(wait=True)
        qt_app.processEvents()


