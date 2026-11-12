# core/config.py — App-wide constants. Single source of truth.
# Do not import from any other QuMail module here.
# Do not store runtime state here — use core/session.py for that.
import os
import base64
from typing import Any

# --- TQR Levels ---
TQR_LEVEL_OTP    = 1   # One-Time Pad — QKD key required
TQR_LEVEL_AES    = 2   # AES-256-GCM seeded with QKD key — QKD key required
TQR_LEVEL_MLKEM  = 3   # ML-KEM FIPS 203 — no QKD key required
TQR_DEFAULT      = TQR_LEVEL_AES  # Default level for new sessions

# --- KME / Virtual Node ---
KME_HOST         = "127.0.0.1"
KME_PORT         = 5000
KME_BASE_URL     = f"http://{KME_HOST}:{KME_PORT}"
KME_API_PATH     = "/api/v1/keys"
KME_KEY_SIZE     = 256   # bits — 256-bit quantum key per request
KME_TIMEOUT_SEC  = 5     # seconds before KME request is considered failed

# --- Portal (Insecure Recipient) ---
PORTAL_HOST      = "127.0.0.1"
PORTAL_PORT      = 5001
PORTAL_LINK_TTL  = 3600  # seconds — portal link expires after 1 hour

# --- MIME ---
MIME_PROTOCOL    = "application/qumail-pgp"
MIME_CONTROL_TYPE = "application/qumail-control"
MIME_PAYLOAD_TYPE = "application/octet-stream"

# --- Certificate Output ---
CERT_OUTPUT_DIR  = "certs"        # relative to project root — created at runtime if missing
SEND_KEYS_DIR    = "secrets/send_keys"  # encrypted ML-KEM private keys, keyed by cert ID

# --- OAuth2: Dynamic Secret Paths ---
import sys
import json
import shutil
from pathlib import Path

def _is_writable_dir(d: Path) -> bool:
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / f".write_probe_{os.getpid()}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False

def get_user_data_dir() -> Path:
    """Return canonical application data directory across Windows and POSIX."""
    override = os.environ.get("QUMAIL_DATA_DIR")
    if override:
        d = Path(override)
        if _is_writable_dir(d):
            return d.resolve()

    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            d = Path(base) / "QuMail"
            if _is_writable_dir(d):
                return d.resolve()
        d = Path.home() / "AppData" / "Local" / "QuMail"
        if _is_writable_dir(d):
            return d.resolve()

    # Fallback to ~/.qumail
    d = Path.home() / ".qumail"
    if _is_writable_dir(d):
        return d.resolve()

    # Workspace fallback for sandboxed testing
    fallback = Path(__file__).resolve().parent.parent / ".qumail_data"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback.resolve()

def get_user_config_dir() -> Path:
    """Return canonical user configuration directory: %LOCALAPPDATA%\\QuMail\\config."""
    cfg = get_user_data_dir() / "config"
    if not _is_writable_dir(cfg):
        cfg = get_user_data_dir()
    return cfg.resolve()

def get_google_client_secrets_path() -> Path:
    """Canonical path to user's Google OAuth client secrets file."""
    return get_user_config_dir() / "google_client_secret.json"

def get_gmail_token_path() -> Path:
    """Canonical path to user's encrypted Gmail OAuth token file."""
    return get_user_config_dir() / "gmail_token.json"

def get_oauth_master_key_path() -> Path:
    """Canonical path to Fernet master key for token encryption."""
    return get_user_config_dir() / "oauth_master.key"

def get_custom_account_path() -> Path:
    """Canonical path to custom mailbox configuration."""
    return get_user_config_dir() / "custom_account.json"

def get_vault_path() -> Path:
    """Canonical path to default user SQLite encrypted vault."""
    return get_user_data_dir() / "vault.sqlite"

