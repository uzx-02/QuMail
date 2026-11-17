# transport/imap_receiver.py — Authenticated IMAP email retrieval.
# Single responsibility: authenticate with Gmail or Yahoo IMAP and fetch incoming
# messages from the inbox. Returns structured InboxMessage objects containing the
# raw MIME message for mime/decapsulator.py to parse downstream.
# Provider is detected from the account's email domain.
# OAuth2 token acquisition is delegated to oauth2_gmail.py or oauth2_yahoo.py.
# Do not import from crypto/, mime/, portal/, certificates/, kme/, or smtp_sender.py.

import base64
import logging
import re
import email
import email.header
import email.utils
import imaplib
import ssl
from dataclasses import dataclass
from email.message import Message
from typing import Optional

logger = logging.getLogger(__name__)

from core.config import APP_NAME
from transport.oauth2_gmail import get_access_token as get_gmail_token, GmailAuthError
from transport.oauth2_yahoo import get_access_token as get_yahoo_token, YahooAuthError

class IMAPReceiverError(Exception):
    """Raised when the IMAP receive operation fails for any reason."""
    pass

class UnknownProviderError(IMAPReceiverError):
    """Raised when the account domain does not match any supported provider."""
    pass


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
    starred : True if IMAP \\Flagged flag is set on the server.
    seen    : True if IMAP \\Seen flag is set on the server.
    folder  : Local mailbox folder identity ('inbox', 'spam', 'trash', etc.).
    """
    uid:     str
    subject: str
    sender:  str
    date:    str
    message: Message
    starred: bool = False
    seen:    bool = True
    folder:  str = "inbox"


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
            return _GMAIL_IMAP_HOST, get_gmail_token(account_email, interactive=False)
        else:
            return _YAHOO_IMAP_HOST, get_yahoo_token()
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


def parse_rfc2047_sender(raw_from: str) -> tuple[str, str]:
    """
    Decodes RFC 2047 MIME encoded-word sender names.
    E.g.: '=?UTF-8?Q?LinkedIn=20Job=20Alerts?= <jobalerts-noreply@linkedin.com>'
    Returns: ('LinkedIn Job Alerts', 'jobalerts-noreply@linkedin.com')
    """
    if not raw_from or not str(raw_from).strip():
        return "Unknown Sender", ""
    raw_str = str(raw_from).strip()
    display_name, email_addr = email.utils.parseaddr(raw_str)
    decoded_parts = []
    try:
        for part, enc in email.header.decode_header(display_name or ""):
            if isinstance(part, bytes):
                decoded_parts.append(part.decode(enc or "utf-8", errors="ignore"))
            else:
                decoded_parts.append(str(part))
        clean_name = "".join(decoded_parts).strip().strip('"\'')
    except Exception:
        clean_name = display_name or ""

    if not clean_name:
        clean_name = email_addr.split("@")[0] if email_addr else raw_str

    return clean_name, email_addr


def _parse_raw_message(uid: str, raw_bytes: bytes, starred: bool = False, seen: bool = True, folder: str = "inbox") -> InboxMessage:
    """
    Parse raw RFC 822 message bytes into an InboxMessage dataclass.

    Decodes both the Subject and From headers using email.header.decode_header
    to handle encoded-word syntax (e.g. =?UTF-8?B?...?= or =?UTF-8?Q?...?=) correctly.
    """
    msg = email.message_from_bytes(raw_bytes)

    # Decode encoded-word Subject if present — plain ASCII subjects pass through unchanged
    raw_subject = msg.get("Subject", "")
    subject_parts = email.header.decode_header(raw_subject)
    subject = "".join(
        part.decode(enc or "utf-8", errors="ignore") if isinstance(part, bytes) else str(part)
        for part, enc in subject_parts
    )

    # Decode encoded-word Sender / From header
    raw_from = msg.get("From", "")
    clean_name, email_addr = parse_rfc2047_sender(raw_from)
    sender_str = f'"{clean_name}" <{email_addr}>' if email_addr and clean_name else (clean_name or raw_from)

    return InboxMessage(
        uid=     uid,
        subject= subject,
        sender=  sender_str,
        date=    msg.get("Date", ""),
        message= msg,
        starred= starred,
        seen=    seen,
        folder=  folder,
    )


def _connect_imap(account_email: str) -> imaplib.IMAP4_SSL:
    """
    Establish an authenticated IMAP4_SSL connection for either custom IMAP or XOAUTH2.
    """
    from transport.custom_mailbox import load_custom_account
    custom = load_custom_account(account_email)
    ssl_ctx = ssl.create_default_context()

    if custom:
        imap_host = custom.get("imapHost") or "imap.gmail.com"
        imap_port = custom.get("imapPort") or 993
        password = custom.get("password", "")
        try:
            imap = imaplib.IMAP4_SSL(
                imap_host,
                int(imap_port),
                ssl_context=ssl_ctx,
                timeout=_IMAP_TIMEOUT_SEC,
            )
            imap.login(account_email, password)
            return imap
        except Exception as exc:
            raise IMAPReceiverError(f"Custom IMAP login failed for '{account_email}' on '{imap_host}': {exc}") from exc
    else:
        provider = _detect_provider(account_email)
        imap_host, access_token = _get_imap_credentials(provider, account_email)
        xoauth2_bytes = _build_xoauth2_string(account_email, access_token)
        try:
            imap = imaplib.IMAP4_SSL(
                imap_host,
                _IMAP_PORT,
                ssl_context=ssl_ctx,
                timeout=_IMAP_TIMEOUT_SEC,
            )
            try:
                imap.socket().settimeout(_IMAP_TIMEOUT_SEC)
            except Exception:
                pass
            imap.authenticate("XOAUTH2", lambda _: base64.b64decode(xoauth2_bytes))
            return imap
        except (GmailAuthError, YahooAuthError) as auth_err:
            raise IMAPReceiverError(f"OAuth authentication failed for '{account_email}': {auth_err}") from auth_err
        except Exception as exc:
            raise IMAPReceiverError(f"IMAP connection failed for '{account_email}' on '{imap_host}': {exc}") from exc


def _find_folder(imap: imaplib.IMAP4_SSL, folder_type: str) -> Optional[str]:
    """
    Discover the mailbox folder name for 'spam', 'starred', or 'sent' on the IMAP server.
    """
    candidates = []
    if folder_type == "spam":
        candidates = ['"[Gmail]/Spam"', '"[Google Mail]/Spam"', 'Junk', 'Spam', '"Junk Email"', '"Bulk Mail"']
    elif folder_type == "starred":
        candidates = ['"[Gmail]/Starred"', '"[Google Mail]/Starred"', 'Starred']
    elif folder_type == "sent":
        candidates = ['"[Gmail]/Sent Mail"', '"[Google Mail]/Sent Mail"', '"Sent Mail"', 'Sent', '"Sent Messages"', '"Sent Items"']

    try:
        status, folder_lines = imap.list()
        if status == "OK" and folder_lines:
            for raw_line in folder_lines:
                if not raw_line:
                    continue
                line_str = raw_line.decode(errors="ignore") if isinstance(raw_line, bytes) else str(raw_line)
                lower_line = line_str.lower()
                if folder_type == "spam" and ("\\junk" in lower_line or "\\spam" in lower_line):
                    parts = line_str.rsplit('"', 2)
                    if len(parts) >= 2:
                        return f'"{parts[1]}"'
                    return line_str.split()[-1]
                elif folder_type == "starred" and ("\\flagged" in lower_line or "\\starred" in lower_line):
                    parts = line_str.rsplit('"', 2)
                    if len(parts) >= 2:
                        return f'"{parts[1]}"'
                    return line_str.split()[-1]
                elif folder_type == "sent" and ("\\sent" in lower_line or "sent mail" in lower_line or "sent items" in lower_line):
                    parts = line_str.rsplit('"', 2)
                    if len(parts) >= 2:
                        return f'"{parts[1]}"'
                    return line_str.split()[-1]
    except Exception:
        pass

    for cand in candidates:
        try:
            status, _ = imap.select(cand, readonly=True)
            if status == "OK":
                return cand
        except Exception:
            continue
    return None


# -------------------------------------------------------------------------
# Public interface
# -------------------------------------------------------------------------

def fetch_inbox(account_email: str, max_count: int = 50) -> list[InboxMessage]:
    """
    Fetch the most recent messages from the account's INBOX.
    """
    imap = _connect_imap(account_email)

    try:
        with imap:
            # Read-only SELECT — avoids unintentionally marking messages as \Seen
            imap.select(_INBOX_FOLDER, readonly=True)

            # Query authoritative FLAGGED UIDs from server for Starred synchronization
            flagged_uids: set[str] = set()
            try:
                f_status, f_data = imap.uid("SEARCH", None, "FLAGGED")
                if f_status == "OK" and f_data and f_data[0]:
                    flagged_uids = set(f_data[0].decode().split())
            except Exception:
                pass

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
            status, fetch_data = imap.uid("FETCH", query_uids, "(FLAGS BODY.PEEK[])")

            if status != "OK" or not fetch_data:
                return []

            messages: list[InboxMessage] = []

            for item in fetch_data:
                if isinstance(item, tuple) and len(item) == 2:
                    header_meta, raw_bytes = item

                    # Extract UID and IMAP FLAGS from metadata line.
                    meta_str = header_meta.decode(errors='ignore')
                    match = re.search(r'UID\s+(\d+)', meta_str, re.IGNORECASE)

                    if match:
                        uid_str = match.group(1)
                        if uid_str in selected_uids:
                            flags_match = re.search(r'FLAGS\s*\(([^)]*)\)', meta_str, re.IGNORECASE)
                            flags_str = flags_match.group(1).lower() if flags_match else ""
                            is_starred = (uid_str in flagged_uids) or ("\\flagged" in flags_str) or ("starred" in flags_str)
                            is_seen = "\\seen" in flags_str
                            messages.append(_parse_raw_message(uid_str, raw_bytes, starred=is_starred, seen=is_seen, folder="inbox"))

            # Maintain reverse-chronological order to match the selected_uids array
            messages.sort(key=lambda m: selected_uids.index(m.uid))
            return messages

    except IMAPReceiverError:
        raise
    except imaplib.IMAP4.error as exc:
        raise IMAPReceiverError(f"IMAP error during inbox fetch: {exc}") from exc


def fetch_spam(account_email: str, max_count: int = 50) -> list[InboxMessage]:
    """
    Fetch messages from the account's Spam / Junk folder.
    """
    try:
        imap = _connect_imap(account_email)
    except Exception as exc:
        logger.debug("Could not connect to IMAP for spam fetch: %s", exc)
        return []

    try:
        with imap:
            spam_folder = _find_folder(imap, "spam")
            if not spam_folder:
                return []

            status, _ = imap.select(spam_folder, readonly=True)
            if status != "OK":
                return []

            status, data = imap.uid("SEARCH", None, "ALL")
            if status != "OK":
                return []

            all_uids: list[str] = data[0].decode().split() if data[0] else []
            if not all_uids:
                return []

            selected_uids = all_uids[-max_count:][::-1]
            if not selected_uids:
                return []

            query_uids = ",".join(selected_uids)
            status, fetch_data = imap.uid("FETCH", query_uids, "(FLAGS BODY.PEEK[])")
            if status != "OK" or not fetch_data:
                return []

            messages: list[InboxMessage] = []
            for item in fetch_data:
                if isinstance(item, tuple) and len(item) == 2:
                    header_meta, raw_bytes = item
                    meta_str = header_meta.decode(errors='ignore')
                    match = re.search(r'UID\s+(\d+)', meta_str, re.IGNORECASE)
                    if match:
                        uid_str = match.group(1)
                        if uid_str in selected_uids:
                            flags_match = re.search(r'FLAGS\s*\(([^)]*)\)', meta_str, re.IGNORECASE)
                            flags_str = flags_match.group(1).lower() if flags_match else ""
                            is_starred = ("\\flagged" in flags_str) or ("starred" in flags_str)
                            is_seen = "\\seen" in flags_str
                            messages.append(_parse_raw_message(uid_str, raw_bytes, starred=is_starred, seen=is_seen, folder="spam"))

            messages.sort(key=lambda m: selected_uids.index(m.uid))
            return messages
    except Exception as exc:
        logger.debug("IMAP spam fetch note for %s: %s", account_email, exc)
        return []


def fetch_starred(account_email: str, max_count: int = 50) -> list[InboxMessage]:
    """
    Fetch messages from the account's Starred folder (e.g. [Gmail]/Starred or FLAGGED search).
    """
    try:
        imap = _connect_imap(account_email)
    except Exception as exc:
        logger.debug("Could not connect to IMAP for starred fetch: %s", exc)
        return []

    try:
        with imap:
            starred_folder = _find_folder(imap, "starred")
            if starred_folder:
                status, _ = imap.select(starred_folder, readonly=True)
            else:
                status, _ = imap.select(_INBOX_FOLDER, readonly=True)

            if status != "OK":
                return []

            if starred_folder:
                status, data = imap.uid("SEARCH", None, "ALL")
            else:
                status, data = imap.uid("SEARCH", None, "FLAGGED")

            if status != "OK":
                return []

            all_uids: list[str] = data[0].decode().split() if data[0] else []
            if not all_uids:
                return []

            selected_uids = all_uids[-max_count:][::-1]
            if not selected_uids:
                return []

            query_uids = ",".join(selected_uids)
            status, fetch_data = imap.uid("FETCH", query_uids, "(FLAGS BODY.PEEK[])")
            if status != "OK" or not fetch_data:
                return []

            messages: list[InboxMessage] = []
            for item in fetch_data:
                if isinstance(item, tuple) and len(item) == 2:
                    header_meta, raw_bytes = item
                    meta_str = header_meta.decode(errors='ignore')
                    match = re.search(r'UID\s+(\d+)', meta_str, re.IGNORECASE)
                    if match:
                        uid_str = match.group(1)
                        if uid_str in selected_uids:
                            flags_match = re.search(r'FLAGS\s*\(([^)]*)\)', meta_str, re.IGNORECASE)
                            flags_str = flags_match.group(1).lower() if flags_match else ""
                            is_seen = "\\seen" in flags_str
                            messages.append(_parse_raw_message(uid_str, raw_bytes, starred=True, seen=is_seen, folder="inbox"))

            messages.sort(key=lambda m: selected_uids.index(m.uid))
            return messages
    except Exception as exc:
        logger.debug("IMAP starred fetch note for %s: %s", account_email, exc)
        return []


def fetch_sent(account_email: str, max_count: int = 50) -> list[InboxMessage]:
    """
    Fetch messages from the account's Sent folder (e.g. [Gmail]/Sent Mail or Sent Items).
    """
    try:
        imap = _connect_imap(account_email)
    except Exception as exc:
        logger.debug("Could not connect to IMAP for sent fetch: %s", exc)
        return []

    try:
        with imap:
            sent_folder = _find_folder(imap, "sent")
            if not sent_folder:
                return []

            status, _ = imap.select(sent_folder, readonly=True)
            if status != "OK":
                return []

            status, data = imap.uid("SEARCH", None, "ALL")
            if status != "OK":
                return []

            all_uids: list[str] = data[0].decode().split() if data[0] else []
            if not all_uids:
                return []

            selected_uids = all_uids[-max_count:][::-1]
            if not selected_uids:
                return []

            query_uids = ",".join(selected_uids)
            status, fetch_data = imap.uid("FETCH", query_uids, "(FLAGS BODY.PEEK[])")
            if status != "OK" or not fetch_data:
                return []

            messages: list[InboxMessage] = []
            for item in fetch_data:
                if isinstance(item, tuple) and len(item) == 2:
                    header_meta, raw_bytes = item
                    meta_str = header_meta.decode(errors='ignore')
                    match = re.search(r'UID\s+(\d+)', meta_str, re.IGNORECASE)
                    if match:
                        uid_str = match.group(1)
                        if uid_str in selected_uids:
                            flags_match = re.search(r'FLAGS\s*\(([^)]*)\)', meta_str, re.IGNORECASE)
                            flags_str = flags_match.group(1).lower() if flags_match else ""
                            is_starred = ("\\flagged" in flags_str) or ("starred" in flags_str)
                            is_seen = "\\seen" in flags_str
                            messages.append(_parse_raw_message(uid_str, raw_bytes, starred=is_starred, seen=is_seen, folder="sent"))

            messages.sort(key=lambda m: selected_uids.index(m.uid))
            return messages
    except Exception as exc:
        logger.debug("IMAP sent fetch note for %s: %s", account_email, exc)
        return []


def fetch_all_folders(account_email: str, max_inbox: int = 50, max_sent: int = 30, max_spam: int = 20, max_starred: int = 20) -> dict[str, list[InboxMessage]]:
    """
    Fetch messages across all main mailbox folders (INBOX, SENT, SPAM, STARRED)
    reusing a single authenticated IMAP SSL connection to maximize performance.
    """
    results: dict[str, list[InboxMessage]] = {
        "inbox": [],
        "sent": [],
        "spam": [],
        "starred": [],
    }
    try:
        imap = _connect_imap(account_email)
    except Exception as exc:
        logger.debug("Could not connect to IMAP for unified batch fetch: %s", exc)
        return results

    try:
        with imap:
            # 1. Fetch INBOX
            try:
                status, _ = imap.select(_INBOX_FOLDER, readonly=True)
                if status == "OK":
                    flagged_uids: set[str] = set()
                    try:
                        f_status, f_data = imap.uid("SEARCH", None, "FLAGGED")
                        if f_status == "OK" and f_data and f_data[0]:
                            flagged_uids = set(f_data[0].decode().split())
                    except Exception:
                        pass

                    status, data = imap.uid("SEARCH", None, "ALL")
                    if status == "OK" and data and data[0]:
                        all_uids = data[0].decode().split()
                        selected_uids = all_uids[-max_inbox:][::-1]
                        if selected_uids:
                            q_uids = ",".join(selected_uids)
                            status, fetch_data = imap.uid("FETCH", q_uids, "(FLAGS BODY.PEEK[])")
                            if status == "OK" and fetch_data:
                                in_msgs = []
                                for item in fetch_data:
                                    if isinstance(item, tuple) and len(item) == 2:
                                        meta_str = item[0].decode(errors='ignore')
                                        match = re.search(r'UID\s+(\d+)', meta_str, re.IGNORECASE)
                                        if match:
                                            uid_str = match.group(1)
                                            if uid_str in selected_uids:
                                                flags_match = re.search(r'FLAGS\s*\(([^)]*)\)', meta_str, re.IGNORECASE)
                                                flags_str = flags_match.group(1).lower() if flags_match else ""
                                                is_starred = (uid_str in flagged_uids) or ("\\flagged" in flags_str) or ("starred" in flags_str)
                                                is_seen = "\\seen" in flags_str
                                                in_msgs.append(_parse_raw_message(uid_str, item[1], starred=is_starred, seen=is_seen, folder="inbox"))
                                in_msgs.sort(key=lambda m: selected_uids.index(m.uid))
                                results["inbox"] = in_msgs
            except Exception as e_inbox:
                logger.debug("Unified sync inbox fetch error: %s", e_inbox)

            # 2. Fetch SENT
            try:
                sent_folder = _find_folder(imap, "sent")
                if sent_folder:
                    status, _ = imap.select(sent_folder, readonly=True)
                    if status == "OK":
                        status, data = imap.uid("SEARCH", None, "ALL")
                        if status == "OK" and data and data[0]:
                            all_uids = data[0].decode().split()
                            selected_uids = all_uids[-max_sent:][::-1]
                            if selected_uids:
                                q_uids = ",".join(selected_uids)
                                status, fetch_data = imap.uid("FETCH", q_uids, "(FLAGS BODY.PEEK[])")
                                if status == "OK" and fetch_data:
                                    sent_msgs = []
                                    for item in fetch_data:
                                        if isinstance(item, tuple) and len(item) == 2:
                                            meta_str = item[0].decode(errors='ignore')
                                            match = re.search(r'UID\s+(\d+)', meta_str, re.IGNORECASE)
                                            if match:
                                                uid_str = match.group(1)
                                                if uid_str in selected_uids:
                                                    flags_match = re.search(r'FLAGS\s*\(([^)]*)\)', meta_str, re.IGNORECASE)
                                                    flags_str = flags_match.group(1).lower() if flags_match else ""
                                                    is_starred = ("\\flagged" in flags_str) or ("starred" in flags_str)
                                                    is_seen = "\\seen" in flags_str
                                                    sent_msgs.append(_parse_raw_message(uid_str, item[1], starred=is_starred, seen=is_seen, folder="sent"))
                                    sent_msgs.sort(key=lambda m: selected_uids.index(m.uid))
                                    results["sent"] = sent_msgs
            except Exception as e_sent:
                logger.debug("Unified sync sent fetch error: %s", e_sent)

            # 3. Fetch SPAM
            try:
                spam_folder = _find_folder(imap, "spam")
                if spam_folder:
                    status, _ = imap.select(spam_folder, readonly=True)
                    if status == "OK":
                        status, data = imap.uid("SEARCH", None, "ALL")
                        if status == "OK" and data and data[0]:
                            all_uids = data[0].decode().split()
                            selected_uids = all_uids[-max_spam:][::-1]
                            if selected_uids:
                                q_uids = ",".join(selected_uids)
                                status, fetch_data = imap.uid("FETCH", q_uids, "(FLAGS BODY.PEEK[])")
                                if status == "OK" and fetch_data:
                                    spam_msgs = []
                                    for item in fetch_data:
                                        if isinstance(item, tuple) and len(item) == 2:
                                            meta_str = item[0].decode(errors='ignore')
                                            match = re.search(r'UID\s+(\d+)', meta_str, re.IGNORECASE)
                                            if match:
                                                uid_str = match.group(1)
                                                if uid_str in selected_uids:
                                                    flags_match = re.search(r'FLAGS\s*\(([^)]*)\)', meta_str, re.IGNORECASE)
                                                    flags_str = flags_match.group(1).lower() if flags_match else ""
                                                    is_starred = ("\\flagged" in flags_str) or ("starred" in flags_str)
                                                    is_seen = "\\seen" in flags_str
                                                    spam_msgs.append(_parse_raw_message(uid_str, item[1], starred=is_starred, seen=is_seen, folder="spam"))
                                    spam_msgs.sort(key=lambda m: selected_uids.index(m.uid))
                                    results["spam"] = spam_msgs
            except Exception as e_spam:
                logger.debug("Unified sync spam fetch error: %s", e_spam)

            # 4. Fetch STARRED
            try:
                starred_folder = _find_folder(imap, "starred")
                if starred_folder:
                    status, _ = imap.select(starred_folder, readonly=True)
                    search_crit = "ALL"
                else:
                    status, _ = imap.select(_INBOX_FOLDER, readonly=True)
                    search_crit = "FLAGGED"

                if status == "OK":
                    status, data = imap.uid("SEARCH", None, search_crit)
                    if status == "OK" and data and data[0]:
                        all_uids = data[0].decode().split()
                        selected_uids = all_uids[-max_starred:][::-1]
                        if selected_uids:
                            q_uids = ",".join(selected_uids)
                            status, fetch_data = imap.uid("FETCH", q_uids, "(FLAGS BODY.PEEK[])")
                            if status == "OK" and fetch_data:
                                star_msgs = []
                                for item in fetch_data:
                                    if isinstance(item, tuple) and len(item) == 2:
                                        meta_str = item[0].decode(errors='ignore')
                                        match = re.search(r'UID\s+(\d+)', meta_str, re.IGNORECASE)
                                        if match:
                                            uid_str = match.group(1)
                                            if uid_str in selected_uids:
                                                flags_match = re.search(r'FLAGS\s*\(([^)]*)\)', meta_str, re.IGNORECASE)
                                                flags_str = flags_match.group(1).lower() if flags_match else ""
                                                is_seen = "\\seen" in flags_str
                                                star_msgs.append(_parse_raw_message(uid_str, item[1], starred=True, seen=is_seen, folder="inbox"))
                                star_msgs.sort(key=lambda m: selected_uids.index(m.uid))
                                results["starred"] = star_msgs
            except Exception as e_starred:
                logger.debug("Unified sync starred fetch error: %s", e_starred)

        return results
    except Exception as exc:
        logger.debug("IMAP unified batch fetch note for %s: %s", account_email, exc)
        return results


def move_message(account_email: str, uid: str, from_folder: str = "INBOX", to_folder: str = "SPAM") -> bool:
    """
    Move a message between folders on the IMAP server (e.g. INBOX <-> SPAM).
    """
    if not uid or not account_email:
        return False
    try:
        imap = _connect_imap(account_email)
        with imap:
            src = _find_folder(imap, "spam") if from_folder.upper() == "SPAM" else _INBOX_FOLDER
            dst = _find_folder(imap, "spam") if to_folder.upper() == "SPAM" else _INBOX_FOLDER

            if not src or not dst:
                return False

            status, _ = imap.select(src, readonly=False)
            if status != "OK":
                return False

            # Try UID MOVE (RFC 6855)
            try:
                status, _ = imap.uid("MOVE", uid, dst)
                if status == "OK":
                    return True
            except Exception:
                pass

            # Fallback to COPY + STORE \Deleted + EXPUNGE
            status, _ = imap.uid("COPY", uid, dst)
            if status == "OK":
                imap.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
                imap.expunge()
                return True
            return False
    except Exception as exc:
        logger.debug("IMAP move_message error for %s uid %s: %s", account_email, uid, exc)
        return False


def fetch_message(account_email: str, uid: str) -> InboxMessage:
    """
    Fetch a single message from INBOX by its IMAP UID.
    """
    imap = _connect_imap(account_email)

    try:
        with imap:
            imap.select(_INBOX_FOLDER, readonly=True)

            status, msg_data = imap.uid("FETCH", uid, "(BODY.PEEK[])")
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


def set_message_flags(
    account_email: str,
    uid: str,
    add_flags: list[str] | None = None,
    remove_flags: list[str] | None = None,
    folder: str = "INBOX",
) -> bool:
    """
    Synchronize IMAP flags (such as \\Flagged and \\Seen) for a single UID.
    Returns True on success, False if connection or STORE fails.
    """
    if not uid or (not add_flags and not remove_flags):
        return False

    try:
        imap = _connect_imap(account_email)
        with imap:
            target_folder = _INBOX_FOLDER
            if folder.upper() == "SPAM":
                found = _find_folder(imap, "spam")
                if found:
                    target_folder = found
            elif folder.upper() != "INBOX":
                target_folder = folder

            imap.select(target_folder, readonly=False)
            if add_flags:
                flag_arg = "(" + " ".join(add_flags) + ")"
                imap.uid("STORE", uid, "+FLAGS.SILENT", flag_arg)
            if remove_flags:
                flag_arg = "(" + " ".join(remove_flags) + ")"
                imap.uid("STORE", uid, "-FLAGS.SILENT", flag_arg)
        return True
    except Exception:
        return False
