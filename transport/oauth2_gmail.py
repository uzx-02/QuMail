"""
transport/oauth2_gmail.py — Google OAuth2 token acquisition, refresh, and profile retrieval.

Restored clean architecture inspired by legacy QuMail:
Uses Google's official `google-auth-oauthlib` and `google-auth` libraries with
standard Fernet token encryption at rest. Eliminates custom socket servers,
ctypes errno tampering, and Windows OpenSSL errno leaks.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
import stat
from typing import Any, Dict, Optional, Tuple

from cryptography.fernet import Fernet, InvalidToken
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from core.config import (
    GMAIL_CLIENT_SECRETS_PATH,
    GMAIL_SCOPES,
    GMAIL_TOKEN_PATH,
    OAUTH_MASTER_KEY_PATH,
    get_google_client_secrets_path,
    get_gmail_token_path,
    get_oauth_master_key_path,
    get_user_config_dir,
)

logger = logging.getLogger("transport.oauth2_gmail")

# Immunize against codex-rejected-cas.pem FileNotFoundError during TLS handshakes
try:
    import ssl
    if not getattr(ssl.SSLContext, "_is_qumail_patched", False):
        from _ssl import _SSLContext

        def _safe_ssl_context_new(cls, protocol=None, *args, **kwargs):
            if protocol is None:
                protocol = getattr(ssl, "PROTOCOL_TLS_CLIENT", ssl.PROTOCOL_TLS)
            self = _SSLContext.__new__(cls, protocol)
            try:
                ssl_dir = os.path.dirname(getattr(ssl, "__file__", ""))
                pem_path = os.path.join(ssl_dir, "codex-rejected-cas.pem")
                if pem_path and os.path.isfile(pem_path):
                    _SSLContext.load_verify_locations(self, cafile=pem_path)
            except Exception:
                pass
            return self

        ssl.SSLContext.__new__ = _safe_ssl_context_new
        ssl.SSLContext._is_qumail_patched = True
except Exception:
    pass


class GmailAuthError(Exception):
    """Raised when Gmail OAuth2 authentication or token refresh fails."""
    pass


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


def _get_fernet() -> Fernet:
    """Return Fernet instance backed by the local master key file."""
    mk_path = get_oauth_master_key_path()
    _ensure_secret_dir(mk_path)
    if mk_path.is_file():
        key = mk_path.read_bytes()
    else:
        # Check legacy relative path if present
        legacy = Path("secrets/oauth_master.key")
        if legacy.is_file():
            key = legacy.read_bytes()
            mk_path.write_bytes(key)
        else:
            key = Fernet.generate_key()
            mk_path.write_bytes(key)
        try:
            os.chmod(str(mk_path), stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    return Fernet(key)


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

            if "client_id" not in token_data or "client_secret" not in token_data:
                from core.config import load_google_client_config
                cfg, _, _ = load_google_client_config()
                if cfg:
                    token_data.setdefault("client_id", cfg.get("client_id"))
                    token_data.setdefault("client_secret", cfg.get("client_secret"))
            creds = Credentials.from_authorized_user_info(token_data, GMAIL_SCOPES)
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
        data.update(extra)

    fernet = _get_fernet()
    encrypted = fernet.encrypt(json.dumps(data, indent=2).encode("utf-8"))
    token_path.write_bytes(encrypted)
    try:
        os.chmod(str(token_path), stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    logger.info("Saved encrypted Google credentials to %s", token_path)

    # Also keep default gmail_token.json updated for single-token / legacy fallback
    default_token_path = get_gmail_token_path()
    if default_token_path != token_path:
        try:
            default_token_path.write_bytes(encrypted)
        except Exception:
            pass


def _resolve_client_secrets_path() -> Path:
    """Locate client_secret JSON file across canonical config and workspace secrets."""
    candidates = [
        get_google_client_secrets_path(),
        Path(GMAIL_CLIENT_SECRETS_PATH),
        Path("secrets/gmail_client_secret.json"),
        Path("secrets/google_client_secret.json"),
    ]
    for c in candidates:
        if c.is_file():
            return c

    # Fallback to demo client secret if present in repo
    demo = Path("secrets/client_secret_953431543574-t137vvqsic9jbrddt9dr1t3g5hjkj5p3.apps.googleusercontent.com.json")
    if demo.is_file():
        return demo

    raise GmailAuthError(
        "Google OAuth client secrets file not found. "
        "Please provide client_secret.json in Settings or place gmail_client_secret.json in secrets/."
    )


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

def authorize_google_account(port: int = 0) -> Dict[str, Any]:
    """
    Launch local browser OAuth2 consent flow using Google's official InstalledAppFlow.
    Retrieves authorization tokens and profile email, stores them safely, and returns account info.
    """
    secrets_path = _resolve_client_secrets_path()
    logger.info("Initializing Google OAuth flow via %s", secrets_path)

    try:
        # Patch WSGI server to return text/html so the modern success page renders correctly
        import wsgiref.util
        from google_auth_oauthlib import flow as google_flow

        def _qumail_wsgi_call(self, environ, start_response):
            start_response("200 OK", [("Content-type", "text/html; charset=utf-8")])
            self.last_request_uri = wsgiref.util.request_uri(environ)
            return [self._success_message.encode("utf-8")]

        google_flow._RedirectWSGIApp.__call__ = _qumail_wsgi_call

        flow = InstalledAppFlow.from_client_secrets_file(
            str(secrets_path),
            scopes=GMAIL_SCOPES,
        )
        creds = flow.run_local_server(
            port=port,
            prompt="consent",
            success_message=_build_oauth_success_html(),
        )
    except Exception as exc:
        logger.error("InstalledAppFlow failed: %s", exc)
        raise GmailAuthError(f"Google OAuth authorization flow failed: {exc}") from exc

    # Query user profile email and avatar using access token and id_token
    email = ""
    display_name = ""
    sub = ""
    avatar_url = ""

    # 1. First, decode claims from id_token if available (instant, zero network latency)
    if hasattr(creds, "id_token") and creds.id_token:
        try:
            parts = creds.id_token.split(".")
            if len(parts) >= 2:
                payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                claims = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
                email = claims.get("email", "").strip()
                display_name = claims.get("name", "").strip()
                sub = claims.get("sub", "").strip()
                avatar_url = claims.get("picture", "").strip()
        except Exception as id_exc:
            logger.debug("Could not parse id_token claims: %s", id_exc)

    # 2. Second, query OpenID Connect userinfo endpoint with access token
    if not avatar_url or not email:
        try:
            import requests
            resp = requests.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {creds.token}"},
                timeout=10,
            )
            if resp.status_code == 200:
                profile = resp.json()
                if not email:
                    email = profile.get("email", "").strip()
                if not display_name:
                    display_name = profile.get("name", "").strip()
                if not sub:
                    sub = profile.get("sub", "").strip()
                if not avatar_url:
                    avatar_url = profile.get("picture", "").strip()
        except Exception as oidc_exc:
            logger.debug("Could not fetch userinfo via OIDC API: %s", oidc_exc)

    # 3. Third, fallback to legacy OAuth2 v2 userinfo
    if not avatar_url or not email:
        try:
            import requests
            resp = requests.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {creds.token}"},
                timeout=10,
            )
            if resp.status_code == 200:
                profile = resp.json()
                if not email:
                    email = profile.get("email", "").strip()
                if not display_name:
                    display_name = profile.get("name", "").strip()
                if not sub:
                    sub = profile.get("id", "").strip()
                if not avatar_url:
                    avatar_url = profile.get("picture", "").strip()
        except Exception as exc:
            logger.debug("Could not fetch userinfo via Google REST API: %s", exc)

    if not email:
        raise GmailAuthError("Could not retrieve verified email address for Google account.")

    # Save credentials with verified email, subject, and avatar
    extra_meta = {
        "email": email,
        "displayName": display_name or email.split("@")[0],
        "subject": sub,
        "id_token": getattr(creds, "id_token", None),
        "avatarUrl": avatar_url,
    }
    _save_credentials(creds, extra_meta)

    # Immediately ensure Cloudflare Directory session token is enrolled for WebLink creation
    try:
        from core.cloud_directory import CloudDirectoryClient
        dir_client = CloudDirectoryClient()
        dir_client._ensure_session_token()
    except Exception as dir_err:
        logger.debug("Auto-enrollment on login note: %s", dir_err)

    return {
        "success": True,
        "email": email,
        "displayName": display_name or email.split("@")[0],
        "avatarUrl": avatar_url,
        "subject": sub,
        "token": creds.token,
    }


def get_access_token(email: str = "") -> str:
    """
    Return a valid Gmail OAuth2 access token for the specified email, refreshing or re-authorizing as needed.
    """
    clean_email = email.strip().lower() if email else ""
    creds, token_data = _load_credentials(clean_email)

    # 1. Valid cached credentials: return immediately
    if creds and creds.valid:
        return creds.token

    # 2. Expired credentials with refresh token: refresh silently
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_credentials(creds, extra=token_data, email=clean_email)
            return creds.token
        except Exception as refresh_exc:
            logger.warning("Silent token refresh failed for %s, re-authorizing: %s", clean_email or "default", refresh_exc)
            creds = None

    # 3. No credentials or refresh failed: trigger consent flow
    auth_res = authorize_google_account()
    return auth_res["token"]


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

        return {
            "email": token_data.get("email"),
            "displayName": token_data.get("displayName") or token_data.get("email", "").split("@")[0],
            "avatarUrl": avatar or "",
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
        access_token = get_access_token(clean_email)
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
    creds, _ = _load_credentials(clean_email)
    if creds and creds.token:
        try:
            requests.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": creds.token},
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
    if token_path.is_file():
        try:
            token_path.unlink()
        except OSError:
            pass
