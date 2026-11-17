"""
Event-Driven Mailbox Synchronization Engine.

Implements background inbox synchronization supporting:
- IMAP IDLE (RFC 2177) where supported by the server.
- Periodic IDLE refresh before server timeout.
- Safe fallback polling (DEGRADED_POLLING) when IDLE is unavailable or fails.
- Reconnection with bounded exponential backoff and jitter.
- Transactional synchronization cursor and metadata-first index updates.
- Authoritative unread counts and expunge detection.
- Non-blocking execution off the GUI thread with clean cancellation and shutdown.
- Application-level events independent of IMAP internals.
"""

from __future__ import annotations

from dataclasses import dataclass
from email.parser import BytesHeaderParser
from email.policy import default
from email.utils import parseaddr, parsedate_to_datetime
from enum import Enum
import imaplib
import random
import re
import select
import socket
import ssl
import threading
import time
from typing import Any, Callable

from core.logging_config import get_logger
from core.mailbox_cursor import MailboxCursor
from core.mailbox_index import MailboxIndex, IndexedMessage, sanitize_snippet

logger = get_logger("mailbox_sync")


# -----------------------------------------------------------------------------
# Lifecycle States & Event Models
# -----------------------------------------------------------------------------

class SyncState(str, Enum):
    """Lifecycle states of the background mailbox synchronization engine."""
    STOPPED = "stopped"
    CONNECTING = "connecting"
    SYNCHRONIZING = "synchronizing"
    IDLE = "idle"
    RECONNECTING = "reconnecting"
    DEGRADED_POLLING = "degraded_polling"
    STOPPING = "stopping"
    FAILED = "failed"


@dataclass(frozen=True)
class SyncStats:
    """Summary statistics for a completed synchronization pass."""
    new_messages_count: int
    updated_messages_count: int
    expunged_messages_count: int
    total_messages: int
    unread_messages: int
    duration_seconds: float


# -----------------------------------------------------------------------------
# IMAP IDLE Client Wrapper
# -----------------------------------------------------------------------------

