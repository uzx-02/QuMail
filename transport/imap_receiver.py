# transport/imap_receiver.py — Authenticated IMAP email retrieval.
# Single responsibility: authenticate with Gmail or Yahoo IMAP and fetch incoming
# messages from the inbox. Returns structured InboxMessage objects containing the
# raw MIME message for mime/decapsulator.py to parse downstream.
# Provider is detected from the account's email domain.
# OAuth2 token acquisition is delegated to oauth2_gmail.py or oauth2_yahoo.py.
# Do not import from crypto/, mime/, portal/, certificates/, kme/, or smtp_sender.py.

import base64
import re
import email
import imaplib
import ssl
from dataclasses  import dataclass
from email.message import Message

from core.config            import APP_NAME
from transport.oauth2_gmail import get_access_token as _gmail_token, GmailAuthError
from transport.oauth2_yahoo import get_access_token as _yahoo_token, YahooAuthError


# -------------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------------

_IMAP_PORT:        int = 993       # Implicit TLS — standard for IMAP4
_IMAP_TIMEOUT_SEC: int = 15        # Seconds before IMAP connection is considered hung
_INBOX_FOLDER:     str = "INBOX"   # Default folder — not configurable in v1

_GMAIL_IMAP_HOST: str = "imap.gmail.com"
_YAHOO_IMAP_HOST: str = "imap.mail.yahoo.com"

# Domain sets used for provider detection from account email address.
# Intentionally mirrored from smtp_sender.py — not imported to avoid lateral dependency.
_GMAIL_DOMAINS: frozenset[str] = frozenset({"gmail.com", "googlemail.com"})
_YAHOO_DOMAINS: frozenset[str] = frozenset({
    "yahoo.com", "yahoo.co.uk", "yahoo.co.in", "yahoo.com.au",
    "yahoo.ca",  "yahoo.de",    "yahoo.fr",    "yahoo.es",
    "ymail.com", "rocketmail.com",
})


# -------------------------------------------------------------------------
# Custom Exceptions
# -------------------------------------------------------------------------

class IMAPReceiverError(Exception):
    """Raised when an IMAP fetch operation fails for any reason."""
    pass


class UnknownProviderError(IMAPReceiverError):
    """
    Raised when the account's email domain does not match any supported provider.
    Callers should surface this to the user via settings_window.py — it indicates
    an unsupported account type, not a transient network failure.
    """
    pass


class MessageNotFoundError(IMAPReceiverError):
    """
    Raised by fetch_message() when the requested UID does not exist in INBOX.
    Distinct from IMAPReceiverError so inbox_view.py can handle a missing message
    gracefully (e.g. deleted on server) without treating it as a connection failure.
    """
    pass


# -------------------------------------------------------------------------
# Result model
# -------------------------------------------------------------------------

@dataclass
class InboxMessage:
    """
    A fetched email message, structured for consumption by inbox_view.py.

    uid     : IMAP UID string — stable identifier for this message on the server.
    subject : Decoded Subject header, or empty string if absent.
    sender  : From header value as a plain string.
    date    : Date header value as a plain string.
    message : Parsed email.message.Message object — passed to mime/decapsulator.py
              to extract ciphertext and metadata for decryption.
    """
    uid:     str
    subject: str
    sender:  str
    date:    str
    message: Message


# -------------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------------

