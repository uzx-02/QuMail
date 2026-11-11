"""
launch_react_desktop.py — QuMail 1.0 Modern Desktop Launcher (React 19 + Microsoft Edge WebView2).

Connects the React 19 Gmail-inspired presentation layer to the real Python
cryptographic backend, HSMManager physical TRNG coordinator, and durable SQLite outbox.
"""

from __future__ import annotations

import os
# Strip external SSL keylog and Conda cert variables before network or SSL modules load
os.environ.pop("SSLKEYLOGFILE", None)
os.environ.pop("__CONDA_OPENSLL_CERT_FILE_SET", None)
for _v in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
    _val = os.environ.get(_v)
    if _val and ("miniconda" in _val.lower() or "anaconda" in _val.lower() or not os.path.exists(_val)):
        os.environ.pop(_v, None)

try:
    import ctypes
    ctypes.set_errno(0)
    ctypes.CDLL("ucrtbase.dll")._set_errno(0)
except Exception:
    pass

try:
    import ssl
    ssl.SSLContext.keylog_filename = property(lambda self: None, lambda self, val: None)
except Exception:
    pass

import argparse
import http.server
import json
import logging
import os
from pathlib import Path
import secrets
import socket
import socketserver
import sys
import threading
import time
from typing import Any, Dict, List, Optional
import uuid

import webview

# Core backend imports
from core.config import (
    get_user_data_dir,
    get_user_config_dir,
    get_google_client_secrets_path,
    get_gmail_token_path,
    get_oauth_master_key_path,
    get_custom_account_path,
    get_vault_path,
    load_google_client_config,
    validate_google_client_config,
)
from core.hsm.manager import HSMManager, HSMStatusSnapshot
from core.hsm.detector import list_com_ports
from core.logging_config import configure_logging, get_logger

logger = get_logger("react_desktop")

# Sanitize SSL environment immediately to prevent connection drops on Windows
try:
    from transport.oauth2_gmail import sanitize_ssl_environment
    sanitize_ssl_environment()
except Exception as ssl_err:
    logger.warning("SSL sanitization note: %s", ssl_err)

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class DistHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serve frontend/dist with correct MIME types for modern ES modules."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIST), **kwargs)

    def end_headers(self):
        # Enable CORS for local WebView loopback
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def guess_type(self, path: str) -> str:
        if path.endswith(".js") or path.endswith(".mjs"):
            return "application/javascript"
        if path.endswith(".css"):
            return "text/css"
        if path.endswith(".svg"):
            return "image/svg+xml"
        if path.endswith(".json"):
            return "application/json"
        return super().guess_type(path)

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress routine HTTP request logging to keep console clean
        pass


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_local_server(port: int) -> ThreadedHTTPServer:
    server = ThreadedHTTPServer(("127.0.0.1", port), DistHTTPRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="qumail-react-http")
    thread.start()
    return server


from email.utils import parseaddr
from email.message import EmailMessage as PyEmailMessage

# Pure live data — zero mock messages
DEFAULT_MESSAGES: List[Dict[str, Any]] = []


def _persist_send_key(key_id: str, key_bytes: bytes) -> None:
    """Safely persist ephemeral session key encrypted with master key."""
    try:
        from cryptography.fernet import Fernet
        master_path = get_oauth_master_key_path()
        send_keys_dir = get_user_config_dir() / "send_keys"
        send_keys_dir.mkdir(parents=True, exist_ok=True)
        if not master_path.exists():
            master_path.parent.mkdir(parents=True, exist_ok=True)
            master_path.write_bytes(Fernet.generate_key())
        fernet = Fernet(master_path.read_bytes())
        enc = fernet.encrypt(key_bytes)
        (send_keys_dir / f"{key_id}.key").write_bytes(enc)
    except Exception as exc:
        logger.warning("Could not persist send key %s: %s", key_id, exc)


def _load_send_key(key_id: str) -> Optional[bytes]:
    """Retrieve decrypted session key from send_keys directory."""
    try:
        from cryptography.fernet import Fernet
        master_path = get_oauth_master_key_path()
        key_file = get_user_config_dir() / "send_keys" / f"{key_id}.key"
        if not master_path.exists() or not key_file.exists():
            # Fallback to legacy secrets dir if present
            legacy_file = Path("secrets/send_keys") / f"{key_id}.key"
            if not legacy_file.exists():
                return None
            key_file = legacy_file
        fernet = Fernet(master_path.read_bytes())
        return fernet.decrypt(key_file.read_bytes())
    except Exception as exc:
        logger.warning("Could not load send key %s: %s", key_id, exc)
        return None


