"""The research binding must never install native code during an operation."""
import ast
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from crypto import legacy_provider


def test_original_pin_reports_blocker_without_loading_research(monkeypatch, capsys):
    loader = Mock(side_effect=AssertionError("research must be explicit"))
    monkeypatch.setattr(legacy_provider, "load_oqs", loader)
    assert legacy_provider.main([]) == 1
    assert '"original_binding": "0.14.1"' in capsys.readouterr().out
    loader.assert_not_called()


def test_research_report_exposes_unavailability(monkeypatch, capsys):
    monkeypatch.setattr(legacy_provider, "load_oqs", Mock(side_effect=legacy_provider.LegacyProviderUnavailable("fixture unavailable")))
    assert legacy_provider.main(["--research"]) == 1
    assert '"research_status": "unavailable"' in capsys.readouterr().out


def test_missing_native_configuration_fails_before_import(monkeypatch):
    monkeypatch.setattr(legacy_provider, "_provider", None)
    monkeypatch.delenv("OQS_INSTALL_PATH", raising=False)
    distribution = Mock(version=legacy_provider.BINDING_VERSION)
    # Use a fixture source, with a matching test digest, to reach the native guard.
    source = Path("oqs.py")
    source.write_text("# fixture", encoding="utf-8")
    distribution.locate_file.return_value = source
    monkeypatch.setattr(legacy_provider.metadata, "distribution", lambda _: distribution)
    monkeypatch.setattr(legacy_provider, "BINDING_SOURCE_SHA256", legacy_provider.hashlib.sha256(source.read_bytes()).hexdigest())
    importer = Mock(side_effect=AssertionError("must not import native wrapper"))
    monkeypatch.setattr(legacy_provider.importlib, "import_module", importer)
    with pytest.raises(legacy_provider.LegacyProviderUnavailable, match="OQS_INSTALL_PATH"):
        legacy_provider.load_oqs()
    importer.assert_not_called()


def test_wrong_binding_version_fails_before_import(monkeypatch):
    monkeypatch.setattr(legacy_provider, "_provider", None)
    monkeypatch.setattr(legacy_provider.metadata, "distribution", lambda _: Mock(version="0.0.0"))
    with pytest.raises(legacy_provider.LegacyProviderUnavailable, match="binding version"):
        legacy_provider.load_oqs()


@pytest.mark.native_crypto
def test_reviewed_binding_rejects_install_sentinel_before_any_side_effect():
    # Execute only the reviewed upstream installer function, never import oqs.
    distribution = legacy_provider.metadata.distribution("liboqs-python")
    source = Path(distribution.locate_file("oqs/oqs.py")).read_bytes()
    assert legacy_provider.hashlib.sha256(source).hexdigest() == legacy_provider.BINDING_SOURCE_SHA256
    tree = ast.parse(source)
    selected = [node for node in tree.body if
                isinstance(node, ast.FunctionDef) and node.name == "_install_liboqs"
                or isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_LIBOQS_VERSION_RE" for t in node.targets)]
    import re
    from typing import Union
    forbidden = Mock(side_effect=AssertionError("runtime native installation attempted"))
    namespace = {"re": re, "Path": Path, "Union": Union, "tempfile": forbidden, "subprocess": forbidden}
    exec(compile(ast.Module(body=selected, type_ignores=[]), "reviewed-oqs-installer", "exec"), namespace)
    with pytest.raises(ValueError, match="Cannot install liboqs version"):
        namespace["_install_liboqs"](Path.cwd(), legacy_provider._NO_INSTALL)
    assert not forbidden.mock_calls
