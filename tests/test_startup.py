from pathlib import Path
from unittest.mock import Mock, patch
import pytest

import main
from core.provider_resolver import ProviderNotFoundError


def test_default_startup_routes_to_modern_mailbox():
    """Default startup (python main.py with no args) MUST route to modern mailbox, NEVER legacy simulator."""
    with patch.object(main, "_launch_mailbox", return_value=0) as launch_mailbox, \
         patch.object(main, "_launch_desktop") as launch_desktop, \
         patch.object(main, "threading") as threading:
        assert main.main([]) == 0
    launch_mailbox.assert_called_once()
    launch_desktop.assert_not_called()
    threading.Thread.assert_not_called()


def test_legacy_simulator_requires_explicit_flag():
    """Legacy research simulator requires explicit --legacy-simulator or --dev-simulator flag."""
    with patch.object(main, "_launch_desktop", return_value=0) as launch_desktop, \
         patch.object(main, "_launch_mailbox") as launch_mailbox, \
         patch.object(main, "threading") as threading:
        assert main.main(["--legacy-simulator"]) == 0
    launch_desktop.assert_called_once()
    launch_mailbox.assert_not_called()
    threading.Thread.assert_called_once_with(target=main._start_kme_server, daemon=True, name="qumail-dev-simulator")


def test_dev_simulator_backwards_compatible_alias():
    """--dev-simulator continues to work as an alias for --legacy-simulator."""
    with patch.object(main, "_launch_desktop", return_value=0) as launch_desktop, \
         patch.object(main, "threading") as threading:
        assert main.main(["--dev-simulator"]) == 0
    launch_desktop.assert_called_once()
    threading.Thread.assert_called_once_with(target=main._start_kme_server, daemon=True, name="qumail-dev-simulator")


def test_simulator_status_does_not_claim_real_qkd():
    from kme.virtual_node import app
    response = app.test_client().get("/api/v1/status")
    assert response.json["provenance"] == "simulated-csprng"
    assert response.json["production_ready"] is False
    assert "simulator" in response.json["node"].lower()


def test_dev_mailbox_defaults_to_submission_disabled():
    with patch.object(main, "_launch_mailbox", return_value=0) as launch_mailbox:
        assert main.main(["--dev-mailbox", "--dev-vault", "dummy.sqlite"]) == 0
    launch_mailbox.assert_called_once_with("dummy.sqlite", None, gmail_enabled=False)


def test_dev_mailbox_submission_requires_explicit_flag():
    with patch.object(main, "_launch_mailbox", return_value=0) as launch_mailbox:
        assert main.main(["--dev-mailbox", "--dev-vault", "dummy.sqlite", "--dev-gmail-submit"]) == 0
    launch_mailbox.assert_called_once_with("dummy.sqlite", None, gmail_enabled=True)


def test_submit_alias_enables_submission():
    with patch.object(main, "_launch_mailbox", return_value=0) as launch_mailbox:
        assert main.main(["--vault", "dummy.sqlite", "--submit"]) == 0
    launch_mailbox.assert_called_once_with("dummy.sqlite", None, gmail_enabled=True)


def test_check_provider_flag_exits_zero():
    with patch.object(main, "verify_provider", return_value={
        "path": "bin/qumail-m5-provider.exe",
        "size_bytes": 1000000,
        "sha256": "abcdef",
        "pe_mitigations": {
            "high_entropy_va_64bit_aslr": True,
            "dynamic_base_aslr": True,
            "nx_compat_dep": True,
            "guard_cf_control_flow_guard": True,
        },
        "manifest_match": True,
    }):
        assert main.main(["--check-provider"]) == 0


def test_missing_provider_fails_safely_without_fallback():
    """If native provider is missing, application exits with error code and NEVER falls back to simulator."""
    with patch.object(main, "resolve_provider", side_effect=ProviderNotFoundError("Not found")), \
         patch.object(main, "_launch_desktop") as launch_desktop, \
         patch.object(main, "_show_critical_error") as mock_err:
        ret = main._launch_mailbox("dummy.sqlite")
        assert ret == 1
        launch_desktop.assert_not_called()
        mock_err.assert_called_once()


def test_legacy_modes_mutually_exclusive_with_modern_modes():
    with pytest.raises(SystemExit):
        main.main(["--legacy-simulator", "--vault", "dummy.sqlite"])
    with pytest.raises(SystemExit):
        main.main(["--dev-simulator", "--dev-mailbox"])
    with pytest.raises(SystemExit):
        main.main(["--dev-identity", "--dev-simulator"])


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
