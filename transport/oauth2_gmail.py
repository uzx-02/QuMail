# transport/oauth2_gmail.py — Gmail OAuth2 token acquisition and refresh.
# Single responsibility: obtain and refresh a valid Gmail OAuth2 access token
# using google-auth-oauthlib. Token storage is handled by core/session.py — not here.
# This file handles only the authentication flow, not email sending or receiving.
# Do not import from crypto/, mime/, portal/, or certificates/.
# Do not store tokens in this file — pass them to core/session.py via the caller.

import json
import os
import stat

from google.oauth2.credentials        import Credentials
from google.auth.transport.requests   import Request
from google_auth_oauthlib.flow        import InstalledAppFlow
from cryptography.fernet import Fernet, InvalidToken

from core.config  import GMAIL_CLIENT_SECRETS_PATH, GMAIL_SCOPES, GMAIL_TOKEN_PATH
_OAUTH_MASTER_KEY_PATH = "secrets/oauth_master.key"



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
        flow = InstalledAppFlow.from_client_secrets_file(
            GMAIL_CLIENT_SECRETS_PATH,
            scopes=GMAIL_SCOPES,
        )
        creds = flow.run_local_server(port=0)
        _save_credentials(creds)
        return creds.token

    except GmailAuthError:
        raise
    except Exception as exc:
        raise GmailAuthError(
            f"Gmail OAuth2 authentication failed: {exc}"
        ) from exc


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