def validate_google_client_config(content: Any) -> tuple[bool, str, dict | None]:
    """Validate Google OAuth client secrets format (Installed App / Web Application)."""
    if not isinstance(content, dict):
        return False, "Invalid Google client secrets: root must be a JSON object.", None
    cfg = content.get("installed") or content.get("web")
    if not isinstance(cfg, dict):
        return False, "Google client secret must contain an 'installed' or 'web' application block.", None
    client_id = cfg.get("client_id")
    client_secret = cfg.get("client_secret")
    if not client_id or not isinstance(client_id, str) or not client_id.strip():
        return False, "Google client configuration missing 'client_id'.", None
    if not client_secret or not isinstance(client_secret, str) or not client_secret.strip():
        return False, "Google client configuration missing 'client_secret'.", None
    return True, "Valid Google Client Configuration", cfg


def load_google_client_config() -> tuple[dict | None, str, str | None]:
    """Load and validate the local Google client secrets configuration."""
    candidates = [
        Path(GMAIL_CLIENT_SECRETS_PATH),
        get_user_config_dir() / "gmail_client_secret.json",
        get_user_config_dir() / "google_client_secret.json",
        Path("secrets/gmail_client_secret.json"),
        Path("secrets/google_client_secret.json"),
    ]
    for p in candidates:
        if p.is_file():
            try:
                import json
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                valid, msg, cfg = validate_google_client_config(data)
                if valid and cfg:
                    return cfg, str(p), None
            except Exception as exc:
                return None, str(p), str(exc)
    return None, "missing", "No Google client secrets file found."







def _resolve_secret_path(filename: str) -> str:
    """Find secret file in canonical user config dir or migrate from legacy locations."""
    canon = get_user_config_dir() / filename
    if canon.is_file():
        return str(canon.resolve())

    # Check legacy workspace secrets
    legacy_candidates = [
        Path("secrets") / filename,
        Path(__file__).resolve().parent.parent / "secrets" / filename,
    ]
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        legacy_candidates.extend([
            exe_dir / "secrets" / filename,
            exe_dir / "_internal" / "secrets" / filename,
            exe_dir / "_internal" / filename,
        ])

    for p in legacy_candidates:
        if p.is_file():
            try:
                shutil.copy2(p, canon)
                return str(canon.resolve())
            except Exception:
                return str(p.resolve())

    return str(canon.resolve())

GMAIL_CLIENT_SECRETS_PATH = _resolve_secret_path("gmail_client_secret.json")
GMAIL_TOKEN_PATH          = _resolve_secret_path("gmail_token.json")
CUSTOM_ACCOUNT_PATH       = _resolve_secret_path("custom_account.json")
OAUTH_MASTER_KEY_PATH     = _resolve_secret_path("oauth_master.key")
GMAIL_SCOPES              = [
    "https://mail.google.com/",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

# --- OAuth2: Yahoo ---
YAHOO_CLIENT_ID     = os.getenv("QUMAIL_YAHOO_CLIENT_ID", "")
YAHOO_CLIENT_SECRET = os.getenv("QUMAIL_YAHOO_CLIENT_SECRET", "")
YAHOO_REDIRECT_URI  = "http://localhost:8765/callback"
YAHOO_TOKEN_PATH    = "secrets/yahoo_token.json"
YAHOO_AUTH_URL      = "https://api.login.yahoo.com/oauth2/request_auth"
YAHOO_TOKEN_URL     = "https://api.login.yahoo.com/oauth2/get_token"
YAHOO_SCOPES        = [
    "mail-r",
    "mail-w",
]

# --- App Metadata ---
APP_NAME         = "QuMail"
APP_VERSION      = "1.0.0"

# --- Cloud Public Key Directory & WebLink Gateway ---
DEFAULT_DIRECTORY_URL = "https://qumail-directory.uzair-shaikh-sec-e24.workers.dev"

def get_directory_server_url() -> str:
    """Return configured cloud directory server URL."""
    return os.environ.get("QUMAIL_DIRECTORY_URL", DEFAULT_DIRECTORY_URL).rstrip("/")
