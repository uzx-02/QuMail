"""
transport/custom_mailbox.py — Authenticated Custom Mailbox (IMAP & SMTP).

Handles credentials validation, server discovery, and encrypted storage for
standard IMAP/SMTP accounts (e.g. Gmail with App Password, Outlook, Yahoo,
Zoho, iCloud, and custom corporate email servers).
"""

from __future__ import annotations

import imaplib
import json
import logging
import os
import smtplib
import socket
import ssl
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from cryptography.fernet import Fernet

import stat
from core.config import CUSTOM_ACCOUNT_PATH, get_oauth_master_key_path
from transport.oauth2_gmail import _get_fernet

logger = logging.getLogger("transport.custom_mailbox")

def _secure_file_permissions(path: str) -> None:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass

def _ensure_secret_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if not parent:
        return
    os.makedirs(parent, exist_ok=True)
    try:
        os.chmod(parent, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    except OSError:
        pass

def _account_path_for_email(email: Optional[str] = None) -> Path:
    canon = Path(CUSTOM_ACCOUNT_PATH)
    if not email:
        return canon
    safe_name = "".join(c if c.isalnum() else "_" for c in email.lower())
    specific = canon.parent / f"custom_account_{safe_name}.json"
    if specific.is_file():
        return specific
    return canon

# Known provider host defaults
PROVIDER_HOST_DEFAULTS = {
    "gmail.com": ("imap.gmail.com", 993, "smtp.gmail.com", 587),
    "googlemail.com": ("imap.gmail.com", 993, "smtp.gmail.com", 587),
    "outlook.com": ("outlook.office365.com", 993, "smtp.office365.com", 587),
    "hotmail.com": ("outlook.office365.com", 993, "smtp.office365.com", 587),
    "live.com": ("outlook.office365.com", 993, "smtp.office365.com", 587),
    "msn.com": ("outlook.office365.com", 993, "smtp.office365.com", 587),
    "office365.com": ("outlook.office365.com", 993, "smtp.office365.com", 587),
    "yahoo.com": ("imap.mail.yahoo.com", 993, "smtp.mail.yahoo.com", 587),
    "ymail.com": ("imap.mail.yahoo.com", 993, "smtp.mail.yahoo.com", 587),
    "rocketmail.com": ("imap.mail.yahoo.com", 993, "smtp.mail.yahoo.com", 587),
    "zoho.com": ("imap.zoho.com", 993, "smtp.zoho.com", 587),
    "zohomail.com": ("imap.zoho.com", 993, "smtp.zoho.com", 587),
    "icloud.com": ("imap.mail.me.com", 993, "smtp.mail.me.com", 587),
    "me.com": ("imap.mail.me.com", 993, "smtp.mail.me.com", 587),
    "mac.com": ("imap.mail.me.com", 993, "smtp.mail.me.com", 587),
}


def infer_server_hosts(email: str) -> Tuple[str, int, str, int]:
    """Derive default IMAP and SMTP hosts and ports from email address."""
    email_clean = email.strip().lower()
    domain = email_clean.split("@")[-1] if "@" in email_clean else ""

    if domain in PROVIDER_HOST_DEFAULTS:
        return PROVIDER_HOST_DEFAULTS[domain]

    # Standard convention for custom / corporate domains
    return (f"imap.{domain}", 993, f"smtp.{domain}", 587)


def verify_imap_credentials(email: str, password: str, imap_host: str, imap_port: int = 993) -> Tuple[bool, str]:
    """
    Perform a live TLS connection and IMAP authentication handshake.
    Returns (success, message).
    """
    try:
        ssl_ctx = ssl.create_default_context()
        with imaplib.IMAP4_SSL(imap_host, int(imap_port), ssl_context=ssl_ctx, timeout=12) as imap:
            res, _ = imap.login(email.strip(), password)
            if res == "OK":
                return True, "IMAP authentication verified successfully."
            return False, f"IMAP server returned status: {res}"
    except imaplib.IMAP4.error as err:
        err_msg = str(err)
        return False, (
            f"Authentication failed: {err_msg}. "
            "Note: If your account has 2-Factor Authentication enabled, you must generate "
            "and use an App Password instead of your normal account password."
        )
    except (socket.gaierror, ConnectionRefusedError, TimeoutError, OSError) as conn_err:
        return False, (
            f"Could not connect to IMAP server '{imap_host}:{imap_port}': {conn_err}. "
            "Please check the server hostname and your network connection."
        )
    except Exception as exc:
        return False, f"Unexpected error during IMAP verification: {exc}"


def verify_smtp_credentials(email: str, password: str, smtp_host: str, smtp_port: int = 587) -> Tuple[bool, str]:
    """Verify SMTP authentication over STARTTLS."""
    try:
        ssl_ctx = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, int(smtp_port), timeout=10) as smtp:
            smtp.ehlo()
            if smtp.has_extn("STARTTLS"):
                smtp.starttls(context=ssl_ctx)
                smtp.ehlo()
            smtp.login(email.strip(), password)
            return True, "SMTP authentication verified successfully."
    except smtplib.SMTPAuthenticationError as err:
        return False, f"SMTP authentication failed: {err}"
    except Exception as exc:
        logger.warning("SMTP verification note: %s", exc)
        return False, str(exc)


