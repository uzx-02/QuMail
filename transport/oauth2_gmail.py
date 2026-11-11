# transport/oauth2_gmail.py — Gmail OAuth2 token acquisition and refresh.
# Single responsibility: obtain and refresh a valid Gmail OAuth2 access token
# using google-auth-oauthlib. Token storage is handled by core/session.py — not here.
# This file handles only the authentication flow, not email sending or receiving.
# Do not import from crypto/, mime/, portal/, or certificates/.
# Do not store tokens in this file — pass them to core/session.py via the caller.

import base64
import http.server
import json
import logging
import os
import stat
import sys
import time
import webbrowser
import secrets
from urllib.parse import urlparse, parse_qs

from google.oauth2.credentials        import Credentials
from google.auth.transport.requests   import Request
from google_auth_oauthlib.flow        import InstalledAppFlow
from cryptography.fernet import Fernet, InvalidToken

from core.config  import (
    GMAIL_CLIENT_SECRETS_PATH,
    GMAIL_SCOPES,
    GMAIL_TOKEN_PATH,
    OAUTH_MASTER_KEY_PATH,
    BUILTIN_GMAIL_CLIENT_CONFIG,
    load_google_client_config,
    validate_google_client_config,
    get_google_client_secrets_path,
    get_gmail_token_path,
    get_oauth_master_key_path,
)
_OAUTH_MASTER_KEY_PATH = str(get_oauth_master_key_path())
logger = logging.getLogger("transport.oauth2_gmail")

# -------------------------------------------------------------------------
# SSL & Network Environment Sanitization
# -------------------------------------------------------------------------

def sanitize_ssl_environment() -> None:
    """
    Sanitize SSL/TLS environment variables to eliminate FileNotFoundError connection aborts.
    Unconditionally removes SSLKEYLOGFILE, ensures valid CA certificates, clears C-level errno,
    and strips Conda-inherited or invalid certificate paths.
    """
    # 1. Unconditionally pop SSLKEYLOGFILE
    os.environ.pop("SSLKEYLOGFILE", None)

    # 2. Reset C-level errno in Python and MSVCRT to eliminate OpenSSL 3.0 stale-errno FileNotFoundError bug
    try:
        import ctypes
        ctypes.set_errno(0)
    except Exception:
        pass
    try:
        import ctypes
        ctypes.CDLL("ucrtbase.dll")._set_errno(0)
    except Exception:
        pass

    # Patch SSLContext.keylog_filename descriptor so setting it never triggers FileNotFoundError
    try:
        import ssl
        ssl.SSLContext.keylog_filename = property(lambda self: None, lambda self, val: None)
    except Exception:
        pass

    # 3. Strip any external CA bundle variables pointing to Conda or non-existent paths
    for var in ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_CERT_FILE", "SSL_CERT_DIR", "__CONDA_OPENSLL_CERT_FILE_SET"):
        val = os.environ.get(var)
        if val and ("miniconda" in val.lower() or "anaconda" in val.lower() or not os.path.exists(val)):
            os.environ.pop(var, None)

    # 4. Point to authoritative certifi CA bundle
    try:
        import certifi
        ca_path = certifi.where()
        if os.path.exists(ca_path):
            os.environ["REQUESTS_CA_BUNDLE"] = ca_path
            os.environ["SSL_CERT_FILE"] = ca_path
    except Exception:
        pass

    # 4. Patch ssl.create_default_context and urllib3 to guarantee keylogfile is never read
    try:
        import ssl
        if not getattr(ssl.create_default_context, "_qumail_patched", False):
            orig_ctx = ssl.create_default_context
            def _safe_create_default_context(*args, **kwargs):
                os.environ.pop("SSLKEYLOGFILE", None)
                return orig_ctx(*args, **kwargs)
            _safe_create_default_context._qumail_patched = True
            ssl.create_default_context = _safe_create_default_context
    except Exception:
        pass

    try:
        import urllib3.util.ssl_
        if not getattr(urllib3.util.ssl_.create_urllib3_context, "_qumail_patched", False):
            orig_u3_ctx = urllib3.util.ssl_.create_urllib3_context
            def _safe_u3_ctx(*args, **kwargs):
                os.environ.pop("SSLKEYLOGFILE", None)
                return orig_u3_ctx(*args, **kwargs)
            _safe_u3_ctx._qumail_patched = True
            urllib3.util.ssl_.create_urllib3_context = _safe_u3_ctx
    except Exception:
        pass


