# portal/portal_server.py — Secure web portal server for non-QuMail recipients.
# Single responsibility: persist portal sessions in Cloud Firestore (shared across
# all Cloud Run instances), serve a time-limited single-use HTTPS/HTTP portal link
# to non-QuMail recipients, and expose retrieve_private_key() for inbox_view.py.
# Does not perform decryption itself — delegates to portal/portal_crypto.py.
# Do not import from transport/, mime/, certificates/, kme/, or ui/.
#
# Deployment modes (controlled by PORTAL_MODE environment variable):
#   local (default) — HTTPS server on PORTAL_HOST:PORTAL_PORT (self-signed cert).
#                     Session store uses Firestore if credentials are available;
#                     falls back to in-memory dict for offline development only.
#   cloud           — Plain HTTP server on 0.0.0.0:8080 (Cloud Run terminates TLS).
#                     Session store always uses Firestore. _generate_tls_cert() and
#                     start() are never called; cloud_entrypoint.py is the entry point.

import os
import ssl
import tempfile
import threading
import time
import uuid
import json
import logging
from dataclasses  import dataclass, field
from datetime     import datetime, timezone, timedelta
from http.server  import BaseHTTPRequestHandler, HTTPServer
from pathlib      import Path
from typing       import Optional

from core.config import PORTAL_HOST, PORTAL_PORT, PORTAL_LINK_TTL


# -------------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------------

_TEMPLATE_PATH: Path = Path(__file__).parent / "templates" / "portal.html"
_LOGGER = logging.getLogger(__name__)

# Imported lazily inside the handler to avoid a circular import at module load.
_PORTAL_CRYPTO_MODULE = None

# Firestore collection names (overridable via env for testing).
_SESSION_COLLECTION    = os.getenv("PORTAL_COLLECTION", "portal_sessions")
_RATE_LIMIT_COLLECTION = os.getenv("PORTAL_RATE_LIMIT_COLLECTION", "portal_rate_limits")

# Anti-abuse controls — same values as before.
_MAX_REQUESTS_PER_WINDOW = 10
_RATE_WINDOW_SECONDS     = 60

# Deployment mode: "cloud" disables the local HTTPS server and TLS cert generation.
_PORTAL_MODE = os.getenv("PORTAL_MODE", "local").lower()


# -------------------------------------------------------------------------
# Custom Exceptions
# -------------------------------------------------------------------------

class PortalSessionError(Exception):
    """Raised when a session lookup fails — expired, consumed, or not found."""
    pass


class PortalServerError(Exception):
    """Raised when the portal HTTPS server fails to start or encounters a fatal error."""
    pass


# -------------------------------------------------------------------------
# Session model
# -------------------------------------------------------------------------

@dataclass
class _PortalSession:
    """
    Record for a single portal send session.

    ciphertext  : Encrypted message bytes from tqr.encrypt().
    metadata    : Crypto metadata dict from tqr.encrypt().
    private_key : ML-KEM private key — never leaves this store except via
                  retrieve_private_key() (called by inbox_view.py) or the
                  /retrieve HTTPS route (called by portal_crypto.py).
    expires_at  : Unix timestamp after which the session is invalid.
    consumed    : True after the portal recipient has successfully retrieved
                  the plaintext — prevents replay access.
    """
    ciphertext:  bytes
    metadata:    dict
    private_key: bytes
    expires_at:  float
    consumed:    bool = field(default=False)


# -------------------------------------------------------------------------
# Firestore client singleton
# -------------------------------------------------------------------------

_firestore_client    = None
_firestore_lock      = threading.Lock()
_firestore_available = True   # Set to False on first init failure; never retried.

# In-memory fallback store — used when Firestore is unavailable (local dev, no GCP creds).
# Keys are session_id strings; values are plain dicts matching the Firestore document shape.
_memory_store: dict = {}
_memory_rate_limits: dict = {}


