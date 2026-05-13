# transport/smtp_sender.py — Authenticated SMTP email dispatch.
# Single responsibility: authenticate with Gmail or Yahoo SMTP and send a
# pre-built MIME message. Does not construct, encrypt, or inspect message content.
# Provider is detected from the sender's email domain.
# OAuth2 token acquisition is delegated to oauth2_gmail.py or oauth2_yahoo.py.
# Do not import from crypto/, mime/, portal/, certificates/, or kme/.

import base64
import smtplib
import ssl
from email.message import Message

from core.config          import APP_NAME
from transport.oauth2_gmail import get_access_token as _gmail_token, GmailAuthError
from transport.oauth2_yahoo import get_access_token as _yahoo_token, YahooAuthError


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
    """
    Raised when the sender's email domain does not match any supported provider.
    Callers should surface this to the user via settings_window.py — it indicates
    an unsupported account type, not a transient network failure.
    """
    pass


# -------------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------------

def _detect_provider(sender_email: str) -> str:
    """
    Derive the email provider from the sender's domain.

    Returns "gmail" or "yahoo".
    Raises UnknownProviderError if the domain is not in a known provider set.
    """
    try:
        domain = sender_email.split("@")[1].lower()
    except IndexError:
        raise UnknownProviderError(
            f"Malformed sender email address: '{sender_email}'. "
            "Expected format: user@domain.tld"
        )

    if domain in _GMAIL_DOMAINS:
        return "gmail"
    if domain in _YAHOO_DOMAINS:
        return "yahoo"

    raise UnknownProviderError(
        f"Email domain '{domain}' is not a supported {APP_NAME} provider. "
        "Supported providers: Gmail, Yahoo."
    )


def _build_xoauth2_string(user_email: str, access_token: str) -> str:
    """
    Build the XOAUTH2 authentication payload as a base64-encoded string.

    Format per RFC 6749 / Google and Yahoo SMTP XOAUTH2 spec:
        "user={email}\x01auth=Bearer {token}\x01\x01"
    Encoded as standard (not URL-safe) base64 with no line breaks.

    The result is passed directly to the raw SMTP AUTH XOAUTH2 command.
    """
    raw = f"user={user_email}\x01auth=Bearer {access_token}\x01\x01"
    return base64.b64encode(raw.encode()).decode()


def _get_smtp_credentials(provider: str, sender_email: str) -> tuple[str, str]:
    """
    Obtain the SMTP host and a valid access token for the detected provider.

    Returns (smtp_host, access_token).
    Raises SMTPSenderError wrapping any auth-layer exception.
    """
    try:
        if provider == "gmail":
            return _GMAIL_SMTP_HOST, _gmail_token()
        else:
            return _YAHOO_SMTP_HOST, _yahoo_token()
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
    Send a fully-built MIME message via SMTP using OAuth2 XOAUTH2 authentication.

    The mime_message is expected to arrive with From, To, and Subject headers
    already populated by compose_window.py. This function does not inspect or
    modify message content — it is pure transport.

    Provider (Gmail / Yahoo) is detected from the sender's email domain.
    Authentication uses XOAUTH2 with a token obtained from the appropriate
    oauth2_*.py module. The SMTP connection uses STARTTLS on port 587.

    Args:
        sender_email:    Sender's email address — used for provider detection
                         and as the SMTP envelope MAIL FROM address.
        recipient_email: Recipient's email address — used as SMTP envelope RCPT TO.
        mime_message:    Fully-assembled email.message.Message object from
                         mime/encapsulator.py. Headers must already be set.

    Raises:
        UnknownProviderError: Sender domain not supported.
        SMTPSenderError:      Auth failure, connection error, or any SMTP-level failure.
    """
    provider            = _detect_provider(sender_email)
    smtp_host, token    = _get_smtp_credentials(provider, sender_email)
    xoauth2_string      = _build_xoauth2_string(sender_email, token)

    try:
        with smtplib.SMTP(smtp_host, _SMTP_PORT, timeout=_SMTP_TIMEOUT_SEC) as smtp:
            smtp.ehlo()
            # Enforce certificate and hostname verification for OAuth-protected SMTP sessions.
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()   # Re-identify after STARTTLS upgrade — required by spec

            # Raw XOAUTH2 command — avoids smtplib's auth() abstraction which
            # does not handle XOAUTH2's error response format correctly on failure.
            code, response = smtp.docmd(
                "AUTH", f"XOAUTH2 {xoauth2_string}"
            )
            if code != 235:
                raise SMTPSenderError(
                    f"SMTP XOAUTH2 authentication rejected "
                    f"(code {code}): {response.decode(errors='replace')}"
                )

            smtp.sendmail(
                from_addr=  sender_email,
                to_addrs=   [recipient_email],
                msg=        mime_message.as_bytes(),
            )

    except SMTPSenderError:
        raise
    except smtplib.SMTPException as exc:
        raise SMTPSenderError(
            f"SMTP error while sending from '{sender_email}' "
            f"to '{recipient_email}': {exc}"
        ) from exc
    except OSError as exc:
        # Covers connection refused, DNS failure, timeout at socket level
        raise SMTPSenderError(
            f"Network error connecting to '{smtp_host}:{_SMTP_PORT}': {exc}"
        ) from exc