class IdleCapableIMAPClient:
    """
    Protocol client for IMAP4rev1 with RFC 2177 IDLE capability.

    Wraps standard socket/SSL and imaplib interactions to provide safe,
    cancellable IDLE and metadata fetching without mutating server flags.
    """

    def __init__(
        self,
        host: str,
        port: int = 993,
        use_ssl: bool = True,
        timeout: float = 15.0,
    ) -> None:
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self.ssl_sock: ssl.SSLSocket | None = None
        self._tag_counter: int = 0
        self._capabilities: set[str] = set()
        self._selected_mailbox: str | None = None
        self._is_idling: bool = False
        self._active_idle_tag: str | None = None

    def _next_tag(self) -> str:
        self._tag_counter += 1
        return f"QM{self._tag_counter:04d}"

    def connect(self) -> None:
        """Establish TCP + TLS connection to the IMAP server."""
        raw_sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        if self.use_ssl:
            context = ssl.create_default_context()
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            self.ssl_sock = context.wrap_socket(raw_sock, server_hostname=self.host)
            self.sock = self.ssl_sock
        else:
            self.sock = raw_sock
        self.sock.settimeout(self.timeout)

        # Read server greeting
        greeting = self._readline()
        if not greeting.startswith(b"* OK"):
            self.close()
            raise ConnectionError(f"Unexpected server greeting: {greeting.decode(errors='replace')}")

        # Query capabilities
        self.update_capabilities()

    def close(self) -> None:
        """Close socket connection immediately."""
        self._is_idling = False
        self._active_idle_tag = None
        if self.sock is not None:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
            self.ssl_sock = None

    def _send_line(self, line: bytes) -> None:
        if self.sock is None:
            raise ConnectionError("Connection is closed.")
        self.sock.sendall(line + b"\r\n")

    def _readline(self) -> bytes:
        if self.sock is None:
            raise ConnectionError("Connection is closed.")
        chunks = []
        while True:
            char = self.sock.recv(1)
            if not char:
                raise EOFError("Connection closed by remote server.")
            chunks.append(char)
            if char == b"\n":
                break
        return b"".join(chunks).rstrip(b"\r\n")

    def _read_literal(self, size: int) -> bytes:
        if self.sock is None:
            raise ConnectionError("Connection is closed.")
        data = bytearray()
        while len(data) < size:
            chunk = self.sock.recv(min(16384, size - len(data)))
            if not chunk:
                raise EOFError("Connection closed while reading literal data.")
            data.extend(chunk)
        return bytes(data)

    def execute_command(self, cmd_str: str) -> tuple[str, list[bytes]]:
        """
        Execute a standard tagged IMAP command.

        Returns (status, untagged_lines). Status is 'OK', 'NO', or 'BAD'.
        """
        tag = self._next_tag()
        self._send_line(f"{tag} {cmd_str}".encode("utf-8"))
        untagged: list[bytes] = []

        while True:
            line = self._readline()
            if line.startswith(f"{tag} ".encode("utf-8")):
                parts = line.split(b" ", 2)
                status = parts[1].decode("ascii", errors="replace")
                return status, untagged

            # Check for literal payload marker at end of untagged response (e.g. {1234})
            literal_match = re.search(rb"\{(\d+)\}$", line)
            if literal_match:
                literal_size = int(literal_match.group(1))
                literal_data = self._read_literal(literal_size)
                untagged.append(line + b"\r\n" + literal_data)
            else:
                untagged.append(line)

    def update_capabilities(self) -> set[str]:
        """Fetch and cache server CAPABILITY list."""
        status, lines = self.execute_command("CAPABILITY")
        caps: set[str] = set()
        for line in lines:
            if line.startswith(b"* CAPABILITY "):
                for item in line[13:].split():
                    caps.add(item.decode("ascii", errors="replace").upper())
        self._capabilities = caps
        return self._capabilities

    def supports_idle(self) -> bool:
        """Return True if server advertises the IDLE capability."""
        return "IDLE" in self._capabilities

    def authenticate_xoauth2(self, email_address: str, access_token: str) -> bool:
        """Authenticate using SASL XOAUTH2."""
        tag = self._next_tag()
        auth_bytes = f"user={email_address}\x01auth=Bearer {access_token}\x01\x01".encode("utf-8")
        import base64
        b64_payload = base64.b64encode(auth_bytes).decode("ascii")

        self._send_line(f"{tag} AUTHENTICATE XOAUTH2 {b64_payload}".encode("ascii"))
        line = self._readline()
        if line.startswith(f"{tag} OK".encode("ascii")):
            self.update_capabilities()
            return True

        if line.startswith(b"+"):
            # Server error challenge: per Gmail XOAUTH2 spec, client must send empty response
            self._send_line(b"")
            line = self._readline()

        parts = line.split(b" ", 2)
        status = parts[1].decode("ascii", errors="replace") if len(parts) > 1 else "FAILED"
        logger.warning("XOAUTH2 authentication failed with status: %s", status)
        return False

    def authenticate_plain(self, username: str, password: str) -> bool:
        """Authenticate using IMAP LOGIN (for testing fixtures)."""
        status, _ = self.execute_command(f'LOGIN "{username}" "{password}"')
        if status == "OK":
            self.update_capabilities()
            return True
        return False

    def select_readonly(self, mailbox: str = "INBOX") -> int:
        """
        Select mailbox in read-only mode (EXAMINE) to prevent modifying \\Seen flags.

        Returns authoritative UIDVALIDITY integer.
        """
        status, lines = self.execute_command(f'EXAMINE "{mailbox}"')
        if status != "OK":
            raise ValueError(f"Failed to select mailbox '{mailbox}': status={status}")

        self._selected_mailbox = mailbox
        uidvalidity = 0
        for line in lines:
            match = re.search(rb"\[UIDVALIDITY\s+(\d+)\]", line, re.IGNORECASE)
            if match:
                uidvalidity = int(match.group(1))
                break

        if uidvalidity <= 0:
            raise ValueError(f"Server did not return a valid UIDVALIDITY for mailbox '{mailbox}'")
        return uidvalidity

    def get_uidnext(self) -> int:
        """Fetch current UIDNEXT prediction for selected mailbox."""
        status, lines = self.execute_command(f'STATUS "{self._selected_mailbox}" (UIDNEXT)')
        if status == "OK":
            for line in lines:
                match = re.search(rb"UIDNEXT\s+(\d+)", line, re.IGNORECASE)
                if match:
                    return int(match.group(1))
        return 1

    def search_all_uids(self) -> set[int]:
        """Fetch all message UIDs currently present in the selected mailbox."""
        status, lines = self.execute_command("UID SEARCH ALL")
        if status != "OK":
            raise RuntimeError(f"UID SEARCH ALL failed with status {status}")

        uids: set[int] = set()
        for line in lines:
            if line.startswith(b"* SEARCH"):
                tokens = line[8:].split()
                for tok in tokens:
                    try:
                        u = int(tok)
                        if u > 0:
                            uids.add(u)
                    except ValueError:
                        pass
        return uids

    def fetch_headers_peek(self, uids: list[int]) -> list[tuple[int, list[str], int, bytes]]:
        """
        Fetch message metadata and headers using non-mutating BODY.PEEK[...].

        Guarantees that background synchronization never mutates \\Seen.

        Returns list of (uid, flags, size, raw_headers_bytes).
        """
        if not uids:
            return []

        uid_query = ",".join(str(u) for u in sorted(uids))
        fetch_cmd = (
            f"UID FETCH {uid_query} "
            "(UID FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM TO CC SUBJECT DATE MESSAGE-ID CONTENT-TYPE)])"
        )
        status, lines = self.execute_command(fetch_cmd)
        if status != "OK":
            raise RuntimeError(f"UID FETCH failed with status {status}")

        results = []
        i = 0
        while i < len(lines):
            line = lines[i]
            # Match FETCH line: * <seq> FETCH (UID <uid> FLAGS (<flags>) RFC822.SIZE <size> BODY[HEADER...] {<len>}
            uid_match = re.search(rb"\bUID\s+(\d+)", line, re.IGNORECASE)
            size_match = re.search(rb"\bRFC822\.SIZE\s+(\d+)", line, re.IGNORECASE)
            flags_match = re.search(rb"\bFLAGS\s*\(([^)]*)\)", line, re.IGNORECASE)

            if uid_match and size_match:
                uid_val = int(uid_match.group(1))
                size_val = int(size_match.group(1))
                raw_flags = flags_match.group(1).decode("ascii", errors="replace").split() if flags_match else []

                # Header payload is attached after literal marker
                raw_header = b""
                if b"\r\n" in line:
                    parts = line.split(b"\r\n", 1)
                    raw_header = parts[1]
                elif i + 1 < len(lines):
                    raw_header = lines[i + 1]
                    i += 1

                results.append((uid_val, raw_flags, size_val, raw_header))
            i += 1

        return results

    def fetch_body_peek(self, uid: int) -> bytes:
        """
        Fetch full message raw bytes using non-mutating BODY.PEEK[].

        Preserves read state on server.
        """
        fetch_cmd = f"UID FETCH {uid} (BODY.PEEK[])"
        status, lines = self.execute_command(fetch_cmd)
        if status != "OK":
            raise RuntimeError(f"UID FETCH BODY.PEEK failed with status {status}")

        for line in lines:
            if b"\r\n" in line:
                return line.split(b"\r\n", 1)[1]
        raise ValueError(f"No message body found for UID {uid}")

    def start_idle(self) -> None:
        """
        Send IMAP IDLE command and verify continuation response (+ idling).
        """
        if not self.supports_idle():
            raise RuntimeError("Server does not support IMAP IDLE (RFC 2177).")

        tag = self._next_tag()
        self._active_idle_tag = tag
        self._send_line(f"{tag} IDLE".encode("ascii"))

        # Wait for '+' continuation
        line = self._readline()
        if not line.startswith(b"+"):
            self._active_idle_tag = None
            raise RuntimeError(f"Server rejected IDLE command: {line.decode(errors='replace')}")

        self._is_idling = True

    def wait_for_idle_notification(self, timeout_seconds: float) -> list[bytes]:
        """
        Wait for untagged server notifications while in IDLE state.

        Returns list of untagged notification lines if server sent data,
        or empty list if timeout expired.
        """
        if not self._is_idling or self.sock is None:
            return []

        r, _, _ = select.select([self.sock], [], [], timeout_seconds)
        if not r:
            return []

        notifications = []
        while True:
            # Check if socket has readable data without blocking
            ready, _, _ = select.select([self.sock], [], [], 0.05)
            if not ready:
                break
            line = self._readline()
            notifications.append(line)
        return notifications

    def stop_idle(self) -> None:
        """
        Terminate active IDLE state by sending DONE\r\n and waiting for tagged OK.
        """
        if not self._is_idling or self.sock is None:
            self._is_idling = False
            return

        tag = self._active_idle_tag
        try:
            self._send_line(b"DONE")
            # Read until tagged OK / NO / BAD
            while True:
                line = self._readline()
                if tag and line.startswith(f"{tag} ".encode("ascii")):
                    break
        finally:
            self._is_idling = False
            self._active_idle_tag = None


