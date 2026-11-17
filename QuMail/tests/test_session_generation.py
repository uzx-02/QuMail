"""Session-generation fences for asynchronous account-owned bridge work."""

import sys
import threading
import types
import time


def _bridge_class(monkeypatch):
    # The test exercises pure bridge methods and does not create a WebView.
    monkeypatch.setitem(sys.modules, "webview", types.ModuleType("webview"))
    from launch_react_desktop import QuMailJsApi
    return QuMailJsApi


def test_stale_inbox_result_cannot_overwrite_new_active_account(monkeypatch):
    QuMailJsApi = _bridge_class(monkeypatch)
    api = object.__new__(QuMailJsApi)
    api._session_lock = threading.RLock()
    api._session_generation = 4
    api.account_email = "alpha@gmail.com"
    api.vault_state = "UNLOCKED"
    api.session_state = "MAILBOX_READY"
    api._staged_lock = threading.Lock()
    api._staged_raw_inbox = []
    api._inbox_lock = threading.RLock()
    api.messages = [{"id": "bravo-cache"}]
    api.connection_status = "ONLINE"
    api.last_sync_error = None

    def delayed_fetch(_email, max_count):
        api._advance_session_generation()
        api.account_email = "bravo@gmail.com"
        return [object()]

    monkeypatch.setattr("transport.imap_receiver.fetch_inbox", delayed_fetch)
    api._process_inbox_items = lambda _items: (_ for _ in ()).throw(AssertionError("stale results must not be processed"))

    assert api.fetchInbox() == [{"id": "bravo-cache"}]
    assert api.account_email == "bravo@gmail.com"


def test_verified_google_binding_claims_legacy_row_without_regenerating_keys(tmp_path, monkeypatch):
    QuMailJsApi = _bridge_class(monkeypatch)
    from core.vault.identity import validated_google_claims

    api = QuMailJsApi(account_email="legacy@gmail.com", vault_path=tmp_path / "legacy.sqlite")
    # Directory registration is a separate later-stage integration concern;
    # this test must prove local migration without any external call.
    api._register_pq_key_to_directory = lambda *_args, **_kwargs: None
    assert api._ensure_account_session("legacy@gmail.com") is True
    old_context = api.active_context
    old_handle = api.active_key_handle
    old_root = api.key_fingerprint

    identity = validated_google_claims(
        {
            "iss": "https://accounts.google.com",
            "aud": "test-desktop-client",
            "azp": "test-desktop-client",
            "sub": "stable-google-subject",
            "email": "legacy@gmail.com",
            "email_verified": True,
            "nonce": "n" * 32,
            "exp": int(time.time()) + 3600,
        },
        "test-desktop-client",
        "n" * 32,
    )

    assert api._ensure_account_session("legacy@gmail.com", identity=identity) is True
    assert api.active_context.account == old_context.account
    assert api.active_context.device == old_context.device
    assert api.active_context.subject == "stable-google-subject"
    assert api.active_key_handle == old_handle
    assert api.key_fingerprint == old_root
    assert len(api.vault_service.vault.summaries()) == 1
