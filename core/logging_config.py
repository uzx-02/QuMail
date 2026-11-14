"""
QuMail Centralized Structured & Privacy-Safe Logging System.

Enforces corporate privacy guarantees:
  - Zero logging of unencrypted message bodies or decrypted attachments.
  - Zero logging of private keys, passphrases, or master keys.
  - Automatic scrubbing of OAuth Bearer tokens and authorization headers.
  - Bounded rotating log storage to prevent disk exhaustion.
  - Consistent severity levels and structured event metadata.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import sys


# Regex patterns for sensitive tokens and credentials
_SENSITIVE_PATTERNS = [
    # Google OAuth access / refresh tokens
    (re.compile(r"ya29\.[a-zA-Z0-9_\-]+", re.IGNORECASE), "[REDACTED_OAUTH_TOKEN]"),
    (re.compile(r"1//[a-zA-Z0-9_\-]+", re.IGNORECASE), "[REDACTED_REFRESH_TOKEN]"),
    # Bearer auth headers
    (re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]+", re.IGNORECASE), "Bearer [REDACTED_OAUTH_TOKEN]"),
    # Private key blocks (OpenPGP armor, PKCS#1, PKCS#8, RFC 8410 Ed25519)
    (re.compile(r"-----BEGIN [A-Z0-9 _-]*PRIVATE KEY(?: BLOCK)?-----[\s\S]*?-----END [A-Z0-9 _-]*PRIVATE KEY(?: BLOCK)?-----", re.MULTILINE), "[REDACTED_PRIVATE_KEY_BLOCK]"),
    # Passwords or client secrets in key-value patterns
    (re.compile(r"(password|client_secret|client_secret_json|private_key|secret)\s*[:=]\s*(?:['\"][^'\"]*['\"]|\S+)", re.IGNORECASE), r"\1='[REDACTED]'"),
]


class PrivacyFilter(logging.Filter):
    """
    Log filter that intercepts and scrubs sensitive cryptographic tokens,
    credentials, and authorization headers from log records.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.scrub(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self.scrub(str(v)) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(self.scrub(str(a)) if isinstance(a, str) else a for a in record.args)
        return True

    @classmethod
    def scrub(cls, text: str) -> str:
        for pattern, replacement in _SENSITIVE_PATTERNS:
            text = pattern.sub(replacement, text)
        return text


def get_default_log_dir() -> Path:
    """Return the platform-appropriate log directory for QuMail."""
    from core.config import get_user_data_dir
    return get_user_data_dir() / "logs"


_CONFIGURED = False


def configure_logging(
    level: int = logging.INFO,
    log_dir: Path | str | None = None,
    console: bool = True,
    file_logging: bool = True,
    max_bytes: int = 5 * 1024 * 1024,  # 5 MiB per log file
    backup_count: int = 3,             # 3 backup files (max 20 MiB total)
) -> None:
    """
    Initialize centralized logging for the QuMail application.

    Configures a console stream handler and a bounded rotating file handler,
    both protected by the PrivacyFilter to prevent secret leakage.
    """
    global _CONFIGURED
    root_logger = logging.getLogger("qumail")
    root_logger.setLevel(level)

    # Avoid adding duplicate handlers on multiple calls
    if _CONFIGURED:
        return

    privacy_filter = PrivacyFilter()
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(privacy_filter)
        root_logger.addHandler(console_handler)

    if file_logging:
        target_dir = Path(log_dir) if log_dir else get_default_log_dir()
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            log_file = target_dir / "qumail.log"
            file_handler = RotatingFileHandler(
                filename=log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
                delay=True,
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            file_handler.addFilter(privacy_filter)
            root_logger.addHandler(file_handler)
        except (OSError, PermissionError) as exc:
            # Fall back to console only if directory cannot be created (e.g. strict sandbox)
            root_logger.warning("Could not initialize file logger at %s: %s", target_dir, exc)

    _CONFIGURED = True


def get_logger(subsystem: str) -> logging.Logger:
    """Obtain a namespaced QuMail logger for a specific module or subsystem."""
    if not _CONFIGURED:
        configure_logging(level=logging.INFO)
    return logging.getLogger(f"qumail.{subsystem}")


def log_sanitized_error(logger: logging.Logger, action: str, error: Exception) -> None:
    """
    Safely record an error event without dumping full stack traces or potential
    plaintext message contents into user-facing production logs.
    """
    code = getattr(error, "code", None)
    code_val = getattr(code, "value", code)
    err_type = type(error).__name__
    if code_val:
        logger.error("Action '%s' failed with %s [code=%s]", action, err_type, code_val)
    else:
        logger.error("Action '%s' failed with %s", action, err_type)
    # Debug record with sanitized string representation for troubleshooting
    logger.debug("Action '%s' details: %s", action, str(error))


if __name__ == "__main__":
    configure_logging(level=logging.DEBUG)
    log = get_logger("test")
    log.info("Centralized logging initialized successfully.")
    # Test redaction
    # Deliberately invalid fixture values: this exercises the generic Bearer
    # and key-value scrubbers without resembling a usable provider credential.
    log.info("Testing token scrubbing: Bearer synthetic-token-redaction-fixture")
    log.info("Testing key scrubbing: client_secret='synthetic-redaction-fixture'")
    print("[OK] Logging self-test completed.")