def _get_firestore():
    """
    Return a shared Firestore client, initialising it on first call.

    Thread-safe. Returns None and sets _firestore_available=False if the
    google-cloud-firestore package is not installed or credentials are not
    configured — callers should check _firestore_available before calling.
    """
    global _firestore_client, _firestore_available
    if _firestore_client is not None:
        return _firestore_client
    if not _firestore_available:
        return None
    with _firestore_lock:
        if _firestore_client is not None:
            return _firestore_client
        if not _firestore_available:
            return None
        try:
            from google.cloud import firestore  # type: ignore
            project = os.getenv("GOOGLE_CLOUD_PROJECT")
            _firestore_client = firestore.Client(project=project) if project else firestore.Client()
            _LOGGER.info("Firestore client initialised (project=%s).", project or "default")
            return _firestore_client
        except ImportError:
            _firestore_available = False
            _LOGGER.warning(
                "Firestore unavailable — portal running with in-memory session store. "
                "Sessions will not persist across restarts."
            )
            return None
        except Exception as exc:
            _firestore_available = False
            _LOGGER.warning(
                "Firestore unavailable — portal running with in-memory session store. "
                "Sessions will not persist across restarts. (Reason: %s)", exc
            )
            return None


# -------------------------------------------------------------------------
# Firestore helpers
# -------------------------------------------------------------------------

def _session_doc_ref(session_id: str):
    """Return the Firestore DocumentReference for a portal session."""
    db = _get_firestore()
    return db.collection(_SESSION_COLLECTION).document(session_id)


def _rate_limit_doc_ref(key: str):
    """Return the Firestore DocumentReference for a rate limit bucket."""
    db = _get_firestore()
    return db.collection(_RATE_LIMIT_COLLECTION).document(key)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# -------------------------------------------------------------------------
# Session management
# -------------------------------------------------------------------------

def store_session(
    ciphertext:  bytes,
    metadata:    dict,
    private_key: bytes,
) -> str:
    """
    Store an encrypted session and return a single-use portal URL.

    Uses Firestore when available, otherwise falls back to the in-memory store.
    Creates a UUID-keyed document with an expiry of PORTAL_LINK_TTL seconds from
    now. The URL is sent to the non-QuMail recipient by compose_window.py.

    Args:
        ciphertext:  Encrypted message bytes from tqr.encrypt().
        metadata:    Crypto metadata dict from tqr.encrypt().
        private_key: ML-KEM private key extracted by tqr.encrypt().

    Returns:
        Full HTTPS/HTTP URL string for the recipient to open in a browser.
    """
    session_id = str(uuid.uuid4())
    expires_dt = _now_utc() + timedelta(seconds=PORTAL_LINK_TTL)

    doc_data = {
        "ciphertext":  ciphertext,
        "metadata":    metadata,
        "private_key": private_key,
        "expires_at":  expires_dt,
        "consumed":    False,
    }

    db = _get_firestore()
    if db is not None:
        ref = db.collection(_SESSION_COLLECTION).document(session_id)
        ref.set(doc_data)
    else:
        _memory_store[session_id] = doc_data

    _LOGGER.info("Portal session stored: %s (expires %s).", session_id, expires_dt.isoformat())

    host = os.getenv("PORTAL_HOST", PORTAL_HOST)
    if _PORTAL_MODE == "cloud":
        return f"https://{host}/{session_id}"
    else:
        return f"https://{host}:{PORTAL_PORT}/{session_id}"


def retrieve_private_key(session_id: str) -> bytes:
    """
    Return the ML-KEM private key for a given session.

    Called by inbox_view.py when the sender wants to locally decrypt a sent
    Level 3 message for display. Does not mark the session as consumed —
    only the browser /retrieve route does that.

    Raises PortalSessionError if the session is not found or has expired.
    """
    db = _get_firestore()
    if db is not None:
        ref  = db.collection(_SESSION_COLLECTION).document(session_id)
        snap = ref.get()
        if not snap.exists:
            raise PortalSessionError(f"No portal session found for ID '{session_id}'.")
        data = snap.to_dict()
        expires_at: datetime = data["expires_at"]
        if not expires_at.tzinfo:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
    else:
        if session_id not in _memory_store:
            raise PortalSessionError(f"No portal session found for ID '{session_id}'.")
        data = _memory_store[session_id]
        expires_at = data["expires_at"]

    if _now_utc() > expires_at:
        raise PortalSessionError(f"Portal session '{session_id}' has expired.")

    return data["private_key"]