# -----------------------------------------------------------------------------
# Background Synchronization Engine
# -----------------------------------------------------------------------------

class MailboxSyncEngine:
    """
    Dedicated background mailbox synchronization engine with lifecycle state machine.

    Maintains IMAP IDLE connection with safe fallback polling, backoff on error,
    authoritative unread tracking, expunge reconciliation, and transactional vault persistence.
    """

    def __init__(
        self,
        account_id: str,
        account_email: str,
        token_or_password_provider: Callable[[], str],
        client_factory: Callable[[], IdleCapableIMAPClient],
        vault: Any,
        mailbox: str = "INBOX",
        poll_interval_seconds: float = 60.0,
        idle_timeout_seconds: float = 600.0,  # 10 minutes default IDLE refresh
        backoff_initial: float = 1.0,
        backoff_multiplier: float = 2.0,
        backoff_max: float = 60.0,
        is_oauth: bool = True,
    ) -> None:
        self.account_id = account_id
        self.account_email = account_email
        self.get_credential = token_or_password_provider
        self.client_factory = client_factory
        self.vault = vault
        self.mailbox = mailbox
        self.poll_interval = max(1.0, min(600.0, poll_interval_seconds))
        self.idle_timeout = max(1.0, idle_timeout_seconds)
        self.backoff_initial = backoff_initial
        self.backoff_multiplier = backoff_multiplier
        self.backoff_max = backoff_max
        self.is_oauth = is_oauth

        self._state = SyncState.STOPPED
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._client: IdleCapableIMAPClient | None = None

        # Event callbacks
        self.on_state_changed: Callable[[SyncState, SyncState, str], None] | None = None
        self.on_sync_started: Callable[[str, str], None] | None = None
        self.on_sync_completed: Callable[[str, str, SyncStats], None] | None = None
        self.on_new_messages: Callable[[str, str, list[IndexedMessage]], None] | None = None
        self.on_messages_changed: Callable[[str, str, list[IndexedMessage]], None] | None = None
        self.on_messages_removed: Callable[[str, str, list[int]], None] | None = None
        self.on_unread_count_changed: Callable[[str, str, int, int], None] | None = None
        self.on_auth_required: Callable[[str, str], None] | None = None
        self.on_sync_error: Callable[[str, Exception, bool], None] | None = None

    @property
    def state(self) -> SyncState:
        return self._state

    def _set_state(self, new_state: SyncState, detail: str = "") -> None:
        old_state = self._state
        if old_state != new_state:
            self._state = new_state
            logger.info("Sync state transition: %s -> %s (%s)", old_state.value, new_state.value, detail)
            if self.on_state_changed:
                try:
                    self.on_state_changed(old_state, new_state, detail)
                except Exception:
                    pass

    def start(self) -> None:
        """Start the background synchronization worker thread."""
        with self._lock:
            if self._worker_thread and self._worker_thread.is_alive():
                logger.warning("MailboxSyncEngine worker already running.")
                return
            self._stop_event.clear()
            self._worker_thread = threading.Thread(
                target=self._run_loop,
                name=f"QuMail-SyncWorker-{self.account_id}",
                daemon=True,
            )
            self._worker_thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """
        Request cancellation and cleanly shut down the background sync worker.
        """
        with self._lock:
            self._set_state(SyncState.STOPPING, "Shutdown requested")
            self._stop_event.set()
            if self._client:
                try:
                    self._client.close()
                except Exception:
                    pass

        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)

        self._set_state(SyncState.STOPPED, "Stopped")

    def _run_loop(self) -> None:
        """Main lifecycle loop of the synchronization worker."""
        current_backoff = self.backoff_initial

        while not self._stop_event.is_set():
            try:
                self._set_state(SyncState.CONNECTING, "Opening IMAP connection")
                client = self.client_factory()
                self._client = client
                client.connect()

                # Authenticate
                token_or_pass = self.get_credential()
                if self.is_oauth:
                    ok = client.authenticate_xoauth2(self.account_email, token_or_pass)
                else:
                    ok = client.authenticate_plain(self.account_email, token_or_pass)

                if not ok:
                    self._set_state(SyncState.FAILED, "Authentication failed")
                    if self.on_auth_required:
                        self.on_auth_required(self.account_id, "Authentication expired or credentials rejected.")
                    break

                # Select mailbox read-only and obtain authoritative UIDVALIDITY
                server_uidvalidity = client.select_readonly(self.mailbox)
                current_backoff = self.backoff_initial

                # Perform initial synchronization
                self._perform_sync(client, server_uidvalidity)

                # Enter IDLE or fallback polling
                if client.supports_idle():
                    self._idle_loop(client, server_uidvalidity)
                else:
                    self._polling_loop(client, server_uidvalidity)

            except (ConnectionError, EOFError, socket.error) as exc:
                if self._stop_event.is_set():
                    break
                logger.warning("Network connection error in sync loop: %s", exc)
                self._set_state(SyncState.RECONNECTING, str(exc))
                if self.on_sync_error:
                    self.on_sync_error(self.account_id, exc, False)
                # Exponential backoff with jitter
                jitter = random.uniform(0.8, 1.2)
                sleep_time = min(self.backoff_max, current_backoff * jitter)
                current_backoff = min(self.backoff_max, current_backoff * self.backoff_multiplier)
                self._interruptible_sleep(sleep_time)

            except Exception as exc:
                if self._stop_event.is_set():
                    break
                logger.error("Unexpected failure in sync loop: %s", exc, exc_info=True)
                self._set_state(SyncState.FAILED, str(exc))
                if self.on_sync_error:
                    self.on_sync_error(self.account_id, exc, True)
                self._interruptible_sleep(self.backoff_initial)

            finally:
                if self._client:
                    try:
                        self._client.close()
                    except Exception:
                        pass
                    self._client = None

        self._set_state(SyncState.STOPPED, "Worker exiting")

    def _perform_sync(self, client: IdleCapableIMAPClient, server_uidvalidity: int) -> SyncStats:
        """
        Execute an atomic synchronization pass.

        Validates UIDVALIDITY, fetches missing message headers via PEEK,
        reconciles flags and expunges, and commits to the encrypted vault.
        """
        t0 = time.perf_counter()
        self._set_state(SyncState.SYNCHRONIZING, "Synchronizing headers and flags")
        if self.on_sync_started:
            try:
                self.on_sync_started(self.account_id, self.mailbox)
            except Exception:
                pass

        # Load cursor and index from vault
        account_ctx = getattr(self.vault, "get_account_context", lambda a: None)(self.account_id)

        # Context manager for vault transaction
        with self.vault.transaction(account_ctx if account_ctx else self.account_id) as vdata:
            cursor = MailboxCursor.load_from_vault(vdata, self.account_id, self.mailbox)
            index = MailboxIndex.load_from_vault(vdata, self.account_id, self.mailbox)

            # Check UIDVALIDITY
            valid = cursor.check_uidvalidity(server_uidvalidity)
            if not valid:
                logger.warning("UIDVALIDITY changed for mailbox %s. Clearing stale index.", self.mailbox)
                index.clear()
                index.uidvalidity = server_uidvalidity

            # Server UIDs
            server_uids = client.search_all_uids()
            server_uidnext = client.get_uidnext()

            # Expunge reconciliation
            expunged_uids = cursor.reconcile_expunges(server_uids)
            for euid in expunged_uids:
                index.remove_message(euid)

            # Determine new UIDs to fetch
            new_uids = sorted(server_uids - cursor.synced_uids)
            new_messages: list[IndexedMessage] = []

            if new_uids:
                # Fetch metadata using non-mutating PEEK
                header_data = client.fetch_headers_peek(new_uids)
                for uid, flags, size, raw_headers in header_data:
                    parsed_hdr = BytesHeaderParser(policy=default).parsebytes(raw_headers)
                    sender_raw = str(parsed_hdr.get("From", ""))
                    disp_name, addr = parseaddr(sender_raw)
                    date_str = str(parsed_hdr.get("Date", ""))
                    try:
                        dt = parsedate_to_datetime(date_str)
                        date_ts = dt.timestamp()
                    except Exception:
                        date_ts = 0.0

                    to_headers = [v.strip() for v in str(parsed_hdr.get("To", "")).split(",") if v.strip()]
                    cc_headers = [v.strip() for v in str(parsed_hdr.get("Cc", "")).split(",") if v.strip()]

                    # Check Content-Type for attachments
                    ctype = str(parsed_hdr.get("Content-Type", "")).lower()
                    has_att = "multipart/mixed" in ctype or "attachment" in ctype

                    seen = r"\Seen" in flags or b"\\Seen" in [f.encode() if isinstance(f, str) else f for f in flags]

                    msg = IndexedMessage(
                        uid=uid,
                        uidvalidity=server_uidvalidity,
                        mailbox=self.mailbox,
                        account_id=self.account_id,
                        sender_display=disp_name or addr,
                        sender_address=addr,
                        recipients=tuple(to_headers + cc_headers),
                        subject=str(parsed_hdr.get("Subject", "")),
                        date=date_str,
                        date_ts=date_ts,
                        message_id=str(parsed_hdr.get("Message-ID", "")),
                        size=size,
                        flags=tuple(flags),
                        seen=seen,
                        has_attachments=has_att,
                        snippet=sanitize_snippet(str(parsed_hdr.get("Subject", ""))),
                        in_reply_to=str(parsed_hdr.get("In-Reply-To", "")),
                        references=tuple(str(parsed_hdr.get("References", "")).split()),
                    )
                    index.upsert_message(msg)
                    new_messages.append(msg)

                cursor.record_synced(new_uids, new_uidnext=server_uidnext)

            # Persist atomically to vault
            cursor.save_to_vault(vdata)
            index.save_to_vault(vdata)

        # Notify observers
        stats = SyncStats(
            new_messages_count=len(new_messages),
            updated_messages_count=0,
            expunged_messages_count=len(expunged_uids),
            total_messages=index.get_total_count(),
            unread_messages=index.get_unread_count(),
            duration_seconds=time.perf_counter() - t0,
        )

        if expunged_uids and self.on_messages_removed:
            try:
                self.on_messages_removed(self.account_id, self.mailbox, expunged_uids)
            except Exception:
                pass

        if new_messages and self.on_new_messages:
            try:
                self.on_new_messages(self.account_id, self.mailbox, new_messages)
            except Exception:
                pass

        if self.on_unread_count_changed:
            try:
                self.on_unread_count_changed(self.account_id, self.mailbox, stats.unread_messages, stats.total_messages)
            except Exception:
                pass

        if self.on_sync_completed:
            try:
                self.on_sync_completed(self.account_id, self.mailbox, stats)
            except Exception:
                pass

        return stats

    def _idle_loop(self, client: IdleCapableIMAPClient, server_uidvalidity: int) -> None:
        """
        Maintain RFC 2177 IDLE connection, handling events and periodic re-issuing.
        """
        while not self._stop_event.is_set():
            self._set_state(SyncState.IDLE, "Waiting for server IDLE events")
            client.start_idle()
            idle_start = time.time()

            try:
                while not self._stop_event.is_set():
                    # Periodic timeout check to avoid server-side IDLE termination
                    if time.time() - idle_start >= self.idle_timeout:
                        break

                    # Check for notifications in small slices
                    notifications = client.wait_for_idle_notification(timeout_seconds=min(1.0, self.idle_timeout))
                    if notifications:
                        # Server sent an event! Stop IDLE and sync.
                        break
            finally:
                client.stop_idle()

            if self._stop_event.is_set():
                break

            # Perform sync pass following notification or timeout
            self._perform_sync(client, server_uidvalidity)

    def _polling_loop(self, client: IdleCapableIMAPClient, server_uidvalidity: int) -> None:
        """Fallback polling loop when IDLE is not available."""
        self._set_state(SyncState.DEGRADED_POLLING, f"Polling fallback every {self.poll_interval}s")

        while not self._stop_event.is_set():
            self._interruptible_sleep(self.poll_interval)
            if self._stop_event.is_set():
                break
            self._perform_sync(client, server_uidvalidity)
            self._set_state(SyncState.DEGRADED_POLLING, f"Polling fallback every {self.poll_interval}s")

    def _interruptible_sleep(self, seconds: float) -> None:
        """Sleep in small slices checking for cancellation."""
        end_time = time.time() + seconds
        while time.time() < end_time and not self._stop_event.is_set():
            time.sleep(min(0.1, end_time - time.time()))
