"""Offline integration tests for OAuth boundaries and account-owned credentials."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import threading
import time

import pytest
from google.oauth2.credentials import Credentials


def _claims(**changes):
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "desktop-client",
        "azp": "desktop-client",
        "sub": "google-subject",
        "email": "owner@gmail.com",
        "email_verified": True,
        "nonce": "n" * 32,
        "exp": int(time.time()) + 3600,
    }
    claims.update(changes)
    return claims


@pytest.mark.parametrize(
    ("changes", "expected_code"),
    [
        ({"aud": "wrong-client"}, "google_token_audience_mismatch"),
        ({"nonce": "x" * 32}, "google_token_nonce_mismatch"),
        ({"iss": "https://not-google.example"}, "google_token_authority_or_claims_invalid"),
        ({"exp": int(time.time()) - 1}, "google_token_authority_or_claims_invalid"),
        ({"sub": ""}, "google_token_authority_or_claims_invalid"),
        ({"email_verified": False}, "google_token_authority_or_claims_invalid"),
    ],
)
def test_verified_google_claim_validation_rejects_security_failures(changes, expected_code):
    """The post-signature boundary must reject malformed or mismatched claims."""
    from core.vault.identity import validated_google_claims
    from core.vault.types import BoundaryError

    with pytest.raises(BoundaryError) as raised:
        validated_google_claims(_claims(**changes), "desktop-client", "n" * 32)
    assert raised.value.code.value == expected_code


def _callback_handler(server, path, host):
    """Call the handler without a network socket or browser."""
    from transport.oauth2_gmail import _OAuthCallbackHandler

    handler = object.__new__(_OAuthCallbackHandler)
    handler.server = server
    handler.path = path
    handler.headers = {"Host": host}
    responses = []
    handler._reply = lambda status, _html: responses.append(status)
    handler.do_GET()
    return responses


def test_loopback_callback_rejects_wrong_state_and_replay_without_network():
    """Only the first callback with the exact state may supply an auth code."""
    from transport.oauth2_gmail import _OAuthCallbackServer

    expected_state = "state-" + "s" * 40
    server = SimpleNamespace(
        server_port=43123,
        expected_state=expected_state,
        authorization_code=None,
        error=None,
        complete=threading.Event(),
    )
    host = "127.0.0.1:43123"

    assert _callback_handler(server, "/callback?code=first&state=" + expected_state, host) == [200]
    assert server.authorization_code == "first"

    # A second otherwise-valid callback cannot replace the original code.
    assert _callback_handler(server, "/callback?code=second&state=" + expected_state, host) == [400]
    assert server.authorization_code == "first"
    assert server.error == "OAuth callback was invalid or replayed."

    rejected = SimpleNamespace(
        server_port=43124,
        expected_state=expected_state,
        authorization_code=None,
        error=None,
        complete=threading.Event(),
    )
    assert _callback_handler(rejected, "/callback?code=code&state=attacker", "127.0.0.1:43124") == [400]
    assert rejected.authorization_code is None
    assert rejected.complete.is_set()


def _expired_credentials(token: str = "old-token") -> Credentials:
    return Credentials(
        token=token,
        refresh_token="fixture-refresh-token",
        client_id="desktop-client.apps.googleusercontent.com",
        expiry=datetime.now(timezone.utc) - timedelta(minutes=5),
    )


def test_parallel_refresh_for_one_account_is_serialized(monkeypatch):
    """Two transport operations share one account lock and issue only one refresh."""
    from transport.oauth2_gmail import _save_credentials, get_access_token

    _save_credentials(
        _expired_credentials(),
        {
            "email": "parallel@gmail.com",
            "id_token": "fixture-id-token",
            "directory_session_token": "owned-directory-session",
        },
        email="parallel@gmail.com",
    )
    calls = []
    calls_lock = threading.Lock()

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"access_token": "fresh-token", "expires_in": 3600}

    def post(*_args, **_kwargs):
        with calls_lock:
            calls.append(1)
        time.sleep(0.05)
        return Response()

    monkeypatch.setattr("requests.post", post)
    results = []
    workers = [threading.Thread(target=lambda: results.append(get_access_token("parallel@gmail.com", interactive=False))) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert results == ["fresh-token", "fresh-token"]
    assert len(calls) == 1
    from transport.oauth2_gmail import _load_credentials
    refreshed, metadata = _load_credentials("parallel@gmail.com")
    assert refreshed and refreshed.token == "fresh-token" and refreshed.valid
    assert metadata and metadata["id_token"] == "fixture-id-token"
    assert metadata["directory_session_token"] == "owned-directory-session"


def test_failed_atomic_credential_replacement_preserves_previous_record(monkeypatch):
    """A refresh/write failure cannot overwrite a readable credential record."""
    import transport.oauth2_gmail as oauth

    original = Credentials(token="original-token", refresh_token="fixture-refresh", client_id="desktop-client")
    oauth._save_credentials(original, {"email": "atomic@gmail.com"}, email="atomic@gmail.com")

    def fail_replace(*_args, **_kwargs):
        raise OSError("simulated interrupted replacement")

    monkeypatch.setattr(oauth.os, "replace", fail_replace)
    replacement = Credentials(token="replacement-token", refresh_token="fixture-refresh", client_id="desktop-client")
    with pytest.raises(OSError, match="interrupted replacement"):
        oauth._save_credentials(replacement, {"email": "atomic@gmail.com"}, email="atomic@gmail.com")

    loaded, metadata = oauth._load_credentials("atomic@gmail.com")
    assert loaded and loaded.token == "original-token"
    assert metadata and metadata["email"] == "atomic@gmail.com"
