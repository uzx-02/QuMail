"""Offline invariants for the desktop public-client Gmail OAuth transport."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import threading

from google.oauth2.credentials import Credentials


def _credentials(token: str) -> Credentials:
    return Credentials(
        token=token,
        refresh_token="test-refresh-token",
        client_id="desktop-client.apps.googleusercontent.com",
        token_uri="https://oauth2.googleapis.com/token",
    )


def test_pkce_s256_matches_rfc_7636_example():
    from transport.oauth2_gmail import pkce_s256_challenge

    assert pkce_s256_challenge(
        "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    ) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_desktop_client_config_does_not_require_client_secret():
    from core.config import validate_google_client_config

    valid, _message, config = validate_google_client_config({
        "installed": {"client_id": "desktop-client.apps.googleusercontent.com"}
    })
    assert valid is True
    assert config == {"client_id": "desktop-client.apps.googleusercontent.com"}


def test_bundled_oauth_config_is_used_when_no_user_override(tmp_path, monkeypatch):
    """A clean installation can authenticate without importing client JSON."""
    import core.config as config

    bundled = tmp_path / "resources"
    bundled.mkdir()
    (bundled / "google_oauth_client.json").write_text(
        '{"installed":{"client_id":"release-client.apps.googleusercontent.com"}}',
        encoding="utf-8",
    )
    user_config = tmp_path / "user-config"
    user_config.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "GMAIL_CLIENT_SECRETS_PATH", str(tmp_path / "missing.json"))
    monkeypatch.setattr(config, "get_user_config_dir", lambda: user_config)
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config.sys, "_MEIPASS", str(tmp_path), raising=False)

    loaded, source, error = config.load_google_client_config()

    assert error is None
    assert source == "bundled-release-resource"
    assert loaded and loaded["client_id"] == "release-client.apps.googleusercontent.com"


def test_per_account_token_records_do_not_fall_back_to_a_different_account():
    from transport.oauth2_gmail import _load_credentials, _save_credentials

    _save_credentials(_credentials("alpha-token"), {"email": "alpha@gmail.com"}, email="alpha@gmail.com")
    _save_credentials(_credentials("bravo-token"), {"email": "bravo@gmail.com"}, email="bravo@gmail.com")

    alpha, alpha_meta = _load_credentials("alpha@gmail.com")
    bravo, bravo_meta = _load_credentials("bravo@gmail.com")
    absent, absent_meta = _load_credentials("absent@gmail.com")

    assert alpha and alpha.token == "alpha-token"
    assert alpha_meta and alpha_meta["email"] == "alpha@gmail.com"
    assert bravo and bravo.token == "bravo-token"
    assert bravo_meta and bravo_meta["email"] == "bravo@gmail.com"
    assert absent is None
    assert absent_meta is None


def test_background_token_lookup_never_starts_interactive_authorization(monkeypatch):
    from transport.oauth2_gmail import GmailAuthError, get_access_token

    def unexpected_browser_flow(*_args, **_kwargs):
        raise AssertionError("background lookup must not invoke OAuth authorization")

    monkeypatch.setattr("transport.oauth2_gmail.authorize_google_account", unexpected_browser_flow)
    try:
        get_access_token("missing@gmail.com", interactive=False)
    except GmailAuthError as exc:
        assert exc.code == "AUTH_REQUIRED"
    else:
        raise AssertionError("missing credentials must require explicit reconnect")


def test_callback_wait_honours_cancellation_before_processing_requests():
    from transport.oauth2_gmail import GmailAuthError, _wait_for_callback

    cancelled = threading.Event()
    cancelled.set()
    server = SimpleNamespace(complete=threading.Event(), timeout=0, handle_request=lambda: None)
    try:
        _wait_for_callback(server, 1, cancelled)
    except GmailAuthError as exc:
        assert exc.code == "CALLBACK_CANCELLED"
    else:
        raise AssertionError("cancelled OAuth callback must not remain pending")


def test_public_client_refresh_does_not_require_or_send_a_client_secret(monkeypatch):
    from transport.oauth2_gmail import _save_credentials, get_access_token

    credential = _credentials("expired-token")
    credential.expiry = datetime.now(timezone.utc) - timedelta(minutes=5)
    _save_credentials(credential, {"email": "refresh@gmail.com"}, email="refresh@gmail.com")
    observed = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"access_token": "refreshed-token", "expires_in": 3600}

    def post(*args, **kwargs):
        observed["url"] = args[0]
        observed.update(kwargs)
        return Response()

    monkeypatch.setattr("requests.post", post)
    access_token = get_access_token("refresh@gmail.com", interactive=False)

    assert access_token == "refreshed-token"
    assert "client_secret" not in observed["data"]


def test_public_client_authorization_exchange_omits_client_secret(monkeypatch):
    """The InstalledAppFlow convenience method requires a secret in some releases."""
    from transport.oauth2_gmail import authorize_google_account

    observed = {}
    credentials = Credentials(
        token="access-token",
        refresh_token="refresh-token",
        client_id="desktop-client.apps.googleusercontent.com",
        id_token="verified-id-token",
    )

    class OAuthSession:
        token = {"id_token": "verified-id-token"}

        def fetch_token(self, *args, **kwargs):
            observed["args"] = args
            observed["kwargs"] = kwargs
            self.token = {"id_token": "verified-id-token"}

        def close(self):
            return None

    class Flow:
        def __init__(self):
            self.redirect_uri = ""
            self.code_verifier = ""
            self.oauth2session = OAuthSession()
            self.credentials = credentials

        def authorization_url(self, **_kwargs):
            return "https://accounts.example.test/authorize", "state-value"

    class Server:
        server_port = 43123

        def __init__(self, *_args, **_kwargs):
            pass

        def server_close(self):
            return None

    identity = SimpleNamespace(
        addresses=[SimpleNamespace(value="account@example.test")],
        subject="google-subject",
        issuer="https://accounts.google.com",
    )
    monkeypatch.setattr(
        "transport.oauth2_gmail._load_client_config",
        lambda: {"installed": {
            "client_id": "desktop-client.apps.googleusercontent.com",
            "token_uri": "https://oauth2.googleapis.com/token",
        }},
    )
    monkeypatch.setattr(
        "transport.oauth2_gmail.InstalledAppFlow.from_client_config",
        lambda *_args, **_kwargs: Flow(),
    )
    monkeypatch.setattr("transport.oauth2_gmail._OAuthCallbackServer", Server)
    monkeypatch.setattr("transport.oauth2_gmail._wait_for_callback", lambda *_args, **_kwargs: "auth-code")
    monkeypatch.setattr("transport.oauth2_gmail.webbrowser.open", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("transport.oauth2_gmail._profile_metadata", lambda *_args, **_kwargs: ("", ""))
    monkeypatch.setattr("transport.oauth2_gmail._save_credentials", lambda *_args, **_kwargs: None)
    def verify_identity(*_args, **kwargs):
        observed["identity_kwargs"] = kwargs
        return identity

    monkeypatch.setattr("core.vault.identity.google_identity", verify_identity)
    monkeypatch.setattr("transport.oauth2_gmail.secrets.token_urlsafe", lambda *_args, **_kwargs: "state-value")

    authorize_google_account()

    assert observed["args"] == ("https://oauth2.googleapis.com/token",)
    assert observed["kwargs"]["code"] == "auth-code"
    assert observed["kwargs"]["include_client_id"] is True
    assert observed["kwargs"]["client_id"] == "desktop-client.apps.googleusercontent.com"
    assert "client_secret" not in observed["kwargs"]
    assert observed["identity_kwargs"]["wait_seconds"] == 20


def test_authorization_uses_optional_local_secret_but_does_not_persist_it(monkeypatch):
    """Google registrations that require a desktop secret keep it local-only."""
    from transport.oauth2_gmail import authorize_google_account

    observed = {}
    credentials = Credentials(
        token="access-token",
        refresh_token="refresh-token",
        client_id="desktop-client.apps.googleusercontent.com",
        client_secret="local-only-secret",
        id_token="verified-id-token",
    )

    class OAuthSession:
        token = {"id_token": "verified-id-token"}

        def close(self):
            return None

    class Flow:
        def __init__(self):
            self.redirect_uri = ""
            self.code_verifier = ""
            self.oauth2session = OAuthSession()
            self.credentials = credentials

        def authorization_url(self, **_kwargs):
            return "https://accounts.example.test/authorize", "state-value"

        def fetch_token(self, **kwargs):
            observed["fetch_kwargs"] = kwargs

    class Server:
        server_port = 43123

        def __init__(self, *_args, **_kwargs):
            pass

        def server_close(self):
            return None

    identity = SimpleNamespace(
        addresses=[SimpleNamespace(value="account@example.test")],
        subject="google-subject",
        issuer="https://accounts.google.com",
    )
    saved = {}
    monkeypatch.setattr(
        "transport.oauth2_gmail._load_client_config",
        lambda: {"installed": {
            "client_id": "desktop-client.apps.googleusercontent.com",
            "client_secret": "local-only-secret",
            "token_uri": "https://oauth2.googleapis.com/token",
        }},
    )
    monkeypatch.setattr(
        "transport.oauth2_gmail.InstalledAppFlow.from_client_config",
        lambda *_args, **_kwargs: Flow(),
    )
    monkeypatch.setattr("transport.oauth2_gmail._OAuthCallbackServer", Server)
    monkeypatch.setattr("transport.oauth2_gmail._wait_for_callback", lambda *_args, **_kwargs: "auth-code")
    monkeypatch.setattr("transport.oauth2_gmail.webbrowser.open", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("transport.oauth2_gmail._profile_metadata", lambda *_args, **_kwargs: ("", ""))
    monkeypatch.setattr("transport.oauth2_gmail._save_credentials", lambda creds, *_args, **_kwargs: saved.setdefault("creds", creds))
    monkeypatch.setattr("core.vault.identity.google_identity", lambda *_args, **_kwargs: identity)
    monkeypatch.setattr("transport.oauth2_gmail.secrets.token_urlsafe", lambda *_args, **_kwargs: "state-value")

    authorize_google_account()

    assert observed["fetch_kwargs"]["code"] == "auth-code"
    assert saved["creds"].client_secret is None


def test_refresh_optionally_sends_configured_desktop_secret(monkeypatch):
    from transport.oauth2_gmail import _refresh_public_client_credentials

    credential = _credentials("expired-token")
    observed = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"access_token": "refreshed-token", "expires_in": 3600}

    def post(*args, **kwargs):
        observed["url"] = args[0]
        observed.update(kwargs)
        return Response()

    monkeypatch.setattr("requests.post", post)
    _refresh_public_client_credentials(credential, "local-only-secret")

    assert observed["data"]["client_secret"] == "local-only-secret"
    assert credential.client_secret is None