def save_custom_account(
    email: str,
    password: str,
    display_name: str = "",
    organization: str = "",
    imap_host: str = "",
    imap_port: int = 993,
    smtp_host: str = "",
    smtp_port: int = 587,
) -> bool:
    """Save encrypted custom mailbox credentials locally."""
    try:
        _ensure_secret_dir(str(CUSTOM_ACCOUNT_PATH))
        data = {
            "email": email.strip(),
            "password": password,
            "displayName": display_name.strip() or email.split("@")[0],
            "organization": organization.strip() or "Custom Mailbox",
            "imapHost": imap_host.strip(),
            "imapPort": int(imap_port),
            "smtpHost": smtp_host.strip(),
            "smtpPort": int(smtp_port),
        }
        encrypted = _get_fernet().encrypt(json.dumps(data).encode("utf-8"))

        # Save to canonical active custom account path
        with open(CUSTOM_ACCOUNT_PATH, "wb") as f:
            f.write(encrypted)
        _secure_file_permissions(str(CUSTOM_ACCOUNT_PATH))

        # Also save to per-account specific path to preserve credentials across multi-account switches
        safe_name = "".join(c if c.isalnum() else "_" for c in email.strip().lower())
        specific_path = Path(CUSTOM_ACCOUNT_PATH).parent / f"custom_account_{safe_name}.json"
        with open(specific_path, "wb") as f:
            f.write(encrypted)
        _secure_file_permissions(str(specific_path))

        logger.info("Saved encrypted custom account credentials for %s", email)
        return True
    except Exception as exc:
        logger.error("Failed to save custom account: %s", exc)
        return False


def load_custom_account(expected_email: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load and decrypt custom mailbox credentials."""
    target_path = _account_path_for_email(expected_email)
    if not target_path.is_file():
        target_path = Path(CUSTOM_ACCOUNT_PATH)
        if not target_path.is_file():
            return None
    try:
        with open(target_path, "rb") as f:
            encrypted = f.read()
        decrypted = _get_fernet().decrypt(encrypted).decode("utf-8")
        data = json.loads(decrypted)
        if expected_email and data.get("email", "").lower() != expected_email.lower():
            safe_name = "".join(c if c.isalnum() else "_" for c in expected_email.lower())
            spec = Path(CUSTOM_ACCOUNT_PATH).parent / f"custom_account_{safe_name}.json"
            if spec.is_file() and spec != target_path:
                with open(spec, "rb") as f2:
                    dec2 = _get_fernet().decrypt(f2.read()).decode("utf-8")
                data2 = json.loads(dec2)
                if data2.get("email", "").lower() == expected_email.lower():
                    return data2
            return None
        return data
    except Exception as exc:
        logger.warning("Could not decrypt custom account file: %s", exc)
        return None


def clear_custom_account(email: Optional[str] = None) -> bool:
    """Remove custom account credentials file."""
    try:
        if email:
            safe_name = "".join(c if c.isalnum() else "_" for c in email.lower())
            specific = Path(CUSTOM_ACCOUNT_PATH).parent / f"custom_account_{safe_name}.json"
            if specific.is_file():
                try:
                    specific.unlink()
                except OSError:
                    pass
        if os.path.exists(CUSTOM_ACCOUNT_PATH):
            os.remove(CUSTOM_ACCOUNT_PATH)
        return True
    except Exception:
        return False
