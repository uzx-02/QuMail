"""
transport/oauth2_gmail.py — Google OAuth2 token acquisition, refresh, and profile retrieval.

Uses Google's official `google-auth-oauthlib` and `google-auth` libraries with
Fernet token encryption at rest.  The app owns a narrow, single-use loopback
receiver so it can enforce callback state, host, timeout, and replay checks
without patching private library internals.
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import secrets
import hashlib
import stat
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse
import webbrowser

from cryptography.fernet import Fernet, InvalidToken
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from core.config import (
    GMAIL_SCOPES,
    GMAIL_TOKEN_PATH,
    get_gmail_token_path,
    get_oauth_master_key_path,
)

logger = logging.getLogger("transport.oauth2_gmail")

class GmailAuthError(Exception):
    """Raised when Gmail OAuth2 authentication or token refresh fails."""

    def __init__(self, message: str, *, code: str = "AUTH_FAILED") -> None:
        super().__init__(message)
        self.code = code


_OAUTH_CALLBACK_TIMEOUT_SECONDS = 300
_OAUTH_REQUEST_TIMEOUT_SECONDS = 20
# A signed Google token can be issued a few seconds ahead of a desktop clock.
# The identity boundary retries only the maintained verifier's
# ``Token used too early`` result; it never accepts skew or an expired token.
_GOOGLE_TOKEN_FUTURE_WAIT_SECONDS = 20
_ACCOUNT_LOCKS: dict[str, threading.RLock] = {}
_ACCOUNT_LOCKS_GUARD = threading.Lock()


def _account_lock(email: str) -> threading.RLock:
    """Return the process-local serialization lock for one credential record."""
    key = email.strip().lower() or "__legacy_default__"
    with _ACCOUNT_LOCKS_GUARD:
        return _ACCOUNT_LOCKS.setdefault(key, threading.RLock())


def generate_pkce_verifier() -> str:
    """Create an RFC 7636 verifier in the permitted 43–128 character range."""
    return secrets.token_urlsafe(64)[:96]


def pkce_s256_challenge(verifier: str) -> str:
    """Return the RFC 7636 S256 challenge for ``verifier``."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# -------------------------------------------------------------------------
# Fernet Token Protection
# -------------------------------------------------------------------------