def _get_session_for_portal(session_id: str) -> _PortalSession:
    """
    Retrieve and validate a session for the portal browser flow.

    Uses Firestore when available, otherwise uses the in-memory store.
    Raises PortalSessionError if the session is missing, expired, or consumed.
    Does not mutate the session; the caller marks it consumed after decryption.
    """
    db = _get_firestore()
    if db is not None:
        ref  = db.collection(_SESSION_COLLECTION).document(session_id)
        snap = ref.get()
        if not snap.exists:
            raise PortalSessionError(f"Session '{session_id}' not found.")
        data = snap.to_dict()
        expires_at: datetime = data["expires_at"]
        if not expires_at.tzinfo:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
    else:
        if session_id not in _memory_store:
            raise PortalSessionError(f"Session '{session_id}' not found.")
        data = _memory_store[session_id]
        expires_at = data["expires_at"]

    if _now_utc() > expires_at:
        raise PortalSessionError(f"Session '{session_id}' has expired.")

    if data.get("consumed", False):
        raise PortalSessionError(f"Session '{session_id}' has already been used.")

    return _PortalSession(
        ciphertext=  data["ciphertext"],
        metadata=    data["metadata"],
        private_key= data["private_key"],
        expires_at=  expires_at.timestamp(),
        consumed=    False,
    )


def _mark_consumed(session_id: str) -> None:
    """
    Atomically mark a session as consumed.

    When Firestore is available, uses a Firestore transaction to prevent replay
    under concurrent access: exactly one request wins; all others find
    consumed=True and receive 410.

    When running in-memory (offline dev), uses a threading.Lock for the same
    effect (single-process guarantee only — no cross-instance safety).
    """
    db = _get_firestore()
    if db is not None:
        from google.cloud import firestore  # type: ignore
        ref         = db.collection(_SESSION_COLLECTION).document(session_id)
        transaction = db.transaction()

        @firestore.transactional
        def _txn(transaction):
            snap = ref.get(transaction=transaction)
            if not snap.exists:
                raise PortalSessionError(f"Session '{session_id}' disappeared during consume.")
            data = snap.to_dict()
            if data.get("consumed", False):
                raise PortalSessionError(f"Session '{session_id}' was already consumed.")
            transaction.update(ref, {"consumed": True})

        _txn(transaction)
    else:
        with _firestore_lock:
            if session_id not in _memory_store:
                raise PortalSessionError(f"Session '{session_id}' disappeared during consume.")
            if _memory_store[session_id].get("consumed", False):
                raise PortalSessionError(f"Session '{session_id}' was already consumed.")
            _memory_store[session_id]["consumed"] = True

    _LOGGER.info("Portal session consumed: %s.", session_id)


def _is_rate_limited(client_ip: str, session_id: str) -> bool:
    """
    Return True when a client exceeds the request allowance for a session.

    When Firestore is available: uses a Firestore transaction for cross-instance
    safety (sliding window, stored in portal_rate_limits/<ip>:<session_id>).
    When running in-memory: uses an in-process dict with a threading.Lock.
    """
    now    = _now_utc()
    cutoff = now - timedelta(seconds=_RATE_WINDOW_SECONDS)
    key    = f"{client_ip}:{session_id}"

    db = _get_firestore()
    if db is not None:
        from google.cloud import firestore  # type: ignore
        ref         = db.collection(_RATE_LIMIT_COLLECTION).document(key)
        transaction = db.transaction()

        @firestore.transactional
        def _txn(transaction) -> bool:
            snap = ref.get(transaction=transaction)
            raw_timestamps: list = snap.to_dict().get("timestamps", []) if snap.exists else []

            def _as_utc(ts) -> datetime:
                if isinstance(ts, datetime):
                    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
                return datetime.fromtimestamp(float(ts), tz=timezone.utc)

            recent = [t for t in raw_timestamps if _as_utc(t) >= cutoff]
            if len(recent) >= _MAX_REQUESTS_PER_WINDOW:
                transaction.set(ref, {
                    "timestamps": recent,
                    "expires_at": now + timedelta(seconds=_RATE_WINDOW_SECONDS),
                })
                return True
            recent.append(now)
            transaction.set(ref, {
                "timestamps": recent,
                "expires_at": now + timedelta(seconds=_RATE_WINDOW_SECONDS),
            })
            return False

        return _txn(transaction)
    else:
        with _firestore_lock:
            bucket = _memory_rate_limits.setdefault(key, [])
            recent = [t for t in bucket if t >= cutoff]
            if len(recent) >= _MAX_REQUESTS_PER_WINDOW:
                _memory_rate_limits[key] = recent
                return True
            recent.append(now)
            _memory_rate_limits[key] = recent
            return False


