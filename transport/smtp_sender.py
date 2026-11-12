# transport/smtp_sender.py — Authenticated SMTP email dispatch.
# Single responsibility: authenticate with Gmail or Yahoo SMTP and send a
# pre-built MIME message. Does not construct, encrypt, or inspect message content.
# Provider is detected from the sender's email domain.
# OAuth2 token acquisition is delegated to oauth2_gmail.py or oauth2_yahoo.py.
# Do not import from crypto/, mime/, portal/, certificates/, or kme/.

from __future__ import annotations

import base64
import logging
import smtplib
import ssl
from email.message import Message

from core.config import APP_NAME
from transport.oauth2_gmail import get_access_token as get_gmail_token, GmailAuthError
from transport.oauth2_yahoo import get_access_token as get_yahoo_token, YahooAuthError

logger = logging.getLogger("transport.smtp_sender")

# -------------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------------

_SMTP_PORT:        int  = 587          # STARTTLS — supported by both providers
_SMTP_TIMEOUT_SEC: int  = 30           # Seconds before SMTP connection is considered hung

_GMAIL_SMTP_HOST:  str  = "smtp.gmail.com"
_YAHOO_SMTP_HOST:  str  = "smtp.mail.yahoo.com"

# Domain sets used for provider detection from sender email address
_GMAIL_DOMAINS: frozenset[str] = frozenset({"gmail.com", "googlemail.com"})
_YAHOO_DOMAINS: frozenset[str] = frozenset({
    "yahoo.com", "yahoo.co.uk", "yahoo.co.in", "yahoo.com.au",
    "yahoo.ca",  "yahoo.de",    "yahoo.fr",    "yahoo.es",
    "ymail.com", "rocketmail.com",
})


# -------------------------------------------------------------------------
# Custom Exceptions
# -------------------------------------------------------------------------

class SMTPSenderError(Exception):
    """Raised when the SMTP send operation fails for any reason."""
    pass


class UnknownProviderError(SMTPSenderError):
    """Raised when the sender's email domain does not match any supported provider."""
    pass


# -------------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------------

def _detect_provider(sender_email: str) -> str:
    """Derive the email provider from the sender's domain."""
    try:
        domain = sender_email.split("@")[1].lower()
    except IndexError:
        raise UnknownProviderError(
            f"Malformed sender email address: '{sender_email}'. Expected format: user@domain.tld"
        )

    if domain in _GMAIL_DOMAINS:
        return "gmail"
    if domain in _YAHOO_DOMAINS:
        return "yahoo"

    raise UnknownProviderError(
        f"Email domain '{domain}' is not a supported {APP_NAME} provider. Supported providers: Gmail, Yahoo."
    )


def _build_xoauth2_string(user_email: str, access_token: str) -> str:
    """
    Build the XOAUTH2 authentication payload as a base64-encoded string.
    Format per RFC 6749: user={email}\x01auth=Bearer {token}\x01\x01
    """
    raw = f"user={user_email}\x01auth=Bearer {access_token}\x01\x01"
    return base64.b64encode(raw.encode()).decode()


def _get_smtp_credentials(provider: str, sender_email: str) -> tuple[str, str]:
    """Obtain the SMTP host and a valid access token for the detected provider."""
    try:
        if provider == "gmail":
            return _GMAIL_SMTP_HOST, get_gmail_token()
        else:
            return _YAHOO_SMTP_HOST, get_yahoo_token()
    except (GmailAuthError, YahooAuthError) as exc:
        raise SMTPSenderError(
            f"OAuth2 token acquisition failed for '{sender_email}': {exc}"
        ) from exc


# -------------------------------------------------------------------------
# Public interface
# -------------------------------------------------------------------------

def send_email(
    sender_email:    str,
    recipient_email: str,
    mime_message:    Message,
) -> None:
    """
    Send a fully-built MIME message via SMTP using OAuth2 XOAUTH2 authentication
    or custom TLS-encrypted mailbox credentials.
    """
    from transport.custom_mailbox import load_custom_account
    custom = load_custom_account(sender_email)

    # 1. Custom IMAP/SMTP Mailbox (App Password or Enterprise TLS)
    if custom:
        smtp_host = custom.get("smtpHost") or "smtp.gmail.com"
        smtp_port = int(custom.get("smtpPort") or 587)
        password  = custom.get("password", "")
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=_SMTP_TIMEOUT_SEC) as smtp:
                smtp.ehlo()
                if smtp.has_extn("STARTTLS"):
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                smtp.login(sender_email, password)
                smtp.sendmail(
                    from_addr=sender_email,
                    to_addrs=[recipient_email],
                    msg=mime_message.as_bytes(),
                )
                logger.info("Custom SMTP message sent to %s via %s", recipient_email, smtp_host)
                return
        except Exception as exc:
            raise SMTPSenderError(f"Custom SMTP dispatch failed for '{sender_email}' on '{smtp_host}': {exc}") from exc

    # 2. Automated Google / Yahoo OAuth2 via standard XOAUTH2
    provider = _detect_provider(sender_email)
    smtp_host, access_token = _get_smtp_credentials(provider, sender_email)
    b64_auth = _build_xoauth2_string(sender_email, access_token)

    # Primary Transport: Port 587 STARTTLS
    p587_err: Exception | None = None
    try:
        with smtplib.SMTP(smtp_host, _SMTP_PORT, timeout=_SMTP_TIMEOUT_SEC) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            code, resp = smtp.docmd("AUTH", f"XOAUTH2 {b64_auth}")
            if code == 334:
                code, resp = smtp.docmd("")

            if code != 235:
                raise SMTPSenderError(
                    f"SMTP XOAUTH2 authentication rejected (code {code}): {resp.decode(errors='replace')}"
                )

            smtp.sendmail(
                from_addr=sender_email,
                to_addrs=[recipient_email],
                msg=mime_message.as_bytes(),
            )
            logger.info("Dispatched email via SMTP port 587 to %s", recipient_email)
            return
    except (SMTPSenderError, GmailAuthError, YahooAuthError):
        raise
    except Exception as exc:
        p587_err = exc
        logger.warning("Port 587 STARTTLS failed (%s), trying Port 465 fallback...", exc)

    # Secondary Transport: Port 465 Implicit SSL fallback
    try:
        with smtplib.SMTP_SSL(smtp_host, 465, context=ssl.create_default_context(), timeout=_SMTP_TIMEOUT_SEC) as smtp:
            smtp.ehlo()
            code, resp = smtp.docmd("AUTH", f"XOAUTH2 {b64_auth}")
            if code == 334:
                code, resp = smtp.docmd("")

            if code != 235:
                raise SMTPSenderError(
                    f"SMTP XOAUTH2 authentication rejected on port 465 (code {code}): {resp.decode(errors='replace')}"
                )

            smtp.sendmail(
                from_addr=sender_email,
                to_addrs=[recipient_email],
                msg=mime_message.as_bytes(),
            )
            logger.info("Dispatched email via SMTP port 465 to %s", recipient_email)
            return
    except (SMTPSenderError, GmailAuthError, YahooAuthError):
        raise
    except Exception as p465_err:
        final_err = p465_err if p587_err is None else p587_err
        raise SMTPSenderError(
            f"SMTP dispatch failed for '{sender_email}' to '{recipient_email}': {final_err}"
        ) from final_err