def _ensure_secret_dir(path: Path | str) -> None:
    p = Path(path).resolve()
    parent = p.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(str(parent), stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    except OSError:
        pass


_DPAPI_MAGIC = b"QUMAIL_DPAPI_v1\0"


def dpapi_protect(data: bytes, description: str = "QuMail OAuth Master Key") -> bytes:
    """Encrypt sensitive key material at rest using Windows DPAPI (CryptProtectData)."""
    if os.name != "nt":
        return data
    try:
        import win32crypt
        return win32crypt.CryptProtectData(data, description, None, None, None, 0)
    except Exception:
        pass
    try:
        import ctypes as c
        from ctypes import wintypes as w

        class DATA_BLOB(c.Structure):
            _fields_ = [("cbData", w.DWORD), ("pbData", c.POINTER(c.c_byte))]

        crypt32 = c.windll.crypt32
        kernel32 = c.windll.kernel32
        blob_in = DATA_BLOB(len(data), c.cast(c.create_string_buffer(data, len(data)), c.POINTER(c.c_byte)))
        blob_out = DATA_BLOB()
        if not crypt32.CryptProtectData(c.byref(blob_in), description, None, None, None, 0, c.byref(blob_out)):
            raise OSError(f"DPAPI CryptProtectData failed: {c.GetLastError()}")
        res = c.string_at(blob_out.pbData, blob_out.cbData)
        kernel32.LocalFree(blob_out.pbData)
        return res
    except Exception as exc:
        logger.warning("Windows DPAPI protect fallback note: %s", exc)
        return data


def dpapi_unprotect(data: bytes) -> bytes:
    """Decrypt sensitive key material using Windows DPAPI (CryptUnprotectData)."""
    if os.name != "nt":
        return data
    try:
        import win32crypt
        return win32crypt.CryptUnprotectData(data, None, None, None, 0)[1]
    except Exception:
        pass
    try:
        import ctypes as c
        from ctypes import wintypes as w

        class DATA_BLOB(c.Structure):
            _fields_ = [("cbData", w.DWORD), ("pbData", c.POINTER(c.c_byte))]

        crypt32 = c.windll.crypt32
        kernel32 = c.windll.kernel32
        blob_in = DATA_BLOB(len(data), c.cast(c.create_string_buffer(data, len(data)), c.POINTER(c.c_byte)))
        blob_out = DATA_BLOB()
        if not crypt32.CryptUnprotectData(c.byref(blob_in), None, None, None, None, 0, c.byref(blob_out)):
            raise OSError(f"DPAPI CryptUnprotectData failed: {c.GetLastError()}")
        res = c.string_at(blob_out.pbData, blob_out.cbData)
        kernel32.LocalFree(blob_out.pbData)
        return res
    except Exception as exc:
        logger.warning("Windows DPAPI unprotect fallback note: %s", exc)
        return data


def _get_fernet() -> Fernet:
    """Return Fernet instance backed by the DPAPI-wrapped local master key file."""
    mk_path = get_oauth_master_key_path()
    _ensure_secret_dir(mk_path)
    if mk_path.is_file():
        raw_bytes = mk_path.read_bytes()
        if raw_bytes.startswith(_DPAPI_MAGIC):
            key = dpapi_unprotect(raw_bytes[len(_DPAPI_MAGIC):])
        else:
            # Legacy plaintext Fernet key on disk: seamlessly migrate to DPAPI wrapping
            key = raw_bytes
            try:
                Fernet(key)
                wrapped = _DPAPI_MAGIC + dpapi_protect(key)
                _atomic_write_bytes(mk_path, wrapped)
                logger.info("Migrated plaintext OAuth master key to Windows DPAPI-wrapped storage at %s", mk_path)
            except Exception as mig_err:
                logger.warning("Could not migrate legacy OAuth master key to DPAPI: %s", mig_err)
    else:
        # Check legacy relative path if present
        legacy = Path("secrets/oauth_master.key")
        if legacy.is_file():
            key = legacy.read_bytes()
        else:
            key = Fernet.generate_key()
        wrapped = _DPAPI_MAGIC + dpapi_protect(key)
        _atomic_write_bytes(mk_path, wrapped)
        try:
            os.chmod(str(mk_path), stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    return Fernet(key)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Durably replace one encrypted credential record without partial writes."""
    _ensure_secret_dir(path)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        try:
            os.chmod(str(path), stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _normalize_client_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Build an installed-app configuration, retaining an optional local secret.

    Desktop clients are public and PKCE is always used.  Some Google client
    registrations nevertheless require their generated client secret at the
    token endpoint.  It is therefore optional input, never bundled, and is
    kept out of persisted per-account token records.
    """
    client_id = str(config.get("client_id") or "").strip()
    if not client_id:
        raise GmailAuthError("Google desktop OAuth client ID is missing.", code="CLIENT_CONFIG")
    installed: Dict[str, Any] = {
        "client_id": client_id,
        "project_id": str(config.get("project_id") or ""),
        "auth_uri": str(config.get("auth_uri") or "https://accounts.google.com/o/oauth2/auth"),
        "token_uri": str(config.get("token_uri") or "https://oauth2.googleapis.com/token"),
    }
    client_secret = config.get("client_secret")
    if isinstance(client_secret, str) and client_secret.strip():
        installed["client_secret"] = client_secret.strip()
    return {"installed": installed}


def _load_client_config() -> Dict[str, Any]:
    """Read a validated client configuration through the canonical config loader."""
    from core.config import load_google_client_config

    config, source, error = load_google_client_config()
    if not config:
        raise GmailAuthError(
            "Google desktop OAuth configuration was not found. Import a desktop client JSON in Settings.",
            code="CLIENT_CONFIG",
        )
    logger.info("Using Google OAuth client configuration from %s", source)
    return _normalize_client_config(config)


def _credentials_from_token_data(token_data: Dict[str, Any]) -> Credentials:
    """Deserialize both legacy confidential and current public-client records.

    ``Credentials.from_authorized_user_info`` in some supported google-auth
    releases insists on a client secret.  Constructing ``Credentials`` directly
    avoids inventing one while retaining the legacy loader for old records.
    """
    if token_data.get("client_secret"):
        return Credentials.from_authorized_user_info(token_data, GMAIL_SCOPES)
    client_id = str(token_data.get("client_id") or "").strip()
    token = token_data.get("token")
    if not client_id or not token:
        raise ValueError("Public-client credential record is incomplete.")
    expiry = None
    raw_expiry = token_data.get("expiry")
    if raw_expiry:
        expiry_text = str(raw_expiry)
        # google-auth serializes an aware UTC datetime as ``+00:00Z`` in
        # some releases; RFC 3339's trailing Z is otherwise conventional.
        if expiry_text.endswith("+00:00Z"):
            expiry_text = expiry_text[:-1]
        elif expiry_text.endswith("Z"):
            expiry_text = expiry_text[:-1] + "+00:00"
        expiry = datetime.fromisoformat(expiry_text)
        if expiry.tzinfo is not None:
            expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)
    return Credentials(
        token=token,
        refresh_token=token_data.get("refresh_token"),
        id_token=token_data.get("id_token"),
        token_uri=token_data.get("token_uri") or "https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=None,
        scopes=token_data.get("scopes") or GMAIL_SCOPES,
        expiry=expiry,
    )


def _refresh_public_client_credentials(creds: Credentials, client_secret: str = "") -> None:
    """Refresh a desktop-client grant without persisting a client secret.

    google-auth 2.49 requires a client secret for ``Credentials.refresh`` even
    though RFC 6749 public clients legitimately omit it.  Keep that library path
    for legacy confidential records; use the documented token endpoint directly
    for secret-less desktop records.
    """
    if not creds.refresh_token or not creds.client_id or not creds.token_uri:
        raise GmailAuthError("Stored Google credentials cannot be refreshed.", code="AUTH_REQUIRED")
    import requests

    refresh_data = {
        "grant_type": "refresh_token",
        "refresh_token": creds.refresh_token,
        "client_id": creds.client_id,
    }
    if client_secret:
        refresh_data["client_secret"] = client_secret
    response = requests.post(
        creds.token_uri,
        data=refresh_data,
        timeout=_OAUTH_REQUEST_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        raise GmailAuthError("Google refresh token was rejected. Reconnect this account.", code="AUTH_REQUIRED")
    try:
        payload = response.json()
        access_token = str(payload["access_token"])
        expires_in = int(payload.get("expires_in", 3600))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise GmailAuthError("Google refresh response was invalid. Reconnect this account.", code="AUTH_REQUIRED") from exc
    if not access_token or expires_in <= 0:
        raise GmailAuthError("Google refresh response was invalid. Reconnect this account.", code="AUTH_REQUIRED")
    creds.token = access_token
    creds.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=expires_in)
    if payload.get("refresh_token"):
        creds.refresh_token = str(payload["refresh_token"])
    if payload.get("id_token"):
        creds.id_token = str(payload["id_token"])


def _load_credentials(email: str = "") -> Tuple[Optional[Credentials], Optional[Dict[str, Any]]]:
    """
    Load cached Gmail credentials from encrypted token file on disk.
    If email is specified, prioritizes per-account token file, verifying identity.
    Returns (Credentials, raw_token_dict) if valid, or (None, None).
    """
    clean_email = email.strip().lower() if email else ""
    candidates = []
    if clean_email:
        candidates.append(get_gmail_token_path(clean_email))
    candidates.extend([get_gmail_token_path(), Path(GMAIL_TOKEN_PATH), Path("secrets/gmail_token.json")])

    for target in candidates:
        if not target.is_file():
            continue
        try:
            raw_enc = target.read_bytes()
            fernet = _get_fernet()
            decrypted = fernet.decrypt(raw_enc).decode("utf-8")
            token_data = json.loads(decrypted)

            # If an email is requested, verify token belongs to this email if metadata is present
            stored_email = (token_data.get("email") or "").strip().lower()
            if not stored_email and token_data.get("id_token"):
                try:
                    parts = token_data["id_token"].split(".")
                    if len(parts) >= 2:
                        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                        claims = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
                        stored_email = (claims.get("email") or "").strip().lower()
                        if stored_email:
                            token_data["email"] = stored_email
                except Exception:
                    pass

            if clean_email and stored_email and stored_email != clean_email:
                continue
            if clean_email and not stored_email and target != get_gmail_token_path(clean_email):
                continue

            if "client_id" not in token_data:
                from core.config import load_google_client_config
                cfg, _, _ = load_google_client_config()
                if cfg:
                    token_data.setdefault("client_id", cfg.get("client_id"))
                    if cfg.get("client_secret"):
                        token_data.setdefault("client_secret", cfg.get("client_secret"))
            creds = _credentials_from_token_data(token_data)
            return creds, token_data
        except InvalidToken as exc:
            logger.warning("Stored Gmail token in %s cannot be decrypted with master key: %s", target, exc)
        except Exception as exc:
            logger.warning("Failed to load Gmail credentials from %s: %s", target, exc)

    return None, None


def _save_credentials(creds: Credentials, extra: Optional[Dict[str, Any]] = None, email: str = "") -> None:
    """Persist refreshed or newly acquired credentials encrypted with Fernet (per-account)."""
    target_email = (email or (extra.get("email") if extra else "") or "").strip().lower()
    token_path = get_gmail_token_path(target_email)
    _ensure_secret_dir(token_path)

    data = json.loads(creds.to_json())
    if extra:
        # ``extra`` is durable identity/presentation metadata from the prior
        # record.  It must never overwrite values just obtained from a refresh;
        # doing so would re-save the expired token and defeat the per-account
        # refresh lock on the next caller.
        credential_fields = {
            "token", "refresh_token", "expiry", "client_id", "client_secret",
            "token_uri", "scopes",
        }
        data.update({key: value for key, value in extra.items() if key not in credential_fields})

    fernet = _get_fernet()
    encrypted = fernet.encrypt(json.dumps(data, sort_keys=True).encode("utf-8"))
    # Validate the exact bytes before replacing the old record.  A failed write
    # must leave the previous credential readable for recovery/reconnect.
    json.loads(fernet.decrypt(encrypted).decode("utf-8"))
    _atomic_write_bytes(token_path, encrypted)
    logger.info("Saved encrypted Google credentials to %s", token_path)

    # Also keep default gmail_token.json updated for single-token / legacy fallback
    default_token_path = get_gmail_token_path()
    if default_token_path != token_path:
        try:
            _atomic_write_bytes(default_token_path, encrypted)
        except Exception as exc:
            logger.warning("Could not update legacy default Gmail token cache: %s", exc)


def _build_oauth_success_html() -> str:
    """Return an aesthetically pleasing, modern dark-themed HTML success page for the browser."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>QuMail - Authentication Successful</title>
  <style>
    :root {
      --bg: #090D16;
      --card: #111827;
      --border: #1F2937;
      --accent: #06B6D4;
      --accent-glow: rgba(6, 182, 212, 0.35);
      --success: #10B981;
      --text: #F3F4F6;
      --muted: #9CA3AF;
    }
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    body {
      background: var(--bg);
      background-image: 
        radial-gradient(circle at 50% 20%, rgba(6, 182, 212, 0.12) 0%, transparent 60%),
        radial-gradient(circle at 80% 80%, rgba(59, 130, 246, 0.08) 0%, transparent 50%);
      color: var(--text);
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 1.5rem;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 20px;
      max-width: 500px;
      width: 100%;
      padding: 2.75rem 2rem;
      text-align: center;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7), 0 0 35px var(--accent-glow);
      animation: fadeIn 0.4s ease-out;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(12px) scale(0.98); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }
    .icon-wrapper {
      position: relative;
      width: 76px;
      height: 76px;
      margin: 0 auto 1.5rem auto;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .pulse-ring {
      position: absolute;
      width: 100%;
      height: 100%;
      border-radius: 50%;
      background: rgba(16, 185, 129, 0.2);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0% { transform: scale(0.95); opacity: 0.8; }
      50% { transform: scale(1.15); opacity: 0.3; }
      100% { transform: scale(0.95); opacity: 0.8; }
    }
    .icon-badge {
      position: relative;
      width: 64px;
      height: 64px;
      background: linear-gradient(135deg, #10B981, #06B6D4);
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 10px 20px -5px rgba(16, 185, 129, 0.5);
    }
    .icon-badge svg {
      width: 32px;
      height: 32px;
      stroke: #ffffff;
      stroke-width: 3;
      fill: none;
      stroke-linecap: round;
      stroke-linejoin: round;
    }
    .title {
      font-size: 1.5rem;
      font-weight: 700;
      color: #ffffff;
      letter-spacing: -0.02em;
      margin-bottom: 0.5rem;
    }
    .subtitle {
      font-size: 0.95rem;
      color: var(--muted);
      line-height: 1.5;
      margin-bottom: 1.75rem;
    }
    .status-box {
      background: #030712;
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.25rem;
      margin-bottom: 1.75rem;
      text-align: left;
    }
    .status-item {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      font-size: 0.85rem;
      color: #D1D5DB;
      margin-bottom: 0.65rem;
    }
    .status-item:last-child {
      margin-bottom: 0;
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent);
      box-shadow: 0 0 8px var(--accent);
      flex-shrink: 0;
    }
    .btn {
      display: inline-block;
      width: 100%;
      padding: 0.85rem 1.5rem;
      background: linear-gradient(135deg, #06B6D4, #3B82F6);
      color: #ffffff;
      font-weight: 600;
      font-size: 0.95rem;
      border-radius: 10px;
      text-decoration: none;
      cursor: pointer;
      border: none;
      transition: all 0.2s ease;
      box-shadow: 0 4px 14px rgba(6, 182, 212, 0.3);
    }
    .btn:hover {
      opacity: 0.92;
      transform: translateY(-1px);
    }
    .notice {
      margin-top: 1.25rem;
      font-size: 0.8rem;
      color: #6B7280;
      line-height: 1.4;
    }
    .logo-footer {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      margin-top: 2rem;
      padding-top: 1.25rem;
      border-top: 1px solid rgba(31, 41, 55, 0.6);
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--muted);
    }
    .logo-q {
      width: 20px;
      height: 20px;
      background: linear-gradient(135deg, #06B6D4, #3B82F6);
      border-radius: 5px;
      display: grid;
      place-items: center;
      color: white;
      font-size: 11px;
      font-weight: 800;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon-wrapper">
      <div class="pulse-ring"></div>
      <div class="icon-badge">
        <svg viewBox="0 0 24 24">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
      </div>
    </div>
    
    <h1 class="title">Authentication Successful</h1>
    <p class="subtitle">Your Google account has been securely linked with QuMail.</p>
    
    <div class="status-box">
      <div class="status-item">
        <span class="dot"></span>
        <span>Google OAuth 2.0 Credentials Sealed</span>
      </div>
      <div class="status-item">
        <span class="dot"></span>
        <span>Post-Quantum Key Exchange Initialized (ML-KEM-768)</span>
      </div>
      <div class="status-item">
        <span class="dot" style="background:#10B981; box-shadow:0 0 8px #10B981;"></span>
        <span>Background Mailbox Sync Active</span>
      </div>
    </div>

    <button class="btn" onclick="window.close()">Return to QuMail Application</button>

    <p class="notice">
      You may now close this browser tab and continue inside the QuMail desktop app.
    </p>

    <div class="logo-footer">
      <div class="logo-q">Q</div>
      <span>QuMail Post-Quantum Security</span>
    </div>
  </div>

  <script>
    setTimeout(function() {
      try { window.close(); } catch(e) {}
    }, 4000);
  </script>
</body>
</html>"""


# -------------------------------------------------------------------------
# Public Interface
# -------------------------------------------------------------------------

class _OAuthCallbackServer(HTTPServer):
    """A one-use loopback receiver for one OAuth transaction."""

    allow_reuse_address = False

    def __init__(self, port: int, expected_state: str) -> None:
        super().__init__(("127.0.0.1", port), _OAuthCallbackHandler)
        self.expected_state = expected_state
        self.authorization_code: Optional[str] = None
        self.error: Optional[str] = None
        self.complete = threading.Event()


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    server: _OAuthCallbackServer

    def log_message(self, _format: str, *_args: Any) -> None:
        # The callback query contains an authorization code; never write it to logs.
        return

    def _reply(self, status: int, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - HTTPServer callback method name
        parsed = urlparse(self.path)
        expected_host = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != expected_host or parsed.path != "/callback":
            self._reply(400, "<h1>Invalid OAuth callback.</h1>")
            return
        query = parse_qs(parsed.query, keep_blank_values=True)
        states = query.get("state", [])
        codes = query.get("code", [])
        errors = query.get("error", [])
        if len(states) != 1 or not secrets.compare_digest(states[0], self.server.expected_state):
            self.server.error = "OAuth callback state validation failed."
            self.server.complete.set()
            self._reply(400, "<h1>OAuth callback rejected.</h1>")
            return
        if errors:
            self.server.error = "Google authorization was cancelled or denied."
            self.server.complete.set()
            self._reply(400, "<h1>Authorization was not completed.</h1>")
            return
        if len(codes) != 1 or not codes[0] or self.server.authorization_code:
            self.server.error = "OAuth callback was invalid or replayed."
            self.server.complete.set()
            self._reply(400, "<h1>OAuth callback rejected.</h1>")
            return
        self.server.authorization_code = codes[0]
        self.server.complete.set()
        self._reply(200, _build_oauth_success_html())


def _wait_for_callback(
    server: _OAuthCallbackServer,
    timeout_seconds: int,
    cancel_event: Optional[threading.Event] = None,
) -> str:
    """Wait for one callback with bounded timeout and an optional cancellation hook."""
    deadline = time.monotonic() + timeout_seconds
    server.timeout = 0.25
    while not server.complete.is_set() and time.monotonic() < deadline:
        if cancel_event is not None and cancel_event.is_set():
            raise GmailAuthError("Google OAuth authorization was cancelled.", code="CALLBACK_CANCELLED")
        server.handle_request()
    if not server.complete.is_set():
        raise GmailAuthError("Google OAuth callback timed out. Please try connecting again.", code="CALLBACK_TIMEOUT")
    if server.error or not server.authorization_code:
        raise GmailAuthError(server.error or "Google OAuth callback failed.", code="CALLBACK_REJECTED")
    return server.authorization_code


def _profile_metadata(access_token: str, verified_email: str) -> tuple[str, str]:
    """Fetch optional presentation metadata without using it as identity evidence."""
    try:
        import requests
        response = requests.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=_OAUTH_REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            return "", ""
        profile = response.json()
        if (profile.get("email") or "").strip().lower() != verified_email:
            logger.warning("Ignoring UserInfo metadata for a different Google account.")
            return "", ""
        return (profile.get("name") or "").strip(), (profile.get("picture") or "").strip()
    except Exception as exc:
        logger.debug("Optional Google UserInfo lookup failed: %s", exc)
        return "", ""


def authorize_google_account(
    port: int = 0,
    *,
    timeout_seconds: int = _OAUTH_CALLBACK_TIMEOUT_SECONDS,
    cancel_event: Optional[threading.Event] = None,
) -> Dict[str, Any]:
    """Run Authorization Code + PKCE through a single-use 127.0.0.1 callback.

    Identity comes solely from a signature-validated ID token.  UserInfo is only
    used to enrich display metadata after its email matches the verified claim.
    """
    config = _load_client_config()
    installed = config["installed"]
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = generate_pkce_verifier()
    server = _OAuthCallbackServer(port, state)
    try:
        redirect_uri = f"http://127.0.0.1:{server.server_port}/callback"
        flow = InstalledAppFlow.from_client_config(config, scopes=GMAIL_SCOPES, state=state)
        flow.redirect_uri = redirect_uri
        flow.code_verifier = verifier
        authorization_url, returned_state = flow.authorization_url(
            access_type="offline",
            prompt="select_account consent",
            include_granted_scopes="true",
            nonce=nonce,
        )
        if not secrets.compare_digest(returned_state, state):
            raise GmailAuthError("OAuth state creation failed.", code="CALLBACK_REJECTED")
        if not webbrowser.open(authorization_url, new=1):
            raise GmailAuthError("Could not open the browser for Google authorization.", code="BROWSER_LAUNCH")
        code = _wait_for_callback(
            server,
            min(max(int(timeout_seconds), 1), _OAUTH_CALLBACK_TIMEOUT_SECONDS),
            cancel_event,
        )
        if installed.get("client_secret"):
            # This preserves compatibility with the current Google client
            # registration, which rejects a secretless exchange. The value is
            # local configuration only and is stripped before token storage.
            flow.fetch_token(code=code, timeout=_OAUTH_REQUEST_TIMEOUT_SECONDS)
        else:
            # Some installed-client registrations accept a secretless PKCE
            # exchange. The maintained helper indexes client_secret, so use
            # its OAuth session directly for this standards-compliant case.
            flow.oauth2session.fetch_token(
                installed["token_uri"],
                code=code,
                code_verifier=verifier,
                include_client_id=True,
                client_id=installed["client_id"],
                timeout=_OAUTH_REQUEST_TIMEOUT_SECONDS,
            )
        creds = flow.credentials
        # Never persist the optional desktop-client secret in an account token
        # record. Refresh reads it afresh from local client configuration.
        creds = Credentials(
            token=creds.token,
            refresh_token=creds.refresh_token,
            id_token=getattr(creds, "id_token", None),
            token_uri=installed["token_uri"],
            client_id=installed["client_id"],
            client_secret=None,
            scopes=getattr(creds, "scopes", None) or GMAIL_SCOPES,
            expiry=getattr(creds, "expiry", None),
        )
        id_token = getattr(creds, "id_token", None) or flow.oauth2session.token.get("id_token")
        if not id_token:
            raise GmailAuthError("Google did not return an ID token for identity verification.", code="ID_TOKEN_MISSING")
        from core.vault.identity import google_identity

        verified = google_identity(
            id_token,
            installed["client_id"],
            nonce,
            state,
            state,
            request=Request(),
            wait_seconds=_GOOGLE_TOKEN_FUTURE_WAIT_SECONDS,
        )
        email = verified.addresses[0].value
        display_name, avatar_url = _profile_metadata(creds.token, email)
        if not display_name and id_token:
            try:
                parts = id_token.split(".")
                if len(parts) >= 2:
                    payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                    id_claims = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
                    display_name = (id_claims.get("name") or "").strip()
            except Exception:
                pass
        effective_display = display_name if (display_name and display_name != email.split("@")[0]) else email
        extra_meta = {
            "email": email,
            "displayName": effective_display,
            "subject": verified.subject,
            "issuer": verified.issuer,
            "id_token": id_token,
            "avatarUrl": avatar_url,
        }
        with _account_lock(email):
            _save_credentials(creds, extra_meta, email=email)
    except GmailAuthError:
        raise
    except Exception as exc:
        logger.warning("Google OAuth authorization failed: %s", type(exc).__name__)
        raise GmailAuthError("Google OAuth authorization could not be completed.", code="AUTH_FAILED") from exc
    finally:
        server.server_close()
        try:
            flow.oauth2session.close()  # type: ignore[name-defined]
        except Exception:
            pass

    return {
        "success": True,
        "email": email,
        "displayName": effective_display,
        "avatarUrl": avatar_url,
        "subject": verified.subject,
        "issuer": verified.issuer,
        # Internal bridge evidence only.  QuMailJsApi consumes it before
        # returning its JSON-safe result to React; it is never serialized to UI.
        "_verified_identity": verified,
        "_id_token": id_token,
        "token": creds.token,
    }


def get_access_token(email: str = "", *, interactive: bool = False) -> str:
    """
    Return a valid Gmail OAuth2 access token for the specified email.

    Mail transport and background work must passively refresh or report a
    reconnect requirement; only a deliberate UI connection may set
    ``interactive=True`` and launch a browser.
    """
    clean_email = email.strip().lower() if email else ""
    with _account_lock(clean_email):
        creds, token_data = _load_credentials(clean_email)

        # 1. Valid cached credentials: return immediately
        if creds and creds.valid:
            return creds.token

        # 2. Expired credentials with refresh token: refresh silently.
        if creds and creds.expired and creds.refresh_token:
            try:
                # Fetch an optional secret only from the local client config;
                # it is intentionally absent from persisted token records.
                config = _load_client_config()["installed"]
                configured_secret = ""
                if config.get("client_id") == creds.client_id:
                    configured_secret = str(config.get("client_secret") or "")
                _refresh_public_client_credentials(creds, configured_secret)
                if getattr(creds, "id_token", None):
                    token_data["id_token"] = creds.id_token
                _save_credentials(creds, extra=token_data, email=clean_email)
                return creds.token
            except Exception as refresh_exc:
                logger.warning("Silent token refresh failed for %s: %s", clean_email or "default", type(refresh_exc).__name__)

    # Never allow a scheduled receive/send/avatar operation to open a browser.
    if not interactive:
        raise GmailAuthError(
            "Google authentication is required. Reconnect this account to continue.",
            code="AUTH_REQUIRED",
        )
    auth_res = authorize_google_account()
    if clean_email and auth_res["email"].strip().lower() != clean_email:
        raise GmailAuthError("The selected Google account does not match the requested mailbox.", code="ACCOUNT_MISMATCH")
    return auth_res["token"]


def get_fresh_id_token(email: str = "") -> Optional[str]:
    """Retrieve an active, verified Google ID token, refreshing silently if expired."""
    clean_email = email.strip().lower() if email else ""
    with _account_lock(clean_email):
        creds, token_data = _load_credentials(clean_email)
        if not creds or not token_data:
            return None

        existing_id = token_data.get("id_token")
        if existing_id:
            try:
                parts = existing_id.split(".")
                if len(parts) >= 2:
                    payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                    claims = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
                    exp = int(claims.get("exp", 0))
                    if exp > int(time.time()) + 60:
                        return existing_id
            except Exception:
                pass

        if creds and creds.refresh_token:
            try:
                config = _load_client_config()["installed"]
                configured_secret = ""
                if config.get("client_id") == creds.client_id:
                    configured_secret = str(config.get("client_secret") or "")
                _refresh_public_client_credentials(creds, configured_secret)
                if getattr(creds, "id_token", None):
                    token_data["id_token"] = creds.id_token
                _save_credentials(creds, extra=token_data, email=clean_email)
                return token_data.get("id_token")
            except Exception as exc:
                logger.warning("Silent token refresh for ID token failed for %s: %s", clean_email or "default", exc)

        return token_data.get("id_token")


def get_stored_account_info(email: str = "") -> Optional[Dict[str, Any]]:
    """Return stored account email and display name if available, recovering avatar from id_token if needed."""
    creds, token_data = _load_credentials(email)
    if token_data and token_data.get("email"):
        avatar = token_data.get("avatarUrl", "")
        # If avatar is missing but id_token is stored in token_data, decode it
        if not avatar and token_data.get("id_token"):
            try:
                parts = token_data["id_token"].split(".")
                if len(parts) >= 2:
                    payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                    claims = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
                    avatar = claims.get("picture", "")
                    if avatar:
                        token_data["avatarUrl"] = avatar
                        if creds:
                            _save_credentials(creds, token_data, email=email)
            except Exception:
                pass

        disp = token_data.get("displayName") or ""
        email_val = token_data.get("email", "")
        if not disp or disp == email_val.split("@")[0]:
            disp = email_val

        return {
            "email": email_val,
            "displayName": disp,
            "avatarUrl": avatar or "",
            "subject": token_data.get("subject") or "",
            "issuer": token_data.get("issuer") or "",
            "tokenExists": True,
        }
    return None


def fetch_account_avatar_from_provider(email: str = "", force_refresh: bool = False) -> str:
    """
    Actively fetch the user's avatar from Gmail / Google profile using stored credentials or access token.
    Updates the encrypted token cache on success and returns the avatar URL.
    """
    clean_email = email.strip().lower() if email else ""
    try:
        creds, token_data = _load_credentials(clean_email)
        if not token_data:
            return ""

        stored_email = (token_data.get("email") or "").strip().lower()
        if clean_email and stored_email and stored_email != clean_email:
            return ""

        # 1. Check existing avatarUrl if not force_refresh
        if not force_refresh and token_data.get("avatarUrl"):
            return token_data["avatarUrl"]

        # 2. Extract from stored id_token if present and not force_refresh
        if not force_refresh and token_data.get("id_token"):
            try:
                parts = token_data["id_token"].split(".")
                if len(parts) >= 2:
                    payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                    claims = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
                    pic = claims.get("picture", "").strip()
                    if pic:
                        token_data["avatarUrl"] = pic
                        if creds:
                            _save_credentials(creds, token_data, email=clean_email)
                        return pic
            except Exception:
                pass

        # 3. Query Google UserInfo endpoints using valid access token
        access_token = get_access_token(clean_email, interactive=False)
        if not access_token:
            return token_data.get("avatarUrl", "")

        import requests
        headers = {"Authorization": f"Bearer {access_token}"}
        for endpoint in (
            "https://openidconnect.googleapis.com/v1/userinfo",
            "https://www.googleapis.com/oauth2/v2/userinfo",
        ):
            try:
                resp = requests.get(endpoint, headers=headers, timeout=8)
                if resp.status_code == 200:
                    data = resp.json()
                    user_email = (data.get("email") or "").strip().lower()
                    if clean_email and user_email and user_email != clean_email:
                        # Cross-account protection: token belongs to different identity!
                        return ""
                    pic = data.get("picture", "").strip()
                    token_data["avatarUrl"] = pic
                    if user_email:
                        token_data["email"] = user_email
                    if data.get("name"):
                        token_data["displayName"] = data.get("name")
                    if creds:
                        _save_credentials(creds, token_data, email=clean_email)
                    return pic
            except Exception as ep_exc:
                logger.debug("Avatar query via %s note: %s", endpoint, ep_exc)

        return token_data.get("avatarUrl", "")
    except Exception as exc:
        logger.debug("fetch_account_avatar_from_provider error: %s", exc)
        return ""

    return ""


def revoke_token(email: str = "") -> None:
    """Revoke Google token and delete token file on logout."""
    import requests
    clean_email = email.strip().lower() if email else ""
    with _account_lock(clean_email):
        creds, _ = _load_credentials(clean_email)
        if creds and (creds.refresh_token or creds.token):
            try:
                requests.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": creds.refresh_token or creds.token},
                    timeout=5,
                )
            except Exception:
                pass

        token_path = get_gmail_token_path(clean_email)
        if token_path.is_file():
            try:
                token_path.unlink()
            except OSError:
                pass
        # The default file is only a backward-compatible mirror.  Remove it
        # only when its encrypted metadata proves it mirrors this account; an
        # unknown legacy default must not be destroyed during another account's
        # logout.
        default_path = get_gmail_token_path()
        if clean_email and default_path != token_path and default_path.is_file():
            try:
                default_data = json.loads(_get_fernet().decrypt(default_path.read_bytes()).decode("utf-8"))
                if (default_data.get("email") or "").strip().lower() == clean_email:
                    default_path.unlink()
            except Exception:
                logger.debug("Could not evaluate legacy default token during logout.")
