# mime/encapsulator.py — RFC 3156-style MIME encapsulation of encrypted QuMail payloads.
# Single responsibility: wrap a ciphertext and its associated metadata into a
# multipart/encrypted MIME message ready for smtp_sender.py to dispatch.
# Does not perform encryption, transport, or KME interaction.
# Do not import from crypto/, transport/, portal/, certificates/, kme/, or ui/.

import json
from email.message       import Message
from email.mime.multipart import MIMEMultipart
from email.mime.base      import MIMEBase
from email                import encoders

from core.config import (
    MIME_PROTOCOL,
    MIME_CONTROL_TYPE,
    MIME_PAYLOAD_TYPE,
    APP_NAME,
    APP_VERSION,
)


# -------------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------------

_CONTROL_FILENAME:  str = "qumail-control.json"   # Filename hint for the metadata part
_PAYLOAD_FILENAME:  str = "qumail-payload.bin"    # Filename hint for the ciphertext part


# -------------------------------------------------------------------------
# Custom Exceptions
# -------------------------------------------------------------------------

class EncapsulationError(Exception):
    """Raised when MIME encapsulation fails due to malformed input or serialization error."""
    pass


# -------------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------------

def _build_control_part(metadata: dict) -> MIMEBase:
    """
    Serialize the crypto metadata dict to JSON and wrap it in a MIME part.

    The control part is the first child of the multipart/encrypted structure.
    It carries all fields needed by decapsulator.py to reconstruct the
    decryption inputs: tqr_level, key_id (L1/L2), nonce, tag, kem_ciphertext (L3), etc.

    The X-QuMail-Version header is added so decapsulator.py can detect version
    mismatches between sender and recipient clients in future versions.

    Raises EncapsulationError if metadata cannot be serialized to JSON.
    """
    try:
        control_json = json.dumps(metadata, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EncapsulationError(
            f"Failed to serialize crypto metadata to JSON: {exc}"
        ) from exc

    part = MIMEBase("application", "qumail-control")
    part.set_payload(control_json)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename=_CONTROL_FILENAME)
    part.add_header("X-QuMail-Version", APP_VERSION)
    return part


def _build_payload_part(ciphertext: bytes) -> MIMEBase:
    """
    Wrap the raw ciphertext bytes in a MIME part.

    The payload part is the second child of the multipart/encrypted structure.
    It carries only the encrypted bytes — no metadata. decapsulator.py always
    reads the control part first to know how to interpret this part.
    """
    part = MIMEBase("application", "octet-stream")
    part.set_payload(ciphertext)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename=_PAYLOAD_FILENAME)
    return part


# -------------------------------------------------------------------------
# Public interface
# -------------------------------------------------------------------------

def encapsulate(
    sender:     str,
    recipient:  str,
    subject:    str,
    ciphertext: bytes,
    metadata:   dict,
) -> Message:
    """
    Wrap encrypted ciphertext and its metadata into a multipart/encrypted MIME message.

    Produces a two-part MIME structure:
      Part 1 — application/qumail-control  : JSON-serialized crypto metadata.
      Part 2 — application/octet-stream    : Raw ciphertext bytes.

    Both parts are base64-encoded for safe transit over SMTP. The outer container
    uses Content-Type: multipart/encrypted with a QuMail-specific protocol parameter
    so decapsulator.py can identify and validate QuMail messages on receipt.

    Args:
        sender:     Sender email address — written to the From header.
        recipient:  Recipient email address — written to the To header.
        subject:    Email subject line — written to the Subject header.
                    compose_window.py is responsible for providing this.
        ciphertext: Raw encrypted bytes from tqr.encrypt(). The private_key has
                    already been extracted by tqr.py before this is called.
        metadata:   Crypto metadata dict from tqr.encrypt(). Must include at minimum
                    "tqr_level". Level-specific fields (key_id, nonce, tag,
                    kem_ciphertext) are passed through without inspection.

    Returns:
        A fully-assembled email.message.Message ready for smtp_sender.send_email().
        From, To, and Subject headers are set. No further header manipulation needed.

    Raises:
        EncapsulationError: If metadata serialization fails or inputs are invalid.
    """
    if not ciphertext:
        raise EncapsulationError("Ciphertext is empty — nothing to encapsulate.")

    if "tqr_level" not in metadata:
        raise EncapsulationError(
            "Metadata is missing required field 'tqr_level'. "
            "Ensure tqr.encrypt() completed successfully before calling encapsulate()."
        )

    container = MIMEMultipart(
        "encrypted",
        protocol=MIME_PROTOCOL,
    )

    # --- Standard headers ---
    container["From"]    = sender
    container["To"]      = recipient
    container["Subject"] = subject
    container["X-Mailer"] = f"{APP_NAME}/{APP_VERSION}"

    # Keep human-readable context without adding extra MIME parts that would
    # break the strict two-part control/payload contract expected by decapsulator.py.
    container.preamble = (
        f"This message was sent using {APP_NAME} v{APP_VERSION}, a quantum-secure email client.\n"
        "Use QuMail to open and decrypt the enclosed payload."
    )
    container.attach(_build_control_part(metadata))
    container.attach(_build_payload_part(ciphertext))

    return container
