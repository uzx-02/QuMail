# transport/oauth2_yahoo.py — Yahoo OAuth2 token acquisition and refresh.
# Single responsibility: obtain and refresh a valid Yahoo OAuth2 access token
# using the standard requests-based authorization code + PKCE flow.
# Yahoo does not have a first-party Python OAuth2 library — the flow is implemented
# directly using the `requests` library, which is already in requirements.txt.
# Token storage is handled by core/session.py — not here.
# This file handles only the authentication flow, not email sending or receiving.
# Do not import from crypto/, mime/, portal/, or certificates/.
# Do not store tokens in this file — pass them to core/session.py via the caller.

import base64
import hashlib
import json
import os
import stat
import secrets
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading   import Thread

import requests
from cryptography.fernet import Fernet, InvalidToken

from core.config import (
    YAHOO_CLIENT_ID,
    YAHOO_CLIENT_SECRET,
    YAHOO_REDIRECT_URI,
    YAHOO_TOKEN_PATH,
    YAHOO_AUTH_URL,
    YAHOO_TOKEN_URL,
    YAHOO_SCOPES,
)

_OAUTH_MASTER_KEY_PATH = "secrets/oauth_master.key"


# -------------------------------------------------------------------------
# Custom Exceptions
# -------------------------------------------------------------------------

class YahooAuthError(Exception):
    """Raised when Yahoo OAuth2 authentication or token refresh fails."""
    pass


# -------------------------------------------------------------------------
# PKCE helpers
# -------------------------------------------------------------------------

def _generate_pkce_pair() -> tuple[str, str]:
    """
    Generate a PKCE code_verifier and code_challenge pair.
    code_verifier: 128-char URL-safe random string (RFC 7636 §4.1)
    code_challenge: BASE64URL(SHA256(code_verifier)) (S256 method)

    Returns (code_verifier, code_challenge).
    """
    code_verifier  = secrets.token_urlsafe(96)   # 96 bytes → 128-char base64url string
    digest         = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


# -------------------------------------------------------------------------
# Token persistence
# -------------------------------------------------------------------------

def _load_token() -> dict | None:
    """
    Load cached Yahoo token data from disk.
    Returns a dict with keys: access_token, refresh_token, expires_at.
    Returns None if no token file exists.
    """
    if not os.path.exists(YAHOO_TOKEN_PATH):
        return None
    try:
        with open(YAHOO_TOKEN_PATH, "rb") as f:
            encrypted = f.read()
        return json.loads(_get_fernet().decrypt(encrypted).decode("utf-8"))
    except InvalidToken as exc:
        raise YahooAuthError("Stored Yahoo token cannot be decrypted.") from exc
    except Exception as exc:
        raise YahooAuthError(
            f"Failed to load Yahoo token from '{YAHOO_TOKEN_PATH}': {exc}"
        ) from exc