def _detect_provider(account_email: str) -> str:
    """
    Derive the email provider from the account's email domain.

    Returns "gmail" or "yahoo".
    Raises UnknownProviderError if the domain is not in a known provider set.
    """
    try:
        domain = account_email.split("@")[1].lower()
    except IndexError:
        raise UnknownProviderError(
            f"Malformed account email address: '{account_email}'. "
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


def _build_xoauth2_string(account_email: str, access_token: str) -> str:
    """
    Build the XOAUTH2 authentication payload as a base64-encoded bytes object.

    Format per the IMAP XOAUTH2 spec:
        "user={email}\\x01auth=Bearer {token}\\x01\\x01"

    imaplib's authenticate() callback must return bytes — the result is
    returned as bytes rather than str to match imaplib's expected signature.
    """
    raw = f"user={account_email}\x01auth=Bearer {access_token}\x01\x01"
    return base64.b64encode(raw.encode())


def _get_imap_credentials(provider: str, account_email: str) -> tuple[str, str]:
    """
    Obtain the IMAP host and a valid access token for the detected provider.

    Returns (imap_host, access_token).
    Raises IMAPReceiverError wrapping any auth-layer exception.
    """
    try:
        if provider == "gmail":
            return _GMAIL_IMAP_HOST, _gmail_token()
        else:
            return _YAHOO_IMAP_HOST, _yahoo_token()
    except (GmailAuthError, YahooAuthError) as exc:
        raise IMAPReceiverError(
            f"OAuth2 token acquisition failed for '{account_email}': {exc}"
        ) from exc


def _open_imap_connection(imap_host: str, account_email: str, access_token: str) -> imaplib.IMAP4_SSL:
    """
    Open an authenticated IMAP4_SSL connection and return the ready client.

    Uses XOAUTH2 via imaplib's authenticate() — the callback returns the
    pre-built XOAUTH2 bytes, which imaplib base64-encodes again internally.
    To avoid double-encoding, the callback returns already-encoded bytes and
    imaplib is called with the raw mechanism string.

    Raises IMAPReceiverError on connection or authentication failure.
    """
    xoauth2_bytes = _build_xoauth2_string(account_email, access_token)

    try:
        ssl_ctx = ssl.create_default_context()
        imap = imaplib.IMAP4_SSL(
            imap_host,
            _IMAP_PORT,
            ssl_context=ssl_ctx,
            timeout=_IMAP_TIMEOUT_SEC,
        )
        # Enforce timeout on the underlying SSL socket for every subsequent read/write.
        # Without this, the timeout only applies to the initial TCP connection.
        try:
            imap.socket().settimeout(_IMAP_TIMEOUT_SEC)
        except Exception:  # noqa: BLE001
            pass
        # imaplib.authenticate() base64-encodes the return value of the callback.
        # Since _build_xoauth2_string() already returns base64 bytes, the callback
        # decodes back to the original raw string so imaplib re-encodes correctly.
        imap.authenticate("XOAUTH2", lambda _: base64.b64decode(xoauth2_bytes))
        return imap
    except imaplib.IMAP4.error as exc:
        raise IMAPReceiverError(
            f"IMAP authentication failed for '{account_email}' "
            f"on '{imap_host}': {exc}"
        ) from exc
    except OSError as exc:
        raise IMAPReceiverError(
            f"Network error connecting to '{imap_host}:{_IMAP_PORT}': {exc}"
        ) from exc


def _parse_raw_message(uid: str, raw_bytes: bytes) -> InboxMessage:
    """
    Parse raw RFC 822 message bytes into an InboxMessage dataclass.

    Decodes the Subject header using email.header.decode_header to handle
    encoded-word syntax (e.g. =?UTF-8?B?...?=) correctly.
    """
    msg = email.message_from_bytes(raw_bytes)

    # Decode encoded-word Subject if present — plain ASCII subjects pass through unchanged
    raw_subject = msg.get("Subject", "")
    subject_parts = email.header.decode_header(raw_subject)
    subject = "".join(
        part.decode(enc or "utf-8") if isinstance(part, bytes) else part
        for part, enc in subject_parts
    )

    return InboxMessage(
        uid=     uid,
        subject= subject,
        sender=  msg.get("From", ""),
        date=    msg.get("Date", ""),
        message= msg,
    )


# -------------------------------------------------------------------------
# Public interface
# -------------------------------------------------------------------------

def fetch_inbox(account_email: str, max_count: int = 50) -> list[InboxMessage]:
    """
    Fetch the most recent messages from the account's INBOX.

    Connects to the provider's IMAP server, selects INBOX in read-only mode,
    and retrieves the last `max_count` messages by UID in reverse chronological
    order (newest first). Each message is parsed into an InboxMessage containing
    the full email.message.Message object for mime/decapsulator.py.

    Args:
        account_email: The authenticated account address — used for provider
                       detection and XOAUTH2 construction.
        max_count:     Maximum number of messages to return. Fetching stops
                       early if fewer messages exist in INBOX.

    Returns:
        List of InboxMessage objects, newest first.
        Empty list if INBOX is empty.

    Raises:
        UnknownProviderError: Account domain not supported.
        IMAPReceiverError:    Auth failure, connection error, or IMAP-level failure.
    """
    provider           = _detect_provider(account_email)
    imap_host, token   = _get_imap_credentials(provider, account_email)

    try:
        with _open_imap_connection(imap_host, account_email, token) as imap:
            # Read-only SELECT — avoids unintentionally marking messages as \Seen
            imap.select(_INBOX_FOLDER, readonly=True)

            status, data = imap.uid("SEARCH", None, "ALL")
            if status != "OK":
                raise IMAPReceiverError(
                    f"INBOX UID search failed with status: '{status}'"
                )

            all_uids: list[str] = data[0].decode().split() if data[0] else []
            if not all_uids:
                return []

            # Take the last max_count UIDs and reverse for newest-first ordering
            selected_uids = all_uids[-max_count:][::-1]
            if not selected_uids:
                return []

            query_uids = ",".join(selected_uids)
            status, fetch_data = imap.uid("FETCH", query_uids, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")

            if status != "OK" or not fetch_data:
                return []

            messages: list[InboxMessage] = []

            for item in fetch_data:
                if isinstance(item, tuple) and len(item) == 2:
                    header_meta, raw_bytes = item

                    # Extract UID from the IMAP metadata line.
                    meta_str = header_meta.decode(errors='ignore')
                    match = re.search(r'UID\s+(\d+)', meta_str, re.IGNORECASE)

                    if match:
                        uid_str = match.group(1)
                        if uid_str in selected_uids:
                            messages.append(_parse_raw_message(uid_str, raw_bytes))

            # Maintain reverse-chronological order to match the selected_uids array
            messages.sort(key=lambda m: selected_uids.index(m.uid))
            return messages

    except IMAPReceiverError:
        raise
    except imaplib.IMAP4.error as exc:
        raise IMAPReceiverError(f"IMAP error during inbox fetch: {exc}") from exc


def fetch_message(account_email: str, uid: str) -> InboxMessage:
    """
    Fetch a single message from INBOX by its IMAP UID.

    Used by inbox_view.py when the user opens a specific message. The returned
    InboxMessage.message object is passed to mime/decapsulator.py to extract
    ciphertext and metadata for tqr.decrypt().

    Args:
        account_email: The authenticated account address.
        uid:           IMAP UID string as returned in InboxMessage.uid from
                       a prior fetch_inbox() call.

    Returns:
        A single InboxMessage for the requested UID.

    Raises:
        UnknownProviderError: Account domain not supported.
        MessageNotFoundError: No message with the given UID exists in INBOX.
        IMAPReceiverError:    Auth failure, connection error, or IMAP-level failure.
    """
    provider           = _detect_provider(account_email)
    imap_host, token   = _get_imap_credentials(provider, account_email)

    try:
        with _open_imap_connection(imap_host, account_email, token) as imap:
            imap.select(_INBOX_FOLDER, readonly=True)

            status, msg_data = imap.uid("FETCH", uid, "(RFC822)")
            if status != "OK" or not msg_data or msg_data[0] is None:
                raise MessageNotFoundError(
                    f"No message with UID '{uid}' found in INBOX for '{account_email}'. "
                    "It may have been deleted on the server."
                )

            raw_bytes = msg_data[0][1]
            return _parse_raw_message(uid, raw_bytes)

    except (IMAPReceiverError, MessageNotFoundError):
        raise
    except imaplib.IMAP4.error as exc:
        raise IMAPReceiverError(f"IMAP error fetching UID '{uid}': {exc}") from exc
