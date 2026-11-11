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
    session._qumail_cwd = Path.cwd()
    session._qumail_tmp = tempfile.TemporaryDirectory(prefix="qumail-tests-")
    os.chdir(session._qumail_tmp.name)


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
    data_dir = tmp_path / ".qumail_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("QUMAIL_DATA_DIR", str(data_dir))
    from core.session import session

    session.reset()

    def no_network(*args, **kwargs):
        raise AssertionError("Tests must use injected transports, not real network connections")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)

    from core.vault.secure_store import WindowsCredentialStore
    from core.vault.types import BoundaryError
    test_cred_store = {}
    orig_put = WindowsCredentialStore.put
    orig_get = WindowsCredentialStore.get
    orig_delete = WindowsCredentialStore.delete

    def safe_put(self, ident: str, secret: bytes):
        try:
            return orig_put(self, ident, secret)
        except BoundaryError:
            test_cred_store[self.target(ident)] = bytes(secret)

    def safe_get(self, ident: str) -> bytes:
        target = self.target(ident)
        if target in test_cred_store:
            return test_cred_store[target]
        return orig_get(self, ident)

    def safe_delete(self, ident: str):
        test_cred_store.pop(self.target(ident), None)
        try:
            orig_delete(self, ident)
        except Exception:
            pass

    monkeypatch.setattr(WindowsCredentialStore, "put", safe_put)
    monkeypatch.setattr(WindowsCredentialStore, "get", safe_get)
    monkeypatch.setattr(WindowsCredentialStore, "delete", safe_delete)

    yield
    session.reset()
