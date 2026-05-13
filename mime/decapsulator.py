# mime/decapsulator.py — MIME extraction of QuMail encrypted payloads.
# Single responsibility: parse an incoming email.message.Message object produced
# by imap_receiver.py, validate it as a QuMail-encrypted message, and extract
# the ciphertext bytes and crypto metadata dict for tqr.decrypt() to consume.
# Does not perform decryption, transport, or KME interaction.
# Do not import from crypto/, transport/, portal/, certificates/, kme/, or ui/.

import base64
import json
from email.message import Message

from core.config import MIME_PROTOCOL, MIME_CONTROL_TYPE, MIME_PAYLOAD_TYPE


# -------------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------------

# Expected MIME subtype for the outer container — "multipart/encrypted"
_EXPECTED_MAINTYPE:    str = "multipart"
_EXPECTED_SUBTYPE:     str = "encrypted"

# Expected content types for the two child parts, matched against the
# values written by encapsulator.py
_EXPECTED_CONTROL_TYPE: str = MIME_CONTROL_TYPE          # application/qumail-control
_EXPECTED_PAYLOAD_TYPE: str = "application/octet-stream" # application/octet-stream


# -------------------------------------------------------------------------
# Custom Exceptions
# -------------------------------------------------------------------------

class DecapsulationError(Exception):
    """
    Raised when the incoming message cannot be parsed as a valid QuMail
    encrypted message. Distinct from a decryption failure — this means the
    MIME structure itself is malformed, missing, or not a QuMail message at all.
    inbox_view.py should catch this and display the message as unreadable
    rather than attempting decryption.
    """
    pass


class NotQuMailMessageError(DecapsulationError):
    """
    Raised when the message is structurally valid MIME but is not a QuMail
    encrypted message (e.g. a plain-text email or a different encrypted format).
    inbox_view.py can use this to display a clear 'not a QuMail message' notice
    rather than a generic error.
    """
    pass


# -------------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------------

def _validate_outer_structure(message: Message) -> None:
    """
    Confirm the outer MIME container is multipart/encrypted with the QuMail protocol.

    Raises NotQuMailMessageError if the message is not a QuMail encrypted email.
    Raises DecapsulationError if the structure is partially matching but malformed.
    """
    maintype = message.get_content_maintype()
    subtype  = message.get_content_subtype()

    if maintype != _EXPECTED_MAINTYPE or subtype != _EXPECTED_SUBTYPE:
        raise NotQuMailMessageError(
            f"Message is not multipart/encrypted "
            f"(got {maintype}/{subtype}). Not a QuMail message."
        )

    protocol = message.get_param("protocol")
    if protocol != MIME_PROTOCOL:
        raise NotQuMailMessageError(
            f"Unrecognised MIME protocol parameter: '{protocol}'. "
            f"Expected '{MIME_PROTOCOL}'. Not a QuMail message."
        )


def _extract_parts(message: Message) -> tuple[Message, Message]:
    """
    Extract the control part and payload part from the multipart container
    by matching Content-Type headers, not by positional index.

    This makes decapsulation robust against legacy messages that may have
    a different number of parts or a different part ordering than the current
    encapsulator.py produces. Each part is identified by its Content-Type alone.

    Searches all child parts for:
      application/qumail-control  — JSON metadata (control part)
      application/octet-stream    — ciphertext bytes (payload part)

    If multiple parts share the same Content-Type, the first match is used.

    Raises DecapsulationError if either required part cannot be found.
    """
    parts = message.get_payload()

    if not isinstance(parts, list) or len(parts) == 0:
        raise DecapsulationError(
            f"QuMail message has no MIME child parts "
            f"(got {type(parts).__name__})."
        )

    control_part: Message | None = None
    payload_part: Message | None = None

    for part in parts:
        ct = part.get_content_type()
        if ct == _EXPECTED_CONTROL_TYPE and control_part is None:
            control_part = part
        elif ct == _EXPECTED_PAYLOAD_TYPE and payload_part is None:
            payload_part = part

    if control_part is None:
        raise DecapsulationError(
            f"QuMail control part not found. "
            f"Expected a part with Content-Type '{_EXPECTED_CONTROL_TYPE}'. "
            f"Message may be corrupted or from an incompatible version."
        )

    if payload_part is None:
        raise DecapsulationError(
            f"QuMail payload part not found. "
            f"Expected a part with Content-Type '{_EXPECTED_PAYLOAD_TYPE}'. "
            f"Message may be corrupted or from an incompatible version."
        )

    return control_part, payload_part


def _decode_part_bytes(part: Message) -> bytes:
    """
    Decode the raw bytes of a base64-encoded MIME part.

    encapsulator.py applies encoders.encode_base64() to both parts.
    get_payload(decode=True) reverses this transparently regardless of
    whether the Content-Transfer-Encoding header is present.
    """
    raw = part.get_payload(decode=True)
    if raw is None:
        raise DecapsulationError(
            "MIME part payload is empty or could not be decoded."
        )
    return raw


def _parse_control(control_bytes: bytes) -> dict:
    """
    Deserialize the JSON control part into a metadata dict.

    Validates that the result is a dict containing at minimum the 'tqr_level'
    field — without it, tqr.decrypt() cannot determine the decryption path.

    Raises DecapsulationError if JSON parsing fails or required fields are absent.
    """
    try:
        metadata = json.loads(control_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DecapsulationError(
            f"Failed to parse QuMail control part as JSON: {exc}"
        ) from exc

    if not isinstance(metadata, dict):
        raise DecapsulationError(
            f"Control part JSON is not a dict (got {type(metadata).__name__})."
        )

    if "tqr_level" not in metadata:
        raise DecapsulationError(
            "Control part metadata is missing required field 'tqr_level'. "
            "Message may be corrupted or from an incompatible QuMail version."
        )

    return metadata


# -------------------------------------------------------------------------
# Public interface
# -------------------------------------------------------------------------

def decapsulate(message: Message) -> tuple[bytes, dict]:
    """
    Extract ciphertext and crypto metadata from an incoming QuMail MIME message.

    Validates the outer MIME structure, extracts and decodes both child parts,
    and deserializes the control part JSON into a metadata dict. The results are
    returned directly to the caller (inbox_view.py) for passing to tqr.decrypt().

    Args:
        message: A parsed email.message.Message object from imap_receiver.py.

    Returns:
        A 2-tuple of (ciphertext: bytes, metadata: dict).
        metadata always contains 'tqr_level' and all level-specific fields
        written by the sending client's encapsulator.py.

    Raises:
        NotQuMailMessageError: Message is valid MIME but not a QuMail email.
        DecapsulationError:    Message is a QuMail email but the structure is
                               malformed or a required field is missing.
    """
    _validate_outer_structure(message)

    control_part, payload_part = _extract_parts(message)

    control_bytes = _decode_part_bytes(control_part)
    payload_bytes = _decode_part_bytes(payload_part)

    metadata = _parse_control(control_bytes)

    return payload_bytes, metadata