def _secure_file_permissions(path: str) -> None:
    """Best-effort hardening: owner read/write only on POSIX."""
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _ensure_secret_dir(path: str) -> None:
    """Create parent directory for token storage with restrictive permissions."""
    parent = os.path.dirname(path)
    if not parent:
        return
    os.makedirs(parent, exist_ok=True)
    try:
        os.chmod(parent, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    except OSError:
        pass


def _get_fernet() -> Fernet:
    """Return Fernet instance backed by a local master key file."""
    _ensure_secret_dir(_OAUTH_MASTER_KEY_PATH)
    if os.path.exists(_OAUTH_MASTER_KEY_PATH):
        with open(_OAUTH_MASTER_KEY_PATH, "rb") as f:
            key = f.read()
    else:
        key = Fernet.generate_key()
        with open(_OAUTH_MASTER_KEY_PATH, "wb") as f:
            f.write(key)
        _secure_file_permissions(_OAUTH_MASTER_KEY_PATH)
    return Fernet(key)


def _save_token(token_data: dict) -> None:
    """
    Persist Yahoo token data (access_token, refresh_token, expires_at) to disk.
    Called after every successful authorisation or refresh.
    """
    try:
        _ensure_secret_dir(YAHOO_TOKEN_PATH)
        encrypted = _get_fernet().encrypt(json.dumps(token_data).encode("utf-8"))
        with open(YAHOO_TOKEN_PATH, "wb") as f:
            f.write(encrypted)
        _secure_file_permissions(YAHOO_TOKEN_PATH)
    except Exception as exc:
        raise YahooAuthError(
            f"Failed to save Yahoo token to '{YAHOO_TOKEN_PATH}': {exc}"
        ) from exc


def _is_token_valid(token_data: dict) -> bool:
    """Return True if the access token has not expired (with a 60-second buffer)."""
    return token_data.get("expires_at", 0) > time.time() + 60


# -------------------------------------------------------------------------
# Browser consent flow (authorization code + PKCE)
# -------------------------------------------------------------------------

def _run_browser_flow(code_verifier: str, code_challenge: str) -> str:
    """
    Launch the Yahoo OAuth2 browser consent flow and capture the authorization code.

    Opens the Yahoo authorization URL in the default browser, then starts a temporary
    local HTTP server on the redirect URI port to capture the callback with the code.

    Returns the authorization code string.
    Raises YahooAuthError if the flow times out or the user denies access.
    """
    auth_code_holder: list[str] = []   # mutable container for inter-thread capture

    class _CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed   = urllib.parse.urlparse(self.path)
            params   = urllib.parse.parse_qs(parsed.query)
            if "code" in params:
                auth_code_holder.append(params["code"][0])
            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>QuMail: Yahoo authorisation complete. "
                b"You may close this window.</h2></body></html>"
            )

        def log_message(self, *args) -> None:
            pass   # Suppress default request logging to stdout

    # --- Parse redirect URI for local server port ---
    parsed_redirect = urllib.parse.urlparse(YAHOO_REDIRECT_URI)
    port            = parsed_redirect.port or 80

    server = HTTPServer(("localhost", port), _CallbackHandler)
    thread = Thread(target=server.handle_request, daemon=True)
    thread.start()

    # --- Build and open the authorization URL ---
    auth_params = {
        "client_id":             YAHOO_CLIENT_ID,
        "redirect_uri":          YAHOO_REDIRECT_URI,
        "response_type":         "code",
        "scope":                 " ".join(YAHOO_SCOPES),
        "code_challenge":        code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{YAHOO_AUTH_URL}?{urllib.parse.urlencode(auth_params)}"
    webbrowser.open(auth_url)

    thread.join(timeout=120)   # Wait up to 2 minutes for user to authorise
    server.server_close()

    if not auth_code_holder:
        raise YahooAuthError(
            "Yahoo OAuth2 flow timed out or was denied. "
            "No authorization code received within 120 seconds."
        )

    return auth_code_holder[0]


# -------------------------------------------------------------------------
# Token exchange and refresh
# -------------------------------------------------------------------------

def _exchange_code_for_token(auth_code: str, code_verifier: str) -> dict:
    """
    Exchange an authorization code for access and refresh tokens.
    Returns a dict with: access_token, refresh_token, expires_at.
    Raises YahooAuthError on failure.
    """
    try:
        resp = requests.post(
            YAHOO_TOKEN_URL,
            data={
                "grant_type":    "authorization_code",
                "client_id":     YAHOO_CLIENT_ID,
                "client_secret": YAHOO_CLIENT_SECRET,
                "redirect_uri":  YAHOO_REDIRECT_URI,
                "code":          auth_code,
                "code_verifier": code_verifier,
            },
            timeout=10,
        )
    except Exception as exc:
        raise YahooAuthError(f"Yahoo token exchange request failed: {exc}") from exc

    if resp.status_code != 200:
        raise YahooAuthError(
            f"Yahoo token exchange failed: {resp.status_code} — {resp.text}"
        )

    data = resp.json()
    return {
        "access_token":  data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expires_at":    time.time() + data.get("expires_in", 3600),
    }


def _refresh_access_token(refresh_token: str) -> dict:
    """
    Use the refresh token to obtain a new access token without user interaction.
    Returns an updated token dict with: access_token, refresh_token, expires_at.
    Raises YahooAuthError on failure.
    """
    try:
        resp = requests.post(
            YAHOO_TOKEN_URL,
            data={
                "grant_type":    "refresh_token",
                "client_id":     YAHOO_CLIENT_ID,
                "client_secret": YAHOO_CLIENT_SECRET,
                "redirect_uri":  YAHOO_REDIRECT_URI,
                "refresh_token": refresh_token,
            },
            timeout=10,
        )
    except Exception as exc:
        raise YahooAuthError(f"Yahoo token refresh request failed: {exc}") from exc

    if resp.status_code != 200:
        raise YahooAuthError(
            f"Yahoo token refresh failed: {resp.status_code} — {resp.text}"
        )

    data = resp.json()
    return {
        "access_token":  data["access_token"],
        "refresh_token": data.get("refresh_token", refresh_token),  # Yahoo may not rotate
        "expires_at":    time.time() + data.get("expires_in", 3600),
    }


# -------------------------------------------------------------------------
# Public interface
# -------------------------------------------------------------------------

def get_access_token() -> str:
    """
    Return a valid Yahoo OAuth2 access token, refreshing or re-authorising as needed.

    Flow:
      1. Load cached token data from YAHOO_TOKEN_PATH.
      2. If the token is valid and not expired — return the access token immediately.
      3. If the token is expired and a refresh token exists — refresh silently.
      4. If no token exists or refresh fails — launch the browser PKCE consent flow.
      5. Persist updated token data back to YAHOO_TOKEN_PATH.

    The access token is returned as a plain string. The caller (smtp_sender.py or
    imap_receiver.py) passes it to the SMTP/IMAP XOAUTH2 authentication call.
    Token storage beyond this call is the responsibility of core/session.py.

    Raises YahooAuthError on any unrecoverable authentication failure.
    """
    try:
        token_data = _load_token()

        # --- Valid cached token: return immediately ---
        if token_data and _is_token_valid(token_data):
            return token_data["access_token"]

        # --- Expired token with refresh token: refresh silently ---
        if token_data and token_data.get("refresh_token"):
            try:
                token_data = _refresh_access_token(token_data["refresh_token"])
                _save_token(token_data)
                return token_data["access_token"]
            except YahooAuthError:
                pass   # Refresh failed — fall through to full re-authorisation

        # --- No token or refresh failed: run browser consent flow ---
        code_verifier, code_challenge = _generate_pkce_pair()
        auth_code  = _run_browser_flow(code_verifier, code_challenge)
        token_data = _exchange_code_for_token(auth_code, code_verifier)
        _save_token(token_data)
        return token_data["access_token"]

    except YahooAuthError:
        raise
    except Exception as exc:
        raise YahooAuthError(
            f"Yahoo OAuth2 authentication failed: {exc}"
        ) from exc


def revoke_token() -> None:
    """
    Revoke the current Yahoo OAuth2 token and delete the local token file.
    Called by settings_window.py when the user disconnects their Yahoo account.
    After revocation, the next call to get_access_token() will trigger a full
    browser consent flow.

    Yahoo's token revocation endpoint accepts the access token directly.
    Does not raise if the token file does not exist — treats it as already revoked.
    """
    try:
        token_data = _load_token()
        if token_data and token_data.get("access_token"):
            # Best-effort server-side revocation — failure does not block local cleanup
            try:
                requests.post(
                    "https://api.login.yahoo.com/oauth2/revoke",
                    data={"token": token_data["access_token"]},
                    auth=(YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET),
                    timeout=5,
                )
            except Exception:
                pass   # Local cleanup proceeds regardless

        if os.path.exists(YAHOO_TOKEN_PATH):
            os.remove(YAHOO_TOKEN_PATH)

    except YahooAuthError:
        raise
    except Exception as exc:
        raise YahooAuthError(f"Yahoo token revocation failed: {exc}") from exc