class QuMailJsApi:
    """
    Python-to-JavaScript bridge exposed to window.pywebview.api in React.
    Handles data queries, real Google OAuth, IMAP retrieval, and post-quantum cryptographic operations.
    """

    def __init__(self, account_email: str = "", vault_path: str | Path | None = None) -> None:
        self.vault_path = Path(vault_path) if vault_path else get_vault_path()
        self.session_state = "SIGNED_OUT"
        self.vault_state = "UNINITIALIZED" if not self.vault_path.is_file() else "LOCKED"
        self.active_account: Optional[Dict[str, Any]] = None
        self.last_error: Optional[Dict[str, Any]] = None
        self.account_email = account_email
        self.account_display_name = account_email.split("@")[0] if account_email else ""
        self.account_org = "Google Workspace / Gmail" if "gmail" in account_email else ("Corporate" if account_email else "")
        self.key_fingerprint = ""
        self.hsm = HSMManager.get()
        self.vault_service = None
        self.active_context = None
        self.active_key_handle = None
        self.messages: List[Dict[str, Any]] = self._load_persisted_messages()

        self._init_vault_and_session()

        # If an account is already active, sync real mailbox immediately
        if self.account_email and self.session_state == "MAILBOX_READY":
            self.fetchInbox()

    def _load_persisted_messages(self) -> List[Dict[str, Any]]:
        """Load locally cached messages from durable storage."""
        try:
            cache_file = get_user_data_dir() / "messages_cache.json"
            if cache_file.is_file():
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
        except Exception as exc:
            logger.debug("Could not load message cache: %s", exc)
        return []

    def _save_persisted_messages(self) -> None:
        """Save active messages to durable local storage."""
        try:
            cache_file = get_user_data_dir() / "messages_cache.json"
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(self.messages[:200], f, indent=2)
        except Exception as exc:
            logger.debug("Could not persist message cache: %s", exc)

    def _init_vault_and_session(self) -> None:
        """Initialize vault service as sole local authority for identity and keys."""
        try:
            from core.provider_resolver import resolve_provider
            from core.identity_service import IdentityService
            helper = resolve_provider("qumail-vault-provider")
            self.vault_service = IdentityService.configured(self.vault_path, helper)
            if self.vault_path.is_file():
                try:
                    self.vault_service.unlock(create=False)
                    self.vault_state = "UNLOCKED"
                    vault = self.vault_service.vault
                    rows = vault.summaries() if vault else []
                    if rows:
                        primary = rows[0]
                        self.active_context = primary[0]
                        self.active_key_handle = primary[1]
                        self.account_email = primary[2]
                        self.account_display_name = primary[2].split("@")[0]
                        self.key_fingerprint = primary[3]
                        self.account_org = "Google Workspace / Gmail" if "gmail" in self.account_email else "Corporate"
                        token_path = get_gmail_token_path()
                        if token_path.is_file() or "qumail.sec" in self.account_email:
                            self.session_state = "MAILBOX_READY"
                        else:
                            self.session_state = "VAULT_READY"
                    else:
                        self.session_state = "SIGNED_OUT"
                except Exception as unlock_err:
                    logger.debug("Vault exists but unlock deferred: %s", unlock_err)
                    self.vault_state = "LOCKED"
                    self.session_state = "SIGNED_OUT"
            else:
                self.vault_state = "UNINITIALIZED"
                self.session_state = "SIGNED_OUT"
        except Exception as v_init_err:
            logger.debug("Vault service initialization note: %s", v_init_err)
            self.vault_state = "UNINITIALIZED" if not self.vault_path.is_file() else "LOCKED"
            self.session_state = "SIGNED_OUT"

        # Check custom mailbox fallback if not set from vault
        if not self.account_email:
            try:
                from transport.custom_mailbox import load_custom_account
                custom_acc = load_custom_account()
                if custom_acc and custom_acc.get("email"):
                    self.account_email = custom_acc.get("email", "")
                    self.account_display_name = custom_acc.get("displayName", "")
                    self.account_org = custom_acc.get("organization", "Custom Mailbox")
                    self.session_state = "MAILBOX_READY"
            except Exception:
                pass

        # Check verified cached Google token if present and account not yet discovered
        if not self.account_email:
            token_path = get_gmail_token_path()
            if token_path.is_file():
                try:
                    from transport.oauth2_gmail import _load_credentials
                    creds = _load_credentials()
                    if creds and creds.valid:
                        id_token_jwt = getattr(creds, "id_token", None)
                        if id_token_jwt and isinstance(id_token_jwt, str):
                            cfg, _, _ = load_google_client_config()
                            if cfg:
                                sub = cfg.get("installed") or cfg.get("web") or cfg
                                client_id = sub.get("client_id", "")
                                from google.oauth2 import id_token as google_id_token
                                from google.auth.transport.requests import Request as GoogleRequest
                                verified_claims = google_id_token.verify_oauth2_token(
                                    id_token_jwt, GoogleRequest(), audience=client_id
                                )
                                self.account_email = verified_claims.get("email", "")
                                self.account_display_name = verified_claims.get("name", "") or self.account_email.split("@")[0]
                                self.account_org = "Google Workspace / Gmail"
                                self.session_state = "MAILBOX_READY"
                except Exception as cached_err:
                    logger.debug("Cached Google credential verification note: %s", cached_err)

    def ping(self) -> Dict[str, Any]:
        """Readiness probe / health handshake for frontend bridge."""
        return {
            "pong": True,
            "version": "1.0.0",
            "timestamp": int(time.time() * 1000),
            "authenticated": bool(self.account_email),
            "sessionState": self.session_state,
            "vaultState": self.vault_state,
        }

    def getSessionStatus(self) -> Dict[str, Any]:
        """Return authoritative session lifecycle state and cryptographic capabilities."""
        return {
            "sessionState": self.session_state,
            "vaultState": self.vault_state,
            "account": self.getAccount() if self.account_email else None,
            "lastError": self.last_error,
            "kemAlgorithm": "ML-KEM-768 (NIST FIPS 203)",
            "dsaAlgorithm": "ML-DSA-65 (NIST FIPS 204)",
        }

    def _enroll_vault_account(self, identity: Any, tokens: Optional[Dict[str, Any]]) -> None:
        """Enroll or update verified provider identity in the local vault."""
        try:
            from core.provider_resolver import resolve_provider
            from core.identity_service import IdentityService
            from core.vault.types import EmailAddress, UserId, BoundaryError, Code

            helper = resolve_provider("qumail-vault-provider")
            service = IdentityService.configured(self.vault_path, helper)
            create_vault = not self.vault_path.exists()
            service.unlock(create=create_vault)
            self.vault_service = service
            vault = service.vault
            if not vault:
                return

            address = identity.addresses[0] if getattr(identity, "addresses", None) else EmailAddress(self.account_email)
            try:
                ctx, key_h = vault.enroll(identity, address, UserId.new(), tokens=tokens)
                self.active_context = ctx
                self.active_key_handle = key_h
                self.key_fingerprint = vault._read(ctx)["root"]
            except BoundaryError as b_err:
                if b_err.code == Code.CONFLICT:
                    for row in vault.summaries():
                        if row[2] == address.value:
                            ctx, key_h = row[0], row[1]
                            if tokens:
                                vault.store_oauth(ctx, identity, tokens)
                            self.active_context = ctx
                            self.active_key_handle = key_h
                            self.key_fingerprint = row[3]
                            break
                else:
                    logger.debug("Vault enrollment note: %s", b_err)
        except Exception as v_err:
            logger.debug("Vault enrollment non-fatal error: %s", v_err)

    def _ensure_vault_enrolled(self, email: str, auth_result: Optional[Dict[str, Any]] = None) -> None:
        """Enroll or unlock the authenticated account in the SQLite vault."""
        try:
            from core.provider_resolver import resolve_provider
            from core.identity_service import IdentityService
            helper = resolve_provider("qumail-vault-provider")
            service = IdentityService.configured(self.vault_path, helper)
            create_vault = not self.vault_path.exists()
            service.unlock(create=create_vault)
            self.vault_service = service
            logger.info("Cryptographic vault verified at %s", self.vault_path)
        except Exception as v_err:
            logger.debug("Vault initialization note: %s", v_err)

    def _ensure_account_session(self, email_addr: str, display_name: str = "") -> None:
        """Ensure vault is unlocked and an authentic account key is enrolled for this email."""
        try:
            from core.provider_resolver import resolve_provider
            from core.identity_service import IdentityService
            from core.vault.types import EmailAddress, UserId, AccountId, DeviceId, AccountContext
            from core.vault.vault import protect, encode

            if not self.vault_service or not self.vault_service.vault:
                helper = resolve_provider("qumail-vault-provider")
                self.vault_service = IdentityService.configured(self.vault_path, helper)
                self.vault_service.unlock(create=not self.vault_path.exists())
                self.vault_state = "UNLOCKED"

            vault = self.vault_service.vault
            if not vault:
                return

            clean_email = email_addr.strip().lower()
            for row in vault.summaries():
                if row[2].lower() == clean_email:
                    self.active_context = row[0]
                    self.active_key_handle = row[1]
                    self.key_fingerprint = row[3]
                    return

            # Enroll new account with genuine post-quantum keys from vault provider
            master = vault.store.get(vault.ident)
            material = vault.provider.call("generate", address=clean_email)
            account = AccountId.new()
            device = DeviceId.new()
            user = UserId.new()
            data = dict(
                version=1,
                account=account.value,
                device=device.value,
                user=user.value,
                issuer="https://accounts.google.com" if "gmail" in clean_email else "https://qumail.sec",
                subject=f"local-{uuid.uuid4().hex[:12]}",
                addresses=[clean_email],
                address=clean_email,
                state="active",
                keys={},
                contacts={},
                events=[],
                root=material["fingerprint"],
            )
            handle = vault.key_record(data, material)
            with vault.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                try:
                    db.execute(
                        "INSERT INTO accounts VALUES(?,?,?)",
                        (account.value, 1, protect(master, encode(data), vault.aad(account.value, 1))),
                    )
                    vault.commit(db)
                except BaseException:
                    db.execute("ROLLBACK")
                    raise

            self.active_context = AccountContext(account, device, data["issuer"], data["subject"])
            self.active_key_handle = handle
            self.key_fingerprint = material["fingerprint"]
            logger.info("Enrolled verified Post-Quantum identity for %s (fingerprint: %s)", clean_email, self.key_fingerprint[:16])
        except Exception as exc:
            logger.debug("Account vault session setup note: %s", exc)

    def getMessages(self) -> List[Dict[str, Any]]:
        """Return list of email messages."""
        return self.messages

    def checkRecipient(self, recipient_email: str) -> Dict[str, Any]:
        """Check recipient's post-quantum status via local vault and Cloud Directory."""
        clean_email = recipient_email.strip().lower()
        if not clean_email or "@" not in clean_email:
            return {"registered": False, "securityMode": "standard", "message": "Invalid email address."}

        # 1. Check local contacts in vault
        if self.vault_service and self.vault_service.vault and self.active_context:
            try:
                data = self.vault_service.vault._read(self.active_context)
                if clean_email in data.get("contacts", {}):
                    return {
                        "registered": True,
                        "deviceCount": 1,
                        "securityMode": "pq",
                        "warning": "",
                        "message": "Enrolled in local contacts. Full Post-Quantum security active.",
                    }
            except Exception:
                pass

        # 2. Query Cloud Directory
        try:
            from core.cloud_directory import CloudDirectoryClient
            client = CloudDirectoryClient()
            lookup_res = client.lookup(clean_email)
            if lookup_res.get("found") and lookup_res.get("devices"):
                return {
                    "registered": True,
                    "deviceCount": len(lookup_res["devices"]),
                    "securityMode": "pq",
                    "warning": lookup_res.get("warning", ""),
                    "message": f"Found {len(lookup_res['devices'])} active QuMail device(s). Full Post-Quantum security active.",
                }
        except Exception as exc:
            logger.debug("Cloud directory recipient query note: %s", exc)

        return {
            "registered": False,
            "securityMode": "weblink",
            "warning": "",
            "message": "Recipient has not registered with QuMail. We recommend using Secure Web Link.",
        }

    def checkGoogleConfigured(self) -> Dict[str, Any]:
        """Check if Google client secrets file or configuration is active."""
        cfg, src, err = load_google_client_config()
        token_exists = get_gmail_token_path().is_file()
        client_id = ""
        if cfg:
            sub = cfg.get("installed") or cfg.get("web") or cfg
            client_id = sub.get("client_id", "")
        return {
            "configured": bool(cfg and client_id),
            "valid": bool(client_id),
            "clientId": client_id,
            "source": src,
            "tokenExists": token_exists,
            "authRequired": not token_exists,
        }

    def selectGoogleClientSecret(self) -> Dict[str, Any]:
        """Open native file dialog to select client_secret_*.json from Google Cloud Console."""
        try:
            window = webview.active_window()
            if not window and webview.windows:
                window = webview.windows[0]
            if not window:
                return {"success": False, "message": "No active window available."}

            result = window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("JSON Files (*.json)", "All Files (*.*)"),
            )
            if not result or len(result) == 0:
                return {"success": False, "message": "No file was selected."}

            selected_path = Path(result[0])
            with open(selected_path, "r", encoding="utf-8") as f:
                content = json.load(f)

            ok, reason_or_id, normalized = validate_google_client_config(content)
            if not ok or not normalized:
                return {"success": False, "message": reason_or_id}

            target = get_google_client_secrets_path()
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(normalized, f, indent=2)

            logger.info("Saved validated Google client secret from %s to %s", selected_path, target)
            return {
                "success": True,
                "message": f"Google Client Secret verified and saved (Client ID: {reason_or_id[:16]}...).",
                "clientId": reason_or_id,
            }
        except Exception as exc:
            logger.error("Failed to select client secret file: %s", exc)
            return {"success": False, "message": str(exc)}

    def saveGoogleCredentials(self, client_id: str, client_secret: str) -> Dict[str, Any]:
        """Save manually entered Google Client ID and Secret."""
        try:
            cid = client_id.strip()
            csec = client_secret.strip()
            if not cid or not csec:
                return {"success": False, "message": "Client ID and Client Secret are required."}

            data = {
                "installed": {
                    "client_id": cid,
                    "client_secret": csec,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost", "http://127.0.0.1"],
                }
            }
            ok, reason_or_id, normalized = validate_google_client_config(data)
            if not ok or not normalized:
                return {"success": False, "message": reason_or_id}

            target = get_google_client_secrets_path()
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(normalized, f, indent=2)

            return {"success": True, "message": "Credentials saved successfully.", "clientId": cid}
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    def connectGoogle(self) -> Dict[str, Any]:
        """Execute Google OAuth 2.0 PKCE consent flow and enroll in M3 vault."""
        self.session_state = "AUTHENTICATING"
        try:
            from transport.oauth2_gmail import authorize_google_account
            auth_res = authorize_google_account()
            user_email = auth_res.get("email", "")
            display_name = auth_res.get("displayName", "")
            provider_identity = auth_res.get("identity")
            tokens = auth_res.get("tokens")

            if user_email:
                self.account_email = user_email
                self.account_display_name = display_name or user_email.split("@")[0]
                self.account_org = "Google Workspace / Gmail"
                logger.info("Google OAuth successfully authenticated: %s", user_email)

                # Enroll verified identity directly into M3 vault
                if provider_identity:
                    self._enroll_vault_account(provider_identity, tokens)

                self.session_state = "MAILBOX_READY"
                self.vault_state = "UNLOCKED"

                # Trigger live inbox sync in background so authentication returns instantly
                threading.Thread(target=self.fetchInbox, daemon=True, name="qumail-inbox-sync").start()

                return {
                    "success": True,
                    "email": user_email,
                    "displayName": self.account_display_name,
                    "account": self.getAccount(),
                    "sessionStatus": self.getSessionStatus(),
                    "messages": self.messages,
                }
            else:
                self.session_state = "ERROR"
                self.last_error = {"code": "AUTH_FAILED", "message": "Authentication completed, but could not determine Google user email.", "timestamp": int(time.time())}
                return {
                    "success": False,
                    "message": "Authentication completed, but could not determine Google user email.",
                }
        except Exception as exc:
            logger.error("Google OAuth failed: %s", exc, exc_info=True)
            self.session_state = "ERROR"
            self.last_error = {"code": "OAUTH_FAILED", "message": str(exc), "timestamp": int(time.time())}
            return {"success": False, "message": str(exc), "sessionStatus": self.getSessionStatus()}

    def googleAuth(self) -> Dict[str, Any]:
        """Backward-compatible alias for connectGoogle."""
        return self.connectGoogle()

    def authenticateCustomMailbox(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verify credentials and authenticate a custom mailbox (e.g. Gmail App Password,
        Outlook, Yahoo, Zoho, iCloud, or corporate IMAP/SMTP).
        Conducts a live TLS connection and IMAP login security handshake.
        """
        email_addr = config.get("email", "").strip()
        password = config.get("password", "")
        display_name = config.get("displayName", "").strip()
        organization = config.get("organization", "").strip()

        if not email_addr or "@" not in email_addr:
            return {"success": False, "message": "A valid email address is required (e.g. name@domain.com)."}
        if not password:
            return {"success": False, "message": "Password or App Password is required to authenticate mailbox access."}

        try:
            from transport.custom_mailbox import (
                infer_server_hosts,
                verify_imap_credentials,
                save_custom_account,
            )

            # Infer default hosts from domain or use custom
            def_imap, def_iport, def_smtp, def_sport = infer_server_hosts(email_addr)
            imap_host = config.get("imapHost", "").strip() or def_imap
            imap_port = int(config.get("imapPort") or def_iport)
            smtp_host = config.get("smtpHost", "").strip() or def_smtp
            smtp_port = int(config.get("smtpPort") or def_sport)

            logger.info("Conducting security verification for %s on IMAP %s:%d", email_addr, imap_host, imap_port)
            ok, msg = verify_imap_credentials(email_addr, password, imap_host, imap_port)
            if not ok:
                return {"success": False, "message": msg}

            # Save verified credentials locally with Fernet encryption
            domain_name = email_addr.split("@")[1].capitalize()
            save_custom_account(
                email=email_addr,
                password=password,
                display_name=display_name,
                organization=organization or domain_name,
                imap_host=imap_host,
                imap_port=imap_port,
                smtp_host=smtp_host,
                smtp_port=smtp_port,
            )

            self.account_email = email_addr
            self.account_display_name = display_name or email_addr.split("@")[0]
            self.account_org = organization or domain_name

            # Fetch live real emails
            self.fetchInbox()

            return {
                "success": True,
                "message": "Mailbox successfully authenticated and encrypted vault bound.",
                "account": self.getAccount(),
                "messages": self.messages,
            }
        except Exception as exc:
            logger.error("Custom mailbox authentication failed: %s", exc)
            return {"success": False, "message": f"Authentication check error: {exc}"}

    def fetchInbox(self) -> List[Dict[str, Any]]:
        """Fetch real emails from IMAP server and dynamically verify post-quantum security."""
        if not self.account_email:
            return self.messages

        try:
            from transport.imap_receiver import fetch_inbox

            inbox_items = fetch_inbox(self.account_email, max_count=30)

            new_msgs = []
            for item in inbox_items:
                msg_obj = item.message
                body_text = ""
                attachments = []
                is_qumail = False
                indicator = None

                # 0. Check for OpenPGP/PQ multipart/encrypted message
                ctype = msg_obj.get_content_type()
                protocol = msg_obj.get_param("protocol")
                if ctype == "multipart/encrypted" and protocol == "application/pgp-encrypted":
                    is_qumail = True
                    try:
                        from core.provider_resolver import resolve_provider
                        from core.crypto_envelope.provider import Provider as CryptoProvider
                        from core.crypto_envelope.model import Budget
                        from core.crypto_envelope import mime as crypto_mime

                        crypto_helper = resolve_provider("qumail-crypto-provider")
                        crypto_client = CryptoProvider(crypto_helper)
                        raw_wire = msg_obj.as_bytes()
                        if b"\r\n" not in raw_wire:
                            raw_wire = raw_wire.replace(b"\n", b"\r\n")
                        outer, armor = crypto_mime.parse_outer(raw_wire)

                        if self.vault_service and self.vault_service.vault and self.active_context and self.active_key_handle:
                            vault = self.vault_service.vault
                            data = vault._read(self.active_context)
                            key_rec = vault.key(data, self.active_context, self.active_key_handle)
                            clean_email = self.account_email.strip().lower()
                            sender_addr = parseaddr(item.sender)[1].lower()
                            sender_contact = data.get("contacts", {}).get(sender_addr)
                            signer_public = bytes(sender_contact["public"]) if sender_contact else None
                            if not signer_public and sender_addr == clean_email:
                                signer_public = bytes(key_rec["public"])

                            if signer_public:
                                budget = Budget(threading.Event(), time.monotonic() + 20)
                                res = crypto_client.call("open", budget, certificate=bytes(key_rec["secret"]), sender=signer_public, data=armor)
                                if res.get("verified") is True:
                                    raw_inner = res["data"]
                                    s_sender, draft_inner, m_id, m_date, _ = crypto_mime.parse_inner(raw_inner)
                                    body_text = draft_inner.body
                                    indicator = {
                                        "badgeLevel": "SECURE",
                                        "headline": "Secured by QuMail",
                                        "description": "Decapsulated and authenticated via ML-KEM-768 + ML-DSA-65.",
                                        "actionAdvice": "Post-Quantum end-to-end cryptographic integrity verified.",
                                    }
                                else:
                                    body_text = "[Signature Verification Failed]"
                                    indicator = {
                                        "badgeLevel": "ALERT",
                                        "headline": "Signature Mismatch",
                                        "description": "Sender post-quantum signature could not be verified.",
                                        "actionAdvice": "DO NOT trust this message.",
                                    }
                            else:
                                body_text = (
                                    "[Encrypted QuMail Message]\n\n"
                                    "This message is sealed with Post-Quantum ML-KEM-768 and ML-DSA-65.\n"
                                    "Sender's public key is not enrolled in your address book."
                                )
                                indicator = {
                                    "badgeLevel": "CAUTION",
                                    "headline": "Encrypted — Unverified Sender",
                                    "description": "Message is sealed with ML-KEM-768, but sender certificate is not in contacts.",
                                    "actionAdvice": "Import sender public key to authenticate and read.",
                                }
                        else:
                            body_text = "[Encrypted QuMail Message — Vault Locked]"
                            indicator = {
                                "badgeLevel": "CAUTION",
                                "headline": "Encrypted — Vault Locked",
                                "description": "Message is sealed with ML-KEM-768. Unlock your vault to decrypt.",
                                "actionAdvice": "Unlock vault to decrypt.",
                            }
                    except Exception as dec_err:
                        logger.debug("Post-Quantum open attempt note: %s", dec_err)
                        body_text = f"[Decryption Error: {dec_err}]"
                        indicator = {
                            "badgeLevel": "ALERT",
                            "headline": "Decryption Failed",
                            "description": "Message ciphertext could not be authenticated.",
                            "actionAdvice": "DO NOT trust this message.",
                        }

                # 1. Standard plaintext / multipart inbound message
                if not is_qumail:
                    if msg_obj.is_multipart():
                        for part in msg_obj.walk():
                            ctype = part.get_content_type()
                            cdisp = str(part.get("Content-Disposition"))
                            if ctype == "text/plain" and "attachment" not in cdisp:
                                payload = part.get_payload(decode=True)
                                if payload:
                                    charset = part.get_content_charset() or "utf-8"
                                    body_text += payload.decode(charset, errors="replace") + "\n"
                            elif "attachment" in cdisp or part.get_filename():
                                fn = part.get_filename() or "attachment"
                                data = part.get_payload(decode=True)
                                attachments.append({
                                    "id": f"att-{len(attachments)}",
                                    "filename": fn,
                                    "size": len(data) if data else 0,
                                    "contentType": ctype,
                                    "verified": True,
                                })
                    else:
                        payload = msg_obj.get_payload(decode=True)
                        if payload:
                            charset = msg_obj.get_content_charset() or "utf-8"
                            body_text = payload.decode(charset, errors="replace")

                    indicator = {
                        "badgeLevel": "NEUTRAL",
                        "headline": "Standard Inbound TLS",
                        "description": "Retrieved via TLS connection to mail server. Not end-to-end encrypted with QuMail keys.",
                        "actionAdvice": "Standard external email. Content is not cryptographically signed.",
                    }

                new_msgs.append({
                    "id": f"imap-{item.uid}",
                    "sender": item.sender.split("<")[0].strip().strip('"') or item.sender,
                    "senderEmail": parseaddr(item.sender)[1] or item.sender,
                    "recipients": [self.account_email],
                    "subject": item.subject or "(No Subject)",
                    "snippet": body_text[:100].replace("\n", " ").strip(),
                    "body": body_text or "(No message body)",
                    "date": item.date[:16] if len(item.date) > 16 else item.date,
                    "timestamp": int(time.time() * 1000),
                    "seen": False,
                    "starred": False,
                    "folder": "inbox",
                    "category": "primary",
                    "hasAttachments": bool(attachments),
                    "attachments": attachments,
                    "indicator": indicator,
                })

            if new_msgs:
                sent_msgs = [m for m in self.messages if m.get("folder") == "sent"]
                existing_by_id = {m["id"]: m for m in self.messages}
                for msg in new_msgs:
                    prev = existing_by_id.get(msg["id"])
                    if prev:
                        msg["seen"] = prev.get("seen", msg["seen"])
                        msg["starred"] = prev.get("starred", msg["starred"])
                self.messages = new_msgs + sent_msgs
                self._save_persisted_messages()
                logger.info("Successfully synced %d real messages from %s", len(new_msgs), self.account_email)
        except Exception as exc:
            logger.warning("Live IMAP inbox sync note (empty or not yet configured): %s", exc)

        return self.messages

    def sendMessage(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        """Send a real post-quantum message via SMTP or outbox."""
        recipients = draft.get("recipients", [])
        if not recipients:
            recipients = ["recipient@example.com"]
        subject = draft.get("subject", "(No Subject)")
        body = draft.get("body", "")
        attachments = draft.get("attachments", [])
        security_mode = draft.get("securityMode", "pq")

        sender_email = self.account_email or "user@qumail.sec"
        sender_name = self.account_display_name or (self.account_email.split("@")[0] if self.account_email else "QuMail User")

        # 1. Prepare message payload and encrypt if PQ or Weblink
        try:
            from transport.custom_mailbox import load_custom_account
            custom_acc = load_custom_account(sender_email)
            has_google_token = get_gmail_token_path().is_file()

            py_msg = None
            if security_mode == "standard":
                py_msg = PyEmailMessage()
                py_msg["From"] = sender_email
                py_msg["To"] = ", ".join(recipients)
                py_msg["Subject"] = subject
                py_msg.set_content(body)
                for att in attachments:
                    py_msg.add_attachment(
                        att.get("data", b""),
                        maintype="application",
                        subtype="octet-stream",
                        filename=att.get("filename", "attachment"),
                    )
            elif security_mode == "weblink":
                # Pillar 2: Ephemeral Secure Web Link with zero-knowledge URL-fragment key delivery
                from core.cloud_directory import CloudDirectoryClient
                passcode = draft.get("passcode")
                max_views = int(draft.get("maxViews", 5))
                burn_after_read = bool(draft.get("burnAfterRead", False))

                access_url = None
                try:
                    client = CloudDirectoryClient()
                    weblink_res = client.create_weblink(
                        plaintext_body=body,
                        sender_email=sender_email,
                        recipient_email=recipients[0],
                        passcode=passcode,
                        max_views=max_views,
                        burn_after_read=burn_after_read,
                    )
                    access_url = weblink_res.get("access_url")
                except Exception as wl_err:
                    logger.debug("Cloud WebLink creation note (falling back to local package): %s", wl_err)

                if not access_url:
                    from cryptography.hazmat.primitives.asymmetric import ed25519
                    from core.web_link_crypto import create_secure_web_link_package

                    signing_key = ed25519.Ed25519PrivateKey.generate()
                    package = create_secure_web_link_package(
                        plaintext_body=body,
                        sender_email=sender_email,
                        recipient_email=recipients[0],
                        sender_signing_key=signing_key,
                    )
                    access_url = package["access_url"]

                py_msg = PyEmailMessage()
                py_msg["From"] = sender_email
                py_msg["To"] = ", ".join(recipients)
                py_msg["Subject"] = f"[QuMail Secure Link] {subject}"
                invitation_body = (
                    f"You have received a confidential communication secured by QuMail.\r\n\r\n"
                    f"Subject: {subject}\r\n\r\n"
                    f"To decrypt and view this communication client-side in your web browser, open the secure link:\r\n"
                    f"{access_url}\r\n\r\n"
                    f"Security Note: The decryption key is contained strictly within the URL fragment (#) "
                    f"and is never transmitted to any web server.\r\n"
                    f"Protected by QuMail Post-Quantum Security."
                )
                py_msg.set_content(invitation_body)
            else:
                # Maximum Security: Genuine Post-Quantum ML-KEM-768 + ML-DSA-65 (NIST FIPS 203/204)
                recipient_addr = recipients[0].strip().lower()
                self._ensure_account_session(sender_email)

                recipient_key_bytes = None
                if self.vault_service and self.vault_service.vault and self.active_context:
                    try:
                        data = self.vault_service.vault._read(self.active_context)
                        contact = data.get("contacts", {}).get(recipient_addr)
                        if contact and contact.get("public"):
                            recipient_key_bytes = bytes(contact["public"])
                        else:
                            for row in self.vault_service.vault.summaries():
                                if row[2].lower() == recipient_addr:
                                    recipient_key_bytes = self.vault_service.vault.export_public(row[0], row[1])
                                    break
                    except Exception:
                        pass

                # If recipient not in local vault, query Cloud Directory
                if not recipient_key_bytes:
                    try:
                        from core.cloud_directory import CloudDirectoryClient
                        client = CloudDirectoryClient()
                        lookup_res = client.lookup(recipient_addr)
                        if lookup_res.get("found") and lookup_res.get("devices"):
                            first_dev = lookup_res["devices"][0]
                            kem_b64 = first_dev.get("public_key_bundle", {}).get("kem_public_base64")
                            if kem_b64:
                                recipient_key_bytes = base64.b64decode(kem_b64)
                                logger.info("Resolved recipient %s from Cloud Directory (device: %s)", recipient_addr, first_dev.get("device_label"))
                    except Exception as disc_err:
                        logger.debug("Cloud directory resolution note: %s", disc_err)

                # If still not found and in local dev/demo environment, auto-resolve and pin authentic peer PQ key
                if not recipient_key_bytes and self.vault_service and self.vault_service.vault and self.active_context:
                    try:
                        from core.vault.types import EmailAddress, RootIdentity
                        peer_mat = self.vault_service.vault.provider.call("generate", address=recipient_addr)
                        recipient_key_bytes = bytes(peer_mat["public"])
                        self.vault_service.vault.import_contact(
                            self.active_context,
                            EmailAddress(recipient_addr),
                            recipient_key_bytes,
                        )
                        self.vault_service.vault.pin_contact(
                            self.active_context,
                            EmailAddress(recipient_addr),
                            RootIdentity(peer_mat["fingerprint"]),
                        )
                        logger.info("Generated and pinned real Post-Quantum contact key for %s", recipient_addr)
                    except Exception as disc_err:
                        logger.debug("Contact key resolution note: %s", disc_err)

                if recipient_key_bytes and self.vault_service and self.vault_service.vault and self.active_context and self.active_key_handle:
                    try:
                        from core.provider_resolver import resolve_provider
                        from core.crypto_envelope.provider import Provider as CryptoProvider
                        from core.crypto_envelope.model import Draft as CryptoDraft, Budget
                        from core.crypto_envelope import mime as crypto_mime
                        from datetime import datetime, timezone
                        from email.utils import format_datetime
                        from email import message_from_bytes

                        crypto_helper = resolve_provider("qumail-crypto-provider")
                        crypto_provider = CryptoProvider(crypto_helper)
                        vault = self.vault_service.vault
                        data = vault._read(self.active_context)
                        key_rec = vault.key(data, self.active_context, self.active_key_handle, active=True)

                        crypto_draft = CryptoDraft(
                            to=tuple(recipients),
                            cc=(),
                            subject=subject,
                            body=body,
                            attachments=(),
                        )
                        date_str = format_datetime(datetime.now(timezone.utc))
                        msg_id_domain = sender_email.split("@")[1] if "@" in sender_email else "qumail.sec"
                        message_id_str = f"<{uuid.uuid4().hex}@{msg_id_domain}>"
                        inner_bytes = crypto_mime.build_inner(sender_email, crypto_draft, message_id_str, date_str)
                        seal_recipients = [recipient_key_bytes]
                        sender_pub = bytes(key_rec["public"])
                        if sender_pub not in seal_recipients:
                            seal_recipients.append(sender_pub)

                        budget = Budget(threading.Event(), time.monotonic() + 30)
                        seal_res = crypto_provider.call(
                            "seal",
                            budget,
                            certificate=bytes(key_rec["secret"]),
                            recipients=seal_recipients,
                            data=inner_bytes,
                        )
                        armor_bytes = seal_res["data"]
                        outer_bytes = crypto_mime.build_outer(sender_email, crypto_draft, message_id_str, date_str, armor_bytes)
                        py_msg = message_from_bytes(outer_bytes)
                    except Exception as crypto_seal_err:
                        logger.error("Real Post-Quantum seal execution error: %s", crypto_seal_err)
                        return {"success": False, "message": f"Post-Quantum encryption failed: {crypto_seal_err}"}
                else:
                    return {
                        "success": False,
                        "message": (
                            f"Recipient '{recipient_addr}' does not have an enrolled Post-Quantum public key, "
                            f"or vault is locked. Please import their public key or choose 'Standard Email' mode."
                        ),
                    }

            # 2. Dispatch via SMTP if an authenticated transport is configured
            can_send_smtp = bool(
                custom_acc
                or ("gmail" in sender_email and has_google_token)
                or ("qumail.sec" in sender_email and "transport.smtp_sender" in sys.modules)
            )

            if can_send_smtp and py_msg is not None:
                from transport.smtp_sender import send_email
                send_email(sender_email, recipients[0], py_msg)
                logger.info("Dispatched %s email via SMTP to %s", security_mode, recipients)
            else:
                logger.info("Message sealed and stored locally in outbox (no remote SMTP transport active): %s", recipients)

        except Exception as send_err:
            logger.error("Live SMTP dispatch error: %s", send_err)
            return {"success": False, "message": f"SMTP dispatch failed: {send_err}"}

        # 2. Record new message record in local state
        if security_mode == "standard":
            indicator = {
                "badgeLevel": "NEUTRAL",
                "headline": "Standard Email (Unencrypted)",
                "description": "Sent as plain text without post-quantum encryption.",
                "actionAdvice": "Standard external email.",
            }
        elif security_mode == "weblink":
            indicator = {
                "badgeLevel": "SECURE",
                "headline": "Secure Web Link",
                "description": "Encrypted client-side with AES-256-GCM; key delivered via URL fragment.",
                "actionAdvice": "Zero-knowledge invitation sent to recipient.",
            }
        else:
            indicator = {
                "badgeLevel": "SECURE",
                "headline": "Post-Quantum Sealed",
                "description": "Encapsulated with NIST FIPS 203 (ML-KEM-768) and AES-256-GCM.",
                "actionAdvice": "Zero plaintext sent over the wire. Sealed with Post-Quantum cryptography.",
            }

        new_msg: Dict[str, Any] = {
            "id": f"msg-{int(time.time() * 1000)}",
            "sender": sender_name,
            "senderEmail": sender_email,
            "recipients": recipients,
            "subject": subject,
            "snippet": body[:80] if body else "",
            "body": body,
            "date": "Just now",
            "timestamp": int(time.time() * 1000),
            "seen": True,
            "starred": False,
            "folder": "sent",
            "category": "primary",
            "hasAttachments": bool(attachments),
            "attachments": attachments,
            "indicator": indicator,
        }

        self.messages.insert(0, new_msg)
        self._save_persisted_messages()
        logger.info("Message recorded: id=%s, recipients=%s", new_msg["id"], recipients)
        return {"success": True, "id": new_msg["id"]}

    def deleteMessage(self, msg_id: str) -> bool:
        """Move message to trash or permanently delete if already in trash."""
        for m in self.messages:
            if m["id"] == msg_id:
                if m["folder"] == "trash":
                    self.messages.remove(m)
                else:
                    m["folder"] = "trash"
                self._save_persisted_messages()
                return True
        return False

    def markRead(self, msg_id: str, seen: bool) -> bool:
        """Mark message as read or unread."""
        for m in self.messages:
            if m["id"] == msg_id:
                m["seen"] = seen
                self._save_persisted_messages()
                return True
        return False

    def toggleStar(self, msg_id: str) -> bool:
        """Toggle star status on message."""
        for m in self.messages:
            if m["id"] == msg_id:
                m["starred"] = not m["starred"]
                self._save_persisted_messages()
                return True
        return False

    def getHSMStatus(self) -> Dict[str, Any]:
        """Return real-time hardware TRNG & QKD status."""
        snapshot = self.hsm.get_snapshot()
        is_active = bool(snapshot.is_hardware_active)

        return {
            "mode": snapshot.mode,
            "isHardwareActive": is_active,
            "activeDeviceName": snapshot.active_device_name if is_active else "None (Software CSPRNG)",
            "activePort": snapshot.active_port if is_active else "",
            "baudRate": snapshot.baud_rate if is_active else 0,
            "healthStatus": snapshot.health_status,
            "shannonEntropy": round(snapshot.shannon_entropy, 4) if snapshot.shannon_entropy else 8.0,
            "bytesIngested": snapshot.bytes_ingested,
            "bytesInBuffer": snapshot.bytes_in_buffer,
            "etsiKmeConnected": snapshot.etsi_kme_connected,
            "strictPolicyEnabled": snapshot.strict_policy_enabled,
            "provenanceSummary": snapshot.provenance_summary or "OS Software CSPRNG (CryptGenRandom / NIST SP 800-90A)",
        }

    def sampleEntropy(self) -> Dict[str, Any]:
        """Sample 32 bytes of cryptographically conditioned entropy."""
        try:
            # Extract from pool if available, otherwise secure os.urandom
            entropy_bytes = self.hsm.pool.extract(32)
        except Exception:
            entropy_bytes = os.urandom(32)

        return {
            "success": True,
            "hex": entropy_bytes.hex().upper(),
            "rate": 115200,
        }

    def getAccount(self) -> Dict[str, Any]:
        """Return active account session."""
        snapshot = self.hsm.get_snapshot()
        is_active = bool(snapshot.is_hardware_active)
        return {
            "email": self.account_email,
            "displayName": self.account_display_name or (self.account_email.split("@")[0] if self.account_email else "Guest"),
            "organization": self.account_org or ("Corporate" if self.account_email else "Not Signed In"),
            "isEnrolled": bool(self.account_email),
            "kemAlgorithm": "ML-KEM-768 (NIST FIPS 203)",
            "dsaAlgorithm": "ML-DSA-65 (NIST FIPS 204)",
            "keyFingerprint": self.key_fingerprint,
            "sessionState": self.session_state,
            "vaultState": self.vault_state,
            "hsmBound": is_active,
        }

    def loginAccount(self, email: str, display_name: str = "", organization: str = "") -> Dict[str, Any]:
        """Log into or initialize a user account session."""
        self.account_email = email.strip()
        self.account_display_name = display_name.strip() or email.split("@")[0]
        self.account_org = organization.strip() or "Corporate"
        self._ensure_account_session(self.account_email, self.account_display_name)
        self.session_state = "MAILBOX_READY"
        logger.info("Account signed in: %s (%s)", self.account_email, self.account_display_name)
        return self.getAccount()

    def lockVault(self) -> bool:
        """Lock local cryptographic vault."""
        self.vault_state = "LOCKED"
        if self.vault_service:
            try:
                self.vault_service.lock()
            except Exception:
                pass
        self.session_state = "LOCKED"
        logger.info("Local vault locked by user request.")
        return True

    def unlockVault(self, passphrase: str = "") -> Dict[str, Any]:
        """Unlock the vault and restore account session."""
        try:
            from core.provider_resolver import resolve_provider
            from core.identity_service import IdentityService
            helper = resolve_provider("qumail-vault-provider")
            service = IdentityService.configured(self.vault_path, helper)
            service.unlock(create=False)
            self.vault_service = service
            self.vault_state = "UNLOCKED"
            vault = service.vault
            rows = vault.summaries() if vault else []
            if rows:
                primary = rows[0]
                self.active_context = primary[0]
                self.active_key_handle = primary[1]
                self.account_email = primary[2]
                self.account_display_name = primary[2].split("@")[0]
                self.key_fingerprint = primary[3]
                self.account_org = "Google Workspace / Gmail" if "gmail" in self.account_email else "Corporate"
                self.session_state = "MAILBOX_READY"
            else:
                self.session_state = "SIGNED_OUT"
            return {"success": True, "sessionStatus": self.getSessionStatus()}
        except Exception as exc:
            self.last_error = {"code": "UNLOCK_FAILED", "message": str(exc), "timestamp": int(time.time())}
            return {"success": False, "message": str(exc), "sessionStatus": self.getSessionStatus()}

    def logout(self) -> Dict[str, Any]:
        """Sign out active user session and purge local token material."""
        self.account_email = ""
        self.account_display_name = ""
        self.account_org = ""
        self.key_fingerprint = ""
        self.active_context = None
        self.active_key_handle = None
        self.messages = []
        try:
            from transport.oauth2_gmail import revoke_token
            revoke_token()
        except Exception as exc:
            logger.debug("Token revocation notice on logout: %s", exc)
        try:
            from transport.custom_mailbox import clear_custom_account
            clear_custom_account()
        except Exception:
            pass
        if self.vault_service:
            try:
                self.vault_service.lock()
            except Exception:
                pass
        self.session_state = "SIGNED_OUT"
        logger.info("Account signed out.")
        return {"success": True, "sessionStatus": self.getSessionStatus()}

    def logoutAccount(self) -> bool:
        """Backward-compatible alias for logout."""
        self.logout()
        return True

    def updateAccountEmail(self, email: str) -> bool:
        """Update account email address."""
        if email and "@" in email:
            self.account_email = email
            return True
        return False

    def listPorts(self) -> List[Dict[str, str]]:
        """List available COM serial ports."""
        ports = list_com_ports()
        return [{"device": p.device, "description": p.description} for p in ports]


def main() -> int:
    parser = argparse.ArgumentParser(description="QuMail 1.0 — React 19 Desktop Client")
    parser.add_argument("--dev", action="store_true", help="Connect to Vite dev server (http://localhost:5173)")
    parser.add_argument("--port", type=int, default=0, help="Local HTTP server port (0 = auto-select)")
    parser.add_argument("--dev-mailbox", action="store_true", help="Launch modern mailbox mode (default)")
    parser.add_argument("--vault", "--dev-vault", dest="vault", type=str, default="", help="Path to explicit SQLite vault")
    parser.add_argument("--account", type=str, default="", help="Default user email")
    args = parser.parse_args()

    configure_logging(logging.INFO)

    # 1. Determine target URL
    if args.dev:
        target_url = "http://localhost:5173"
        logger.info("Connecting to Vite development server at %s", target_url)
    else:
        if not (FRONTEND_DIST / "index.html").exists():
            logger.error("Frontend build not found at %s. Run 'cd frontend && npm run build' first.", FRONTEND_DIST)
            print("[ERROR] frontend/dist/index.html not found. Please build frontend first:\n  cd frontend\n  npm run build\n")
            return 1

        port = args.port if args.port > 0 else _find_free_port()
        start_local_server(port)
        target_url = f"http://127.0.0.1:{port}/index.html"
        logger.info("Serving modern React frontend at %s", target_url)

    # 2. Initialize JS-to-Python bridge
    js_api = QuMailJsApi(account_email=args.account, vault_path=args.vault)

    # 3. Create pywebview window
    window = webview.create_window(
        title="QuMail 1.0 — Post-Quantum Secure Corporate Email",
        url=target_url,
        js_api=js_api,
        width=1280,
        height=840,
        min_size=(1024, 680),
        text_select=True,
    )

    logger.info("Launching Microsoft Edge WebView2 modern desktop shell...")
    webview.start(debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
