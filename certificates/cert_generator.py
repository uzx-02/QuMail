# certificates/cert_generator.py — Encryption audit certificate generator.
# Single responsibility: produce a structured JSON certificate for every sent
# email, capturing the key UUID, algorithm, TQR level, timestamp, sender address,
# and a SHA-256 hash of the recipient address. Write it to CERT_OUTPUT_DIR.
# Does not produce PDF output — that is pdf_export.py's responsibility.
# Do not import from transport/, ui/, portal/, kme/, or crypto/.

import hashlib
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass

from core.config import APP_NAME, APP_VERSION, CERT_OUTPUT_DIR


# -------------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------------

# Human-readable algorithm labels keyed by TQR level integer.
# Used in the certificate and surfaced in the PDF by pdf_export.py.
_ALGORITHM_LABELS: dict[int, str] = {
    1: "One-Time Pad (QKD-delivered key)",
    2: "AES-256-GCM (QKD-seeded key)",
    3: "ML-KEM-768 + AES-256-GCM (FIPS 203)",
}


# -------------------------------------------------------------------------
# Custom Exceptions
# -------------------------------------------------------------------------

class CertGenerationError(Exception):
    """Raised when certificate generation or disk write fails."""
    pass


# -------------------------------------------------------------------------
# Certificate model
# -------------------------------------------------------------------------

@dataclass
class EncryptionCertificate:
    """
    Structured encryption audit record for a single sent email.

    cert_id        : UUID4 uniquely identifying this certificate.
    app_name       : Always "QuMail" — for forward compatibility parsing.
    app_version    : QuMail version that generated this certificate.
    timestamp_utc  : ISO 8601 UTC timestamp of the send event.
    tqr_level      : TQR level used (1, 2, or 3).
    algorithm      : Human-readable algorithm label for the TQR level.
    key_id         : UUID of the QKD key used (Level 1 / 2). Empty string for Level 3.
    sender         : Sender's email address in plain text.
    recipient_hash : SHA-256 hex digest of the recipient's email address.
                     The recipient's address is hashed rather than stored in
                     plain text so certificates can be shared without disclosing
                     communication partners.
    """
    cert_id:        str
    app_name:       str
    app_version:    str
    timestamp_utc:  str
    tqr_level:      int
    algorithm:      str
    key_id:         str
    sender:         str
    recipient_hash: str


# -------------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------------

def _hash_recipient(recipient_email: str) -> str:
    """Return the SHA-256 hex digest of the recipient's email address (lowercased)."""
    return hashlib.sha256(recipient_email.lower().encode("utf-8")).hexdigest()


def _iso_utc_now() -> str:
    """Return the current UTC time as an ISO 8601 string (e.g. '2026-03-26T14:05:00Z')."""
    import datetime
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_cert_dir() -> str:
    """
    Create CERT_OUTPUT_DIR if it does not exist and return its absolute path.
    Raises CertGenerationError if the directory cannot be created.
    """
    try:
        os.makedirs(CERT_OUTPUT_DIR, exist_ok=True)
        return os.path.abspath(CERT_OUTPUT_DIR)
    except OSError as exc:
        raise CertGenerationError(
            f"Cannot create certificate output directory '{CERT_OUTPUT_DIR}': {exc}"
        ) from exc


def _build_certificate(
    tqr_level:       int,
    key_id:          str,
    sender:          str,
    recipient_email: str,
) -> EncryptionCertificate:
    """
    Construct an EncryptionCertificate dataclass from send-event data.

    Raises CertGenerationError if tqr_level is not recognised.
    """
    if tqr_level not in _ALGORITHM_LABELS:
        raise CertGenerationError(
            f"Unrecognised TQR level '{tqr_level}' — cannot determine algorithm label."
        )

    return EncryptionCertificate(
        cert_id=        str(uuid.uuid4()),
        app_name=       APP_NAME,
        app_version=    APP_VERSION,
        timestamp_utc=  _iso_utc_now(),
        tqr_level=      tqr_level,
        algorithm=      _ALGORITHM_LABELS[tqr_level],
        key_id=         key_id,
        sender=         sender,
        recipient_hash= _hash_recipient(recipient_email),
    )


def _write_json(cert: EncryptionCertificate, cert_dir: str) -> str:
    """
    Serialize the certificate to JSON and write it to cert_dir.

    Filename: qumail_cert_{cert_id}.json
    Returns the absolute path of the written file.
    Raises CertGenerationError on serialization or write failure.
    """
    filename = f"qumail_cert_{cert.cert_id}.json"
    filepath = os.path.join(cert_dir, filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(asdict(cert), f, indent=2)
    except (OSError, TypeError) as exc:
        raise CertGenerationError(
            f"Failed to write certificate to '{filepath}': {exc}"
        ) from exc
    return filepath


# -------------------------------------------------------------------------
# Public interface
# -------------------------------------------------------------------------

def generate(
    tqr_level:       int,
    key_id:          str,
    sender:          str,
    recipient_email: str,
) -> tuple[EncryptionCertificate, str]:
    """
    Generate and persist a JSON encryption certificate for a completed send event.

    Called by compose_window.py immediately after smtp_sender.send_email() succeeds.
    The returned cert object and file path are stored in core/session.py
    (session.last_cert_path) so pdf_export.py can locate the file without
    re-scanning the directory.

    Args:
        tqr_level:       Effective TQR level used for this send (1, 2, or 3).
                         Must be the resolved level after any downgrade — not the
                         user-selected level.
        key_id:          UUID string of the QKD key used. Pass an empty string
                         for Level 3, which does not involve a KME key.
        sender:          Sender's email address — stored in plain text.
        recipient_email: Recipient's email address — stored as SHA-256 hash only.

    Returns:
        A 2-tuple of (EncryptionCertificate, json_file_path: str).
        json_file_path is the absolute path to the written JSON file, which
        pdf_export.py reads directly.

    Raises:
        CertGenerationError: If any stage of generation or disk write fails.
    """
    cert_dir = _ensure_cert_dir()
    cert     = _build_certificate(tqr_level, key_id, sender, recipient_email)
    path     = _write_json(cert, cert_dir)
    return cert, path
