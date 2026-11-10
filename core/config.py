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
from pathlib import Path

def _resolve_secret_path(filename: str) -> str:
    """Find secret file across runtime directory, source tree, or frozen bundle."""
    candidates = [
        Path("secrets") / filename,
        Path(__file__).resolve().parent.parent / "secrets" / filename,
    ]
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidates.extend([
            exe_dir / "secrets" / filename,
            exe_dir / "_internal" / "secrets" / filename,
            exe_dir / "_internal" / filename,
        ])
        if hasattr(sys, "_MEIPASS"):
            meipass = Path(sys._MEIPASS)
            candidates.extend([
                meipass / "secrets" / filename,
                meipass / filename,
            ])

    for p in candidates:
        if p.is_file():
            return str(p.resolve())

    # Default fallback for new writes
    if getattr(sys, "frozen", False):
        target = Path(sys.executable).parent / "secrets" / filename
    else:
        target = Path(__file__).resolve().parent.parent / "secrets" / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    return str(target.resolve())

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
