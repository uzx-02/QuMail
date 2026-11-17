from pathlib import Path
from unittest.mock import Mock, patch
import pytest

import main
from core.provider_resolver import ProviderNotFoundError


def test_default_startup_routes_to_react_desktop():
    """Default startup (python main.py with no args) MUST route to the modern React desktop launcher."""
    with patch.object(main, "_launch_react_desktop", return_value=0) as launch_react:
        assert main.main([]) == 0
    launch_react.assert_called_once()


def test_dev_mode_flag_passes_to_launcher():
    """--dev flag passes dev_mode=True to the React desktop launcher."""
    with patch.object(main, "_launch_react_desktop", return_value=0) as launch_react:
        assert main.main(["--dev"]) == 0
    launch_react.assert_called_once()
    assert launch_react.call_args.kwargs["dev_mode"] is True


def test_custom_vault_flag_passes_to_launcher():
    """--vault passes explicit SQLite vault path to the React desktop launcher."""
    with patch.object(main, "_launch_react_desktop", return_value=0) as launch_react:
        assert main.main(["--vault", "custom_vault.sqlite"]) == 0
    launch_react.assert_called_once()
    assert launch_react.call_args.kwargs["vault"] == "custom_vault.sqlite"


def test_check_provider_flag_exits_zero():
    """--check-provider probe verifies native binaries and exits zero."""
    with patch.object(main, "verify_provider", return_value={
        "path": "bin/qumail-crypto-provider.exe",
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


def test_missing_provider_fails_safely():
    """If native provider is missing, application logs critical error and returns 1."""
    with patch.object(main, "resolve_provider", side_effect=ProviderNotFoundError("Not found")), \
         patch.object(main, "_show_critical_error") as mock_err:
        ret = main._launch_react_desktop()
        assert ret == 1
        mock_err.assert_called_once()