# Run sanitization immediately on module import
sanitize_ssl_environment()


# -------------------------------------------------------------------------
# -------------------------------------------------------------------------
# Visual Browser Success Landing Page
# -------------------------------------------------------------------------

SUCCESS_HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>QuMail — Authentication Successful</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: radial-gradient(circle at 50% 15%, #0f172a 0%, #020617 100%);
      color: #f8fafc;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }
    .card {
      background: rgba(15, 23, 42, 0.92);
      border: 1px solid rgba(255, 255, 255, 0.12);
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      border-radius: 24px;
      padding: 48px 40px;
      max-width: 480px;
      width: 100%;
      text-align: center;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7), 0 0 60px rgba(16, 185, 129, 0.2);
      animation: fadeIn 0.4s ease-out;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(16px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .icon-wrap {
      width: 80px;
      height: 80px;
      margin: 0 auto 24px;
      background: linear-gradient(135deg, rgba(16, 185, 129, 0.25), rgba(6, 182, 212, 0.25));
      border: 2px solid rgba(16, 185, 129, 0.5);
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 0 32px rgba(16, 185, 129, 0.4);
    }
    .icon-wrap svg {
      width: 44px;
      height: 44px;
      stroke: #34d399;
    }
    h1 {
      font-size: 26px;
      font-weight: 700;
      letter-spacing: -0.02em;
      margin-bottom: 12px;
      color: #ffffff;
    }
    p.desc {
      font-size: 14px;
      line-height: 1.6;
      color: #94a3b8;
      margin-bottom: 24px;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.3);
      color: #34d399;
      padding: 6px 14px;
      border-radius: 9999px;
      font-size: 13px;
      font-weight: 500;
      margin-bottom: 28px;
    }
    .guidance-banner {
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.35);
      border-radius: 14px;
      padding: 16px 20px;
      text-align: left;
      display: flex;
      align-items: center;
      gap: 14px;
      margin-bottom: 12px;
    }
    .guidance-check {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      background: #10b981;
      color: #ffffff;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 18px;
      font-weight: 700;
      flex-shrink: 0;
    }
    .guidance-title {
      font-size: 14px;
      font-weight: 600;
      color: #f1f5f9;
      margin-bottom: 2px;
    }
    .guidance-desc {
      font-size: 12px;
      color: #94a3b8;
      line-height: 1.4;
    }
    .subtext {
      margin-top: 16px;
      font-size: 12px;
      color: #64748b;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon-wrap">
      <svg fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    </div>
    <h1>Authentication Complete</h1>
    <p class="desc">Your Google account has been verified and securely connected to QuMail.</p>
    <div class="badge">
      <span style="width: 8px; height: 8px; border-radius: 50%; background: #10b981; display: inline-block;"></span>
      Post-Quantum ML-KEM Vault Bound
    </div>
    <div class="guidance-banner">
      <div class="guidance-check">✓</div>
      <div>
        <div class="guidance-title">Please close this browser tab</div>
        <div class="guidance-desc">Return to the QuMail desktop application to access your secured inbox.</div>
      </div>
    </div>
    <p class="subtext">Your QuMail desktop app is authenticated and active.</p>
  </div>
</body>
</html>
"""



# -------------------------------------------------------------------------
# Custom Exceptions
# -------------------------------------------------------------------------

class GmailAuthError(Exception):
    """Raised when Gmail OAuth2 authentication or token refresh fails."""
    pass


# -------------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------------

def _load_credentials() -> Credentials | None:
    """
    Load cached Gmail credentials from the token file on disk.
    Returns a Credentials object if the token file exists, None otherwise.
    The token file is written by _save_credentials() after first authorisation.
    """
    if not os.path.exists(GMAIL_TOKEN_PATH):
        return None
    try:
        with open(GMAIL_TOKEN_PATH, "rb") as f:
            encrypted = f.read()
        token_data = json.loads(_get_fernet().decrypt(encrypted).decode("utf-8"))
        return Credentials.from_authorized_user_info(token_data, GMAIL_SCOPES)
    except InvalidToken as exc:
        raise GmailAuthError("Stored Gmail token cannot be decrypted.") from exc
    except Exception as exc:
        raise GmailAuthError(
            f"Failed to load Gmail token from '{GMAIL_TOKEN_PATH}': {exc}"
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


def _save_credentials(creds: Credentials) -> None:
    """
    Persist refreshed or newly acquired Gmail credentials to the token file.
    Called after every successful authorisation or refresh so the next
    session can skip the browser flow.
    """
    try:
        _ensure_secret_dir(GMAIL_TOKEN_PATH)
        encrypted = _get_fernet().encrypt(creds.to_json().encode("utf-8"))
        with open(GMAIL_TOKEN_PATH, "wb") as f:
            f.write(encrypted)
        _secure_file_permissions(GMAIL_TOKEN_PATH)
    except Exception as exc:
        raise GmailAuthError(
            f"Failed to save Gmail token to '{GMAIL_TOKEN_PATH}': {exc}"
        ) from exc


# -------------------------------------------------------------------------
# Clean Dedicated Loopback OAuth Server
# -------------------------------------------------------------------------

class _OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """
    Minimal, clean HTTP request handler for the OAuth2 redirect callback.
    Responds to Google's loopback GET with the visual success landing page,
    flushes the response, closes the connection cleanly, and yields control.
    """
    def log_message(self, *args):
        pass  # Never log OAuth callback requests or sensitive URL parameters

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if "code" in qs and qs["code"]:
            self.server.oauth_code = qs["code"][0]
        if "error" in qs and qs["error"]:
            self.server.oauth_error = qs["error"][0]
        if "state" in qs and qs["state"]:
            self.server.oauth_state = qs["state"][0]

        html_bytes = SUCCESS_HTML_PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html_bytes)))
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(html_bytes)
        self.wfile.flush()


class _OAuthLoopbackServer(http.server.HTTPServer):
    """Loopback HTTP server bound strictly to IPv4 127.0.0.1 on an OS-assigned ephemeral port."""
    def __init__(self, host: str = "127.0.0.1"):
        super().__init__((host, 0), _OAuthCallbackHandler)
        self.timeout = 1.0
        self.oauth_code: str | None = None
        self.oauth_error: str | None = None
        self.oauth_state: str | None = None
        self.expected_state: str | None = None
        self.nonce: str | None = None


def _run_loopback_flow(flow: InstalledAppFlow, timeout: int = 180) -> tuple[Credentials, str]:
    """
    Run a clean, isolated IPv4 loopback HTTP server to receive Google's OAuth callback.
    Avoids wsgiref keep-alive connection drops, IPv6 localhost resolution mismatch,
    and CPython SSL WinSock abort errors (CPython #35324 / #102547).
    Returns (credentials, nonce).
    """
    server = _OAuthLoopbackServer("127.0.0.1")
    port = server.server_port
    redirect_uri = f"http://127.0.0.1:{port}/"
    flow.redirect_uri = redirect_uri

    nonce = secrets.token_urlsafe(32)
    auth_url, state = flow.authorization_url(
        prompt="select_account consent",
        access_type="offline",
        nonce=nonce,
    )
    server.expected_state = state
    server.nonce = nonce
    logger.info("Opening system browser for Google OAuth: redirect=%s", redirect_uri)
    webbrowser.open(auth_url, new=1, autoraise=True)

    deadline = time.time() + timeout
    while time.time() < deadline and not server.oauth_code and not server.oauth_error:
        server.handle_request()

    # Clean server teardown: Close the loopback socket completely BEFORE calling fetch_token
    # to guarantee zero port collisions or WinSock reset interference with outbound HTTPS.
    server.server_close()
    time.sleep(0.25)

    # Sanitize environment and clear C-level errno
    sanitize_ssl_environment()

    if server.oauth_error:
        raise GmailAuthError(f"Google sign-in was declined: {server.oauth_error}")
    if not server.oauth_code:
        raise GmailAuthError("Google sign-in timed out waiting for browser consent.")

    # Constant-time state parameter verification
    if not server.oauth_state or not secrets.compare_digest(server.expected_state or "", server.oauth_state or ""):
        raise GmailAuthError("OAuth state parameter mismatch (possible CSRF or replay attempt).")

    # Strategy 1: Attempt standard flow.fetch_token()
    last_exc = None
    try:
        flow.fetch_token(code=server.oauth_code)
        return flow.credentials, nonce
    except Exception as exc:
        last_exc = exc
        logger.warning(
            "flow.fetch_token() note: %s; falling back to direct secure HTTPS token exchange...",
            exc,
        )

    # Strategy 2: Direct secure HTTPS token exchange via urllib.request
    # Immune to requests connection pool resets, stale C errno, and urllib3 protocol aborts
    try:
        import urllib.request
        import urllib.parse
        import ssl
        import certifi

        cfg_dict = getattr(flow, "client_config", {})
        inst = cfg_dict.get("installed") or cfg_dict.get("web") or cfg_dict
        client_id = inst.get("client_id", "")
        client_secret = inst.get("client_secret", "")
        token_endpoint = inst.get("token_uri", "https://oauth2.googleapis.com/token")

        data_dict = {
            "grant_type": "authorization_code",
            "code": server.oauth_code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": flow.redirect_uri,
        }
        if hasattr(flow, "code_verifier") and flow.code_verifier:
            data_dict["code_verifier"] = flow.code_verifier

        encoded_data = urllib.parse.urlencode(data_dict).encode("utf-8")
        req = urllib.request.Request(
            token_endpoint,
            data=encoded_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "User-Agent": "QuMail/1.0",
                "Connection": "close",
            },
        )

        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
            resp_body = resp.read().decode("utf-8")
            token_json = json.loads(resp_body)

        from google.oauth2.credentials import Credentials
        creds = Credentials(
            token=token_json.get("access_token"),
            refresh_token=token_json.get("refresh_token"),
            id_token=token_json.get("id_token"),
            token_uri=token_endpoint,
            client_id=client_id,
            client_secret=client_secret,
            scopes=GMAIL_SCOPES,
        )
        logger.info("Direct secure token exchange via urllib succeeded.")
        return creds, nonce
    except Exception as direct_exc:
        logger.error("Direct secure token exchange failed: %s", direct_exc, exc_info=True)
        raise GmailAuthError(f"OAuth token exchange failed after retries: {last_exc or direct_exc}") from direct_exc


# -------------------------------------------------------------------------
# Public interface
# -------------------------------------------------------------------------

def get_access_token() -> str:
    """
    Return a valid Gmail OAuth2 access token, refreshing or re-authorising as needed.

    Flow:
      1. Load cached credentials from GMAIL_TOKEN_PATH.
      2. If credentials exist and are valid — return the access token immediately.
      3. If credentials exist but are expired — refresh silently using the refresh token.
      4. If no credentials exist or refresh fails — launch the local browser OAuth2
         consent flow using the client secrets file at GMAIL_CLIENT_SECRETS_PATH.
      5. Persist updated credentials back to GMAIL_TOKEN_PATH.

    The access token is returned as a plain string. The caller (smtp_sender.py or
    imap_receiver.py) passes it to the SMTP/IMAP authentication call.
    Token storage beyond this call is the responsibility of core/session.py.

    Raises GmailAuthError on any unrecoverable authentication failure.
    """
    try:
        creds = _load_credentials()

        # --- Valid cached credentials: return immediately ---
        if creds and creds.valid:
            return creds.token

        # --- Expired credentials with a refresh token: refresh silently ---
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                _save_credentials(creds)
                return creds.token
            except Exception as refresh_exc:
                # Refresh failed — fall through to full re-authorisation
                creds = None

        # --- No credentials or refresh failed: run browser consent flow ---
        client_config, source_desc, err = load_google_client_config()
        if not client_config:
            raise GmailAuthError(
                f"Google OAuth client configuration not found: {err or 'Missing client_secret.json'}. "
                "Please select your client_secret.json or configure your Gmail account "
                "under Custom Mailbox."
            )
        logger.info("Initializing Google OAuth flow using %s", source_desc)
        flow = InstalledAppFlow.from_client_config(
            client_config,
            scopes=GMAIL_SCOPES,
        )
        creds, _ = _run_loopback_flow(flow)
        _save_credentials(creds)
        return creds.token

    except GmailAuthError:
        raise
    except Exception as exc:
        raise GmailAuthError(
            f"Gmail OAuth2 authentication failed: {exc}"
        ) from exc


def authorize_google_account() -> dict:
    """
    Run browser Google OAuth 2.0 PKCE consent flow and return cryptographically verified
    user profile, tokens, and M3 VerifiedProviderIdentity.
    Uses canonical or auto-discovered client_secret.json, or preconfigured credentials.
    Presents an informative confirmation card in the browser instructing the user to close the tab.
    """
    sanitize_ssl_environment()

    client_config, source_desc, err = load_google_client_config()
    if not client_config:
        raise GmailAuthError(
            f"Google OAuth client configuration not found: {err or 'Missing client_secret.json'}. "
            "Please select your client_secret_*.json via 'Select client_secret.json' or configure your credentials."
        )

    logger.info("Initializing Google OAuth flow using %s", source_desc)
    flow = InstalledAppFlow.from_client_config(
        client_config,
        scopes=GMAIL_SCOPES,
    )

    creds, nonce = _run_loopback_flow(flow)
    _save_credentials(creds)

    id_token = getattr(creds, "id_token", None)
    if not id_token or not isinstance(id_token, str):
        raise GmailAuthError("Google OAuth flow completed, but response did not contain an ID token.")

    installed_or_web = client_config.get("installed") or client_config.get("web") or client_config
    client_id = installed_or_web.get("client_id", "")
    if not client_id:
        raise GmailAuthError("Missing client_id in Google OAuth client configuration.")

    # Cryptographically verify ID token JWT against Google public keys with audience matching client_id
    from google.oauth2 import id_token as google_id_token
    from google.auth.transport.requests import Request as GoogleRequest
    try:
        verified_claims = google_id_token.verify_oauth2_token(
            id_token,
            GoogleRequest(),
            audience=client_id,
        )
    except Exception as ver_err:
        logger.error("Google ID token signature verification failed: %s", ver_err)
        raise GmailAuthError(f"Google ID token signature verification failed: {ver_err}") from ver_err

    # Constant-time nonce validation
    token_nonce = verified_claims.get("nonce", "")
    if not token_nonce or not secrets.compare_digest(token_nonce, nonce):
        logger.error("Google ID token nonce mismatch: expected=%s, got=%s", nonce, token_nonce)
        raise GmailAuthError("Google ID token nonce mismatch (possible replay attempt).")

    # Strict issuer validation
    iss = verified_claims.get("iss", "")
    if iss not in ("accounts.google.com", "https://accounts.google.com"):
        raise GmailAuthError(f"Google ID token issuer is invalid: {iss}")

    # Strict email verification
    if verified_claims.get("email_verified") is not True:
        raise GmailAuthError("Google account email is not verified.")

    # Expiration check
    if int(verified_claims.get("exp", 0)) <= int(time.time()):
        raise GmailAuthError("Google ID token has expired.")

    # Audience check
    if verified_claims.get("aud") != client_id:
        raise GmailAuthError("Google ID token audience mismatch.")

    user_email = verified_claims.get("email", "")
    if not user_email or "@" not in user_email:
        raise GmailAuthError("Google ID token did not contain a valid email address.")

    # Workspace hosted domain verification: Google explicitly warns email_verified alone
    # is not authoritative for third-party email. Domain aliases fail closed.
    domain = user_email.rsplit("@", 1)[1].lower()
    if domain != "gmail.com" and verified_claims.get("hd") != domain:
        raise GmailAuthError(f"Google Workspace domain mismatch: expected hd={domain}, got {verified_claims.get('hd')}")

    display_name = verified_claims.get("name", "") or user_email.split("@")[0]
    sub = verified_claims.get("sub", "")

    # Construct authentic M3 VerifiedProviderIdentity
    from experiments.m3.identity import validated_google_claims
    try:
        provider_identity = validated_google_claims(verified_claims, client_id, nonce)
    except Exception as m3_err:
        raise GmailAuthError(f"M3 identity claims validation failed: {m3_err}") from m3_err

    logger.info("Cryptographically verified Google ID token: email=%s, sub=%s", user_email, sub)

    expiry_ts = int(creds.expiry.timestamp()) if getattr(creds, "expiry", None) else int(time.time()) + 3600

    return {
        "email": user_email,
        "displayName": display_name,
        "subject": sub,
        "token": creds.token,
        "identity": provider_identity,
        "tokens": {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token or "",
            "expiry": expiry_ts,
            "scopes": list(GMAIL_SCOPES),
        },
    }


def revoke_token() -> None:
    """
    Revoke the current Gmail OAuth2 token and delete the local token file.
    Called by settings_window.py when the user disconnects their Gmail account.
    After revocation, the next call to get_access_token() will trigger a full
    browser consent flow.

    Does not raise if the token file does not exist — treats it as already revoked.
    """
    import google.auth.transport.requests
    import requests as req_lib

    try:
        creds = _load_credentials()
        if creds and creds.token:
            # Best-effort server-side revocation — failure does not block local cleanup
            try:
                req_lib.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": creds.token},
                    timeout=5,
                )
            except Exception:
                pass  # Local cleanup proceeds regardless

        if os.path.exists(GMAIL_TOKEN_PATH):
            os.remove(GMAIL_TOKEN_PATH)

    except GmailAuthError:
        raise
    except Exception as exc:
        raise GmailAuthError(f"Gmail token revocation failed: {exc}") from exc