# -------------------------------------------------------------------------
# TLS certificate (self-signed, ephemeral) — local mode only
# -------------------------------------------------------------------------

def _generate_tls_cert() -> tuple[str, str]:
    """
    Generate an ephemeral self-signed TLS certificate and private key.

    Used only in local mode. In cloud mode (PORTAL_MODE=cloud) Cloud Run
    terminates TLS at the load balancer — this function is never called.

    Written to a temp directory — both files are deleted when the process exits.
    Uses the cryptography library (already in requirements.txt via the
    cryptography package used by level2_aes.py).

    Returns (cert_path, key_path) as strings for ssl.SSLContext.load_cert_chain().
    Raises PortalServerError if generation fails.
    """
    try:
        import datetime as _dt
        from cryptography                        import x509
        from cryptography.x509.oid              import NameOID
        from cryptography.hazmat.primitives     import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "QuMail Portal"),
        ])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(_dt.datetime.utcnow())
            .not_valid_after(_dt.datetime.utcnow() + _dt.timedelta(days=1))
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName("localhost")]),
                critical=False,
            )
            .sign(private_key, hashes.SHA256())
        )

        tmp_dir   = tempfile.mkdtemp()
        cert_path = os.path.join(tmp_dir, "portal_cert.pem")
        key_path  = os.path.join(tmp_dir, "portal_key.pem")

        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        with open(key_path, "wb") as f:
            f.write(private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            ))

        return cert_path, key_path

    except Exception as exc:
        raise PortalServerError(
            f"Failed to generate self-signed TLS certificate: {exc}"
        ) from exc


# -------------------------------------------------------------------------
# HTTP request handler
# -------------------------------------------------------------------------

