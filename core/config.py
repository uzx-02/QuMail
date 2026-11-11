# core/config.py — App-wide constants. Single source of truth.
# Do not import from any other QuMail module here.
# Do not store runtime state here — use core/session.py for that.
import os

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

def validate_google_client_config(content: dict) -> tuple[bool, str, dict | None]:
    """
    Validate whether a parsed JSON dictionary is a valid Google OAuth 2.0 client configuration.
    Explicitly rejects Google Cloud Service Account keys (type == 'service_account') with
    clear, actionable guidance for the user.
    Returns (is_valid, error_or_client_id, normalized_dict).
    """
    if not isinstance(content, dict):
        return False, "Invalid JSON structure (expected an object).", None

    if content.get("type") == "service_account":
        return (
            False,
            "The selected file is a Google Cloud Service Account key, not an OAuth 2.0 Client ID. "
            "QuMail requires an OAuth 2.0 Client ID of type 'Desktop app' (Installed application). "
            "In Google Cloud Console, navigate to 'APIs & Services' > 'Credentials', click 'Create Credentials' "
            "> 'OAuth client ID', select Application type 'Desktop app', and download that JSON.",
            None,
        )

    cfg = None
    if "installed" in content and isinstance(content["installed"], dict):
        cfg = content["installed"]
    elif "web" in content and isinstance(content["web"], dict):
        cfg = content["web"]
    elif "client_id" in content:
        cfg = content

    if not cfg:
        return (
            False,
            "Selected JSON does not contain 'installed' or 'web' OAuth client configuration. "
            "Please ensure you downloaded the client secret JSON for a Desktop or Web application.",
            None,
        )

    client_id = str(cfg.get("client_id", "")).strip()
    client_secret = str(cfg.get("client_secret", "")).strip()

    if not client_id:
        return False, "Selected JSON is missing 'client_id'.", None

    normalized = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": cfg.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
            "token_uri": cfg.get("token_uri", "https://oauth2.googleapis.com/token"),
            "redirect_uris": cfg.get("redirect_uris", ["http://localhost", "http://127.0.0.1"]),
        }
    }
    return True, client_id, normalized

def load_google_client_config() -> tuple[dict | None, str, str | None]:
    """
    Locate, validate, and load Google OAuth client configuration.
    Order of precedence:
      1. Explicit environment variable QUMAIL_GOOGLE_CLIENT_CONFIG_PATH
      2. Canonical user config: %LOCALAPPDATA%/QuMail/config/google_client_secret.json
      3. Project workspace fallback: secrets/gmail_client_secret.json
      4. Auto-discovery: parent / workspace folders matching client_secret_*.json
         (If found and valid, auto-copies to canonical config for permanent reliability)
      5. Built-in configuration / environment variables (QUMAIL_GMAIL_CLIENT_ID)
    Returns: (config_dict, source_description, error_message)
    """
    # 1. Environment variable override
    env_path = os.environ.get("QUMAIL_GOOGLE_CLIENT_CONFIG_PATH")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                ok, res, norm = validate_google_client_config(data)
                if ok and norm:
                    return norm, f"environment variable ({p})", None
                return None, str(p), res
            except Exception as exc:
                return None, str(p), f"Failed to read file: {exc}"

    # 2. Canonical user config
    canon = get_google_client_secrets_path()
    if canon.is_file():
        try:
            with open(canon, "r", encoding="utf-8") as f:
                data = json.load(f)
            ok, res, norm = validate_google_client_config(data)
            if ok and norm:
                return norm, f"user configuration ({canon})", None
            return None, str(canon), res
        except Exception as exc:
            pass

    # 3. Workspace secrets directory fallback
    ws_secret = Path(__file__).resolve().parent.parent / "secrets" / "gmail_client_secret.json"
    if ws_secret.is_file():
        try:
            with open(ws_secret, "r", encoding="utf-8") as f:
                data = json.load(f)
            ok, res, norm = validate_google_client_config(data)
            if ok and norm:
                # Copy to canonical config for permanent persistence
                try:
                    with open(canon, "w", encoding="utf-8") as cf:
                        json.dump(norm, cf, indent=2)
                except Exception:
                    pass
                return norm, f"workspace secrets ({ws_secret})", None
        except Exception:
            pass

    # 4. Auto-discovery in workspace and parent folders
    search_dirs = [
        Path.cwd(),
        Path(__file__).resolve().parent.parent,
        Path(__file__).resolve().parent.parent.parent,
    ]
    if getattr(sys, "frozen", False):
        search_dirs.append(Path(sys.executable).parent)
        search_dirs.append(Path(sys.executable).parent.parent)

    seen_files = set()
    for s_dir in search_dirs:
        try:
            for match in s_dir.glob("client_secret_*.json"):
                if match in seen_files:
                    continue
                seen_files.add(match)
                try:
                    with open(match, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    ok, res, norm = validate_google_client_config(data)
                    if ok and norm:
                        # Auto-copy to canonical user config
                        try:
                            with open(canon, "w", encoding="utf-8") as cf:
                                json.dump(norm, cf, indent=2)
                        except Exception:
                            pass
                        return norm, f"auto-discovered {match.name}", None
                except Exception:
                    continue
        except Exception:
            continue

    # 5. Built-in configuration if populated
    client_id = os.getenv("QUMAIL_GMAIL_CLIENT_ID", "").strip()
    client_secret = os.getenv("QUMAIL_GMAIL_CLIENT_SECRET", "").strip()
    if client_id:
        cfg = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost", "http://127.0.0.1"],
            }
        }
        return cfg, "environment client credentials", None

    return None, "none", "No Google OAuth Client configuration found."

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

# Pre-configured Desktop Client ID & Secret for seamless end-user Google Sign-In
BUILTIN_GMAIL_CLIENT_CONFIG = {
    "installed": {
        "client_id": os.getenv("QUMAIL_GMAIL_CLIENT_ID", ""),
        "client_secret": os.getenv("QUMAIL_GMAIL_CLIENT_SECRET", ""),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost", "http://127.0.0.1"],
    }
}

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
