"""Isolated prototype tests; a partial selection is never a release result."""
import os
from pathlib import Path
import random
import socket
import tempfile

import pytest


def pytest_addoption(parser):
    parser.addoption("--test-order", default="normal", help="normal, reverse or integer seed")


def pytest_sessionstart(session):
    # Must precede collection: virtual_node loads its relative registry on import.
    session._qumail_cwd = Path.cwd()
    session._qumail_tmp = tempfile.TemporaryDirectory(prefix="qumail-tests-")
    os.chdir(session._qumail_tmp.name)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def pytest_collection_modifyitems(config, items):
    order = config.getoption("--test-order")
    if order == "reverse":
        items.reverse()
    elif order != "normal":
        try:
            seed = int(order)
        except ValueError as exc:
            raise pytest.UsageError("--test-order requires normal, reverse or an integer") from exc
        random.Random(seed).shuffle(items)


def pytest_sessionfinish(session, exitstatus):
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter and any(reporter.stats.get(s) for s in ("skipped", "xfailed", "xpassed")):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        reporter.write_sep("!", "Unexpected skip/xfail: required validation is incomplete")
    os.chdir(session._qumail_cwd)
    session._qumail_tmp.cleanup()


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from kme import virtual_node as node
    from portal import portal_server as portal
    from core.session import session
    from kme.kme_client import kme_client

    monkeypatch.setattr(node, "_sae_registry", {})
    monkeypatch.setattr(node, "_issued_keys", {})
    monkeypatch.setattr(node, "_RATE_HISTORY", {})
    monkeypatch.setattr(node, "_REGISTRY_PATH", str(tmp_path / "secrets" / "registry.json"))
    # Fixed time prevents the rate-limit test depending on machine speed.
    monkeypatch.setattr(node, "time", type("Clock", (), {"time": staticmethod(lambda: 1000.0)}))
    monkeypatch.setattr(portal, "_memory_store", {})
    monkeypatch.setattr(portal, "_memory_rate_limits", {})
    monkeypatch.setattr(portal, "_firestore_client", None)
    monkeypatch.setattr(portal, "_firestore_available", False)
    monkeypatch.setattr(portal, "_PORTAL_MODE", "local")
    monkeypatch.setattr(portal, "_server_started", False)
    monkeypatch.setattr(kme_client, "base_url", "http://127.0.0.1:5000")
    session.reset()

    def no_network(*args, **kwargs):
        raise AssertionError("Tests must use injected transports, not real network connections")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    yield
    session.reset()