class _PortalHandler(BaseHTTPRequestHandler):
    """
    Handles two routes:
      GET  /{session_id}          → serve portal.html with session_id embedded.
      POST /{session_id}/retrieve → decrypt and return plaintext JSON; mark consumed.

    All other paths return 404. All errors return JSON with an "error" key.
    """

    def do_GET(self) -> None:
        session_id = self.path.lstrip("/")
        if not session_id:
            self._respond_json(404, {"error": "Not found."})
            return
        try:
            _get_session_for_portal(session_id)   # Validate before serving HTML
            html = _TEMPLATE_PATH.read_bytes()
            # Inject session_id so portal.html can POST to the retrieve endpoint.
            html = html.replace(b"{{SESSION_ID}}", session_id.encode())
            self._respond(200, "text/html; charset=utf-8", html)
        except PortalSessionError as exc:
            _LOGGER.warning("Portal GET rejected: %s", exc)
            self._respond_json(410, {"error": "Session expired or unavailable."})
        except FileNotFoundError:
            _LOGGER.error("Portal template missing at %s", _TEMPLATE_PATH)
            self._respond_json(500, {"error": "Portal template missing."})

    def do_POST(self) -> None:
        # Expected path: /{session_id}/retrieve
        parts = self.path.strip("/").split("/")
        if len(parts) != 2 or parts[1] != "retrieve":
            self._respond(404, "application/json", b'{"error": "Not found."}')
            return

        session_id = parts[0]
        client_ip  = self.client_address[0] if self.client_address else "unknown"

        if _is_rate_limited(client_ip, session_id):
            _LOGGER.warning("Portal rate limited for %s on session %s", client_ip, session_id)
            self._respond_json(429, {"error": "Too many requests. Please wait and retry."})
            return

        try:
            session = _get_session_for_portal(session_id)

            # Lazy import to avoid circular dependency at module load time.
            global _PORTAL_CRYPTO_MODULE
            if _PORTAL_CRYPTO_MODULE is None:
                import portal.portal_crypto as _pc
                _PORTAL_CRYPTO_MODULE = _pc

            plaintext = _PORTAL_CRYPTO_MODULE.decrypt_for_portal(
                ciphertext=  session.ciphertext,
                metadata=    session.metadata,
                private_key= session.private_key,
            )
            _mark_consumed(session_id)

            import base64
            body = json.dumps({"plaintext": base64.b64encode(plaintext).decode()}).encode()
            self._respond(200, "application/json", body)

        except PortalSessionError as exc:
            _LOGGER.warning("Portal POST rejected: %s", exc)
            self._respond_json(410, {"error": "Session expired or unavailable."})
        except Exception:
            _LOGGER.exception("Portal decryption failed for session %s", session_id)
            self._respond_json(500, {"error": "Decryption failed."})

    def _respond(self, code: int, content_type: str, body: bytes) -> None:
        # Determine allowed origin for CORS — restrict to the portal's own host.
        portal_host = os.getenv("PORTAL_HOST", PORTAL_HOST)
        if _PORTAL_MODE == "cloud":
            cors_origin = f"https://{portal_host}"
        else:
            cors_origin = f"https://{portal_host}:{PORTAL_PORT}"

        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # Single-use portal — instruct browsers not to cache any response.
        self.send_header("Cache-Control",             "no-store")
        self.send_header("Pragma",                    "no-cache")
        self.send_header("X-Content-Type-Options",    "nosniff")
        self.send_header("X-Frame-Options",           "DENY")
        self.send_header("Referrer-Policy",           "no-referrer")
        self.send_header("Access-Control-Allow-Origin", cors_origin)
        self.end_headers()
        self.wfile.write(body)

    def _respond_json(self, code: int, payload: dict) -> None:
        """Respond with a safe JSON payload."""
        body = json.dumps(payload).encode("utf-8")
        self._respond(code, "application/json", body)

    def log_message(self, *args) -> None:
        pass   # Suppress default request logging to stdout


# -------------------------------------------------------------------------
# Server lifecycle (local mode only)
# -------------------------------------------------------------------------

class _ReusableHTTPServer(HTTPServer):
    """HTTPServer subclass that forces SO_REUSEADDR before binding."""
    allow_reuse_address = True


_server_started: bool = False
_server_lock:    threading.Lock = threading.Lock()


def start() -> None:
    """
    Start the portal HTTPS server in a background daemon thread.

    LOCAL MODE ONLY. In cloud mode (PORTAL_MODE=cloud), this function must not
    be called — Cloud Run uses cloud_entrypoint.py as the entry point instead.

    Generates an ephemeral self-signed TLS certificate valid for 24 hours.
    Safe to call multiple times — subsequent calls are no-ops if the server
    is already running.

    Binds to PORTAL_HOST:PORTAL_PORT from core/config.py.
    Raises PortalServerError if the server fails to bind or start.
    """
    global _server_started

    if _PORTAL_MODE == "cloud":
        _LOGGER.warning(
            "portal_server.start() called in cloud mode — this is a no-op. "
            "Cloud Run uses cloud_entrypoint.py as the entry point."
        )
        return

    with _server_lock:
        if _server_started:
            return

        cert_path, key_path = _generate_tls_cert()

        try:
            server = _ReusableHTTPServer((PORTAL_HOST, PORTAL_PORT), _PortalHandler)
            ctx    = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
            server.socket = ctx.wrap_socket(server.socket, server_side=True)
        except OSError as exc:
            raise PortalServerError(
                f"Portal server failed to bind on {PORTAL_HOST}:{PORTAL_PORT}: {exc}"
            ) from exc

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        _server_started = True
        _LOGGER.info("Portal HTTPS server started on %s:%s.", PORTAL_HOST, PORTAL_PORT)
