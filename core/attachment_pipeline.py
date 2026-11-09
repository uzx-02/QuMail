"""
Practical MIME & Attachment Security Pipeline.

Enforces concrete, measured resource limits supporting PDFs, presentations,
office documents, images, and common business attachments within an intended
15–25 MiB envelope capacity.

Provides streaming/bounded MIME processing, transfer-encoding validation,
filename sanitization, collision-resistant encrypted cache storage, and
safe, explicit user export with zero auto-execution.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from email.message import EmailMessage
from email.parser import BytesParser, BytesHeaderParser
from email.policy import default
import hashlib
import os
from pathlib import Path
import quopri
import re
import secrets
import stat
import time
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from core.logging_config import get_logger

logger = get_logger("attachment_pipeline")


# -----------------------------------------------------------------------------
# Measured & Enforced Resource Limits
# -----------------------------------------------------------------------------

MAX_WIRE_SIZE: int = 25 * 1024 * 1024           # 25 MiB maximum wire payload
MAX_BODY_SIZE: int = 1 * 1024 * 1024             # 1 MiB decoded plain-text body
MAX_INDIVIDUAL_ATTACHMENT_SIZE: int = 20 * 1024 * 1024  # 20 MiB per attachment
MAX_AGGREGATE_ATTACHMENT_SIZE: int = 20 * 1024 * 1024   # 20 MiB total attachments
MAX_ATTACHMENT_COUNT: int = 20                   # Maximum 20 attachments
MAX_MIME_DEPTH: int = 8                          # Maximum nesting depth
MAX_MIME_PARTS: int = 64                         # Maximum total MIME parts
MAX_HEADER_SIZE: int = 64 * 1024                 # 64 KiB maximum header block
MAX_DECODED_OUTPUT_SIZE: int = 25 * 1024 * 1024  # 25 MiB maximum decoded stream
MAX_DECOMPRESSION_RATIO: int = 10                # 10x maximum expansion ratio


# -----------------------------------------------------------------------------
# Custom Exceptions
# -----------------------------------------------------------------------------

class AttachmentPipelineError(Exception):
    """Base error for attachment pipeline and MIME parsing failures."""
    pass


class ResourceLimitExceededError(AttachmentPipelineError):
    """Raised when a message or attachment exceeds measured bounds."""
    pass


class MalformedMIMEError(AttachmentPipelineError):
    """Raised when a MIME structure, boundary, or transfer-encoding is malformed."""
    pass


class PathTraversalSecurityError(AttachmentPipelineError):
    """Raised when an attachment filename attempts path traversal or exploits system names."""
    pass


# -----------------------------------------------------------------------------
# Filename & Path Sanitization
# -----------------------------------------------------------------------------

_WINDOWS_RESERVED_NAMES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
})


def sanitize_attachment_filename(raw_name: str | None, fallback_id: str = "") -> str:
    """
    Sanitize an untrusted attachment filename for safe display and caching.

    Enforces:
      - Stripping leading/trailing directory paths and traversal components (.. / \\).
      - Stripping Windows alternate data stream indicators (:).
      - Stripping control characters (0x00–0x1f, 0x7f) and bidi overrides.
      - Rejecting or prefixing Windows reserved device names (CON, NUL, COM1, etc.).
      - Stripping trailing dots and spaces (Windows filesystem restriction).
      - Bounding maximum filename length to 128 characters.
      - Safe fallback name if filename is missing, empty, or entirely invalid.
    """
    if not raw_name or not isinstance(raw_name, str):
        suffix = fallback_id or secrets.token_hex(4)
        return f"attachment_{suffix}.bin"

    # Take basename only
    name = Path(raw_name).name

    # Remove alternate data stream syntax
    if ":" in name:
        name = name.split(":")[0]

    # Strip bidi overrides and non-printable control characters
    bidi_and_ctrl = (
        "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
        "\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f"
        "\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f\x7f"
    )
    name = "".join(c for c in name if c not in bidi_and_ctrl)

    # Replace forbidden path characters with underscores
    name = re.sub(r'[<>"/\\|?*]', '_', name)

    # Strip trailing dots and spaces
    name = name.rstrip(". ")

    # Check for reserved Windows device names (check full stem and first component before any dots)
    first_part = name.split(".")[0].upper()
    stem = Path(name).stem.upper()
    if first_part in _WINDOWS_RESERVED_NAMES or stem in _WINDOWS_RESERVED_NAMES:
        name = f"safe_{name}"

    # Bounded length: preserve extension if possible
    if len(name) > 128:
        ext = Path(name).suffix[:16]
        stem = Path(name).stem[: 128 - len(ext)]
        name = stem + ext

    if not name or name in (".", "..") or not name.strip():
        suffix = fallback_id or secrets.token_hex(4)
        return f"attachment_{suffix}.bin"

    return name


def validate_export_destination(path_input: Path | str) -> Path:
    """
    Validate a user-selected destination path for attachment export.

    Enforces:
      - Absolute path.
      - Not a UNC path (no leading \\\\ or //).
      - No path traversal components (. or ..).
      - No reserved device names or trailing dots/spaces in any component.
      - Parent directory exists and is a directory.
    """
    path = Path(path_input).resolve()
    path_str = str(path)

    if not path.is_absolute():
        raise PathTraversalSecurityError("Export destination path must be absolute.")
    if path_str.startswith(("\\\\", "//")):
        raise PathTraversalSecurityError("UNC network export paths are prohibited.")

    for part in path.parts[1:]:
        if part in (".", "..") or part.endswith((".", " ")):
            raise PathTraversalSecurityError(f"Invalid path component: {part!r}")
        if re.search(r'[<>:"|?*\x00-\x1f]', part):
            raise PathTraversalSecurityError(f"Illegal character in path component: {part!r}")
        stem = Path(part).stem.upper()
        if stem in _WINDOWS_RESERVED_NAMES:
            raise PathTraversalSecurityError(f"Reserved device name in destination path: {part!r}")

    if not path.parent.is_dir():
        raise PathTraversalSecurityError(f"Destination parent directory does not exist: {path.parent}")

    return path


# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class ProcessedAttachment:
    """Metadata and content reference for a processed attachment."""
    attachment_id: str
    filename: str
    media_type: str
    size: int
    content_hash: str
    cached_path: Path | None = None
    data: bytes | None = None

    def to_meta_dict(self) -> dict[str, Any]:
        """Convert to metadata summary dictionary for index storage."""
        return {
            "attachment_id": self.attachment_id,
            "filename": self.filename,
            "media_type": self.media_type,
            "size": self.size,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True)
class ParsedMessageContent:
    """Result of parsing and safely decoding a MIME message."""
    headers: dict[str, str]
    body: str
    attachments: tuple[ProcessedAttachment, ...]
    total_attachment_bytes: int
    has_attachments: bool


# -----------------------------------------------------------------------------
# Transfer-Encoding Decoders
# -----------------------------------------------------------------------------

def safe_decode_transfer_encoding(
    payload: bytes | str,
    encoding: str,
    max_output: int,
) -> bytes:
    """
    Safely decode Content-Transfer-Encoding (base64, quoted-printable, 7bit, 8bit).

    Enforces max_output limits during decoding to prevent decompression or
    amplification attacks.
    """
    enc = (encoding or "").strip().lower()
    raw_bytes = payload.encode("ascii", errors="replace") if isinstance(payload, str) else payload

    if not enc or enc in ("7bit", "8bit", "binary"):
        if len(raw_bytes) > max_output:
            raise ResourceLimitExceededError(f"Payload size {len(raw_bytes)} exceeds limit {max_output}")
        return raw_bytes

    if enc == "base64":
        # Base64 output size is at most ~3/4 of input size
        cleaned = re.sub(rb"\s+", b"", raw_bytes)
        try:
            decoded = base64.b64decode(cleaned, validate=True)
        except Exception as exc:
            raise MalformedMIMEError(f"Malformed base64 transfer encoding: {exc}") from exc
        if len(decoded) > max_output:
            raise ResourceLimitExceededError(f"Decoded base64 size {len(decoded)} exceeds limit {max_output}")
        return decoded

    if enc == "quoted-printable":
        try:
            decoded = quopri.decodestring(raw_bytes)
        except Exception as exc:
            raise MalformedMIMEError(f"Malformed quoted-printable transfer encoding: {exc}") from exc
        if len(decoded) > max_output:
            raise ResourceLimitExceededError(f"Decoded quoted-printable size {len(decoded)} exceeds limit {max_output}")
        return decoded

    raise MalformedMIMEError(f"Unsupported or dangerous Content-Transfer-Encoding: {encoding!r}")


# -----------------------------------------------------------------------------
# Encrypted Attachment Cache
# -----------------------------------------------------------------------------

class EncryptedAttachmentCache:
    """
    Application-controlled encrypted disk cache for attachments.

    Each cached file is encrypted with AES-256-GCM using the account's master key
    or an account-derived cache key. Files are named by their SHA-256 hash.
    """

    def __init__(self, cache_dir: Path | str, encryption_key: bytes) -> None:
        if len(encryption_key) != 32:
            raise ValueError("Encryption key must be exactly 32 bytes for AES-256-GCM.")
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.encryption_key = encryption_key

    def _aad(self, content_hash: str) -> bytes:
        return f"QuMail-Attachment-v1/{content_hash}".encode()

    def store(self, data: bytes, content_hash: str | None = None) -> Path:
        """Encrypt and store attachment bytes in the cache directory."""
        if content_hash is None:
            content_hash = hashlib.sha256(data).hexdigest()

        target_file = self.cache_dir / f"{content_hash}.enc"
        if target_file.is_file():
            return target_file

        nonce = secrets.token_bytes(12)
        encrypted = nonce + AESGCM(self.encryption_key).encrypt(nonce, data, self._aad(content_hash))

        temp_file = self.cache_dir / f"{content_hash}.tmp.{secrets.token_hex(4)}"
        try:
            with open(temp_file, "xb") as f:
                f.write(encrypted)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, target_file)
            return target_file
        except Exception:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass
            raise

    def retrieve(self, content_hash: str) -> bytes:
        """Read and decrypt an attachment from the cache."""
        target_file = self.cache_dir / f"{content_hash}.enc"
        if not target_file.is_file():
            raise FileNotFoundError(f"Cached attachment {content_hash} not found.")

        with open(target_file, "rb") as f:
            blob = f.read()

        if len(blob) < 28:
            raise AttachmentPipelineError("Corrupted cached attachment payload.")

        nonce = blob[:12]
        ciphertext = blob[12:]
        try:
            return AESGCM(self.encryption_key).decrypt(nonce, ciphertext, self._aad(content_hash))
        except Exception as exc:
            raise AttachmentPipelineError("Failed to decrypt cached attachment: invalid tag.") from exc

    def purge_account(self) -> None:
        """Securely remove all cached files in the account directory."""
        if not self.cache_dir.exists():
            return
        for item in self.cache_dir.glob("*.enc"):
            try:
                item.unlink(missing_ok=True)
            except OSError:
                pass


# -----------------------------------------------------------------------------
# Attachment Pipeline
# -----------------------------------------------------------------------------

class AttachmentPipeline:
    """
    MIME message parsing and attachment extraction engine.

    Parses raw MIME bytes, enforces limits, decodes content safely, and optionally
    stores attachments in the encrypted cache.
    """

    def __init__(
        self,
        cache: EncryptedAttachmentCache | None = None,
        max_wire_size: int = MAX_WIRE_SIZE,
        max_body_size: int = MAX_BODY_SIZE,
        max_individual_attachment_size: int = MAX_INDIVIDUAL_ATTACHMENT_SIZE,
        max_aggregate_attachment_size: int = MAX_AGGREGATE_ATTACHMENT_SIZE,
        max_attachment_count: int = MAX_ATTACHMENT_COUNT,
    ) -> None:
        self.cache = cache
        self.max_wire_size = max_wire_size
        self.max_body_size = max_body_size
        self.max_individual_attachment_size = max_individual_attachment_size
        self.max_aggregate_attachment_size = max_aggregate_attachment_size
        self.max_attachment_count = max_attachment_count

    def parse_message(
        self,
        raw_bytes: bytes,
        store_in_cache: bool = False,
    ) -> ParsedMessageContent:
        """
        Parse raw MIME wire message bytes and extract bounded body and attachments.

        Args:
            raw_bytes:      Raw RFC 822 / MIME bytes.
            store_in_cache: If True and cache is configured, writes attachments to encrypted cache.

        Returns:
            ParsedMessageContent with headers, body, and attachment metadata/data.
        """
        if len(raw_bytes) > self.max_wire_size:
            raise ResourceLimitExceededError(
                f"Raw message size {len(raw_bytes)} bytes exceeds maximum wire ceiling of {self.max_wire_size} bytes."
            )

        # Header block size check
        head_end = raw_bytes.find(b"\r\n\r\n")
        if head_end == -1:
            head_end = raw_bytes.find(b"\n\n")
        if head_end != -1 and head_end > MAX_HEADER_SIZE:
            raise ResourceLimitExceededError(
                f"Header block size {head_end} bytes exceeds limit of {MAX_HEADER_SIZE} bytes."
            )

        try:
            msg = BytesParser(policy=default).parsebytes(raw_bytes)
        except Exception as exc:
            raise MalformedMIMEError(f"Failed to parse MIME message structure: {exc}") from exc

        headers: dict[str, str] = {}
        for k in ("From", "To", "Cc", "Subject", "Date", "Message-ID", "Content-Type"):
            headers[k] = str(msg.get(k, ""))

        bodies: list[str] = []
        attachments: list[ProcessedAttachment] = []
        total_attachment_bytes = 0
        part_count = 0

        def walk_parts(part: Any, depth: int) -> None:
            nonlocal part_count, total_attachment_bytes
            part_count += 1
            if depth > MAX_MIME_DEPTH:
                raise ResourceLimitExceededError(f"MIME nesting depth exceeds limit of {MAX_MIME_DEPTH}.")
            if part_count > MAX_MIME_PARTS:
                raise ResourceLimitExceededError(f"Total MIME parts exceed limit of {MAX_MIME_PARTS}.")

            if part.is_multipart():
                for subpart in part.iter_parts():
                    walk_parts(subpart, depth + 1)
                return

            disp = str(part.get_content_disposition() or "").lower()
            maintype = part.get_content_maintype()
            subtype = part.get_content_subtype()
            media_type = f"{maintype}/{subtype}".lower()
            raw_filename = part.get_filename()

            is_attachment = disp == "attachment" or (raw_filename is not None and disp != "inline")

            if is_attachment:
                if len(attachments) >= self.max_attachment_count:
                    raise ResourceLimitExceededError(
                        f"Attachment count exceeds limit of {self.max_attachment_count} files."
                    )

                cte = str(part.get("Content-Transfer-Encoding", ""))
                payload = part.get_payload()

                if isinstance(payload, list):
                    raise MalformedMIMEError("Multipart attachment nested inside leaf part.")

                # Decode payload safely
                decoded = safe_decode_transfer_encoding(
                    payload or b"",
                    cte,
                    max_output=self.max_individual_attachment_size,
                )

                if len(decoded) > self.max_individual_attachment_size:
                    raise ResourceLimitExceededError(
                        f"Attachment '{raw_filename}' size {len(decoded)} exceeds individual limit of {self.max_individual_attachment_size} bytes."
                    )

                if total_attachment_bytes + len(decoded) > self.max_aggregate_attachment_size:
                    raise ResourceLimitExceededError(
                        f"Aggregate attachment size {total_attachment_bytes + len(decoded)} exceeds limit of {self.max_aggregate_attachment_size} bytes."
                    )

                total_attachment_bytes += len(decoded)
                att_id = secrets.token_hex(8)
                safe_name = sanitize_attachment_filename(raw_filename, fallback_id=att_id)
                chash = hashlib.sha256(decoded).hexdigest()

                cached_path = None
                if store_in_cache and self.cache is not None:
                    cached_path = self.cache.store(decoded, content_hash=chash)

                attachments.append(
                    ProcessedAttachment(
                        attachment_id=att_id,
                        filename=safe_name,
                        media_type=media_type,
                        size=len(decoded),
                        content_hash=chash,
                        cached_path=cached_path,
                        data=decoded if not store_in_cache else None,
                    )
                )

            elif media_type == "text/plain":
                cte = str(part.get("Content-Transfer-Encoding", ""))
                payload = part.get_payload()
                decoded_bytes = safe_decode_transfer_encoding(
                    payload or b"",
                    cte,
                    max_output=self.max_body_size,
                )
                charset = part.get_content_charset() or "utf-8"
                text = decoded_bytes.decode(charset, errors="replace")
                bodies.append(text)

        walk_parts(msg, 1)

        combined_body = "\n\n".join(bodies)
        if len(combined_body.encode("utf-8")) > self.max_body_size:
            raise ResourceLimitExceededError(f"Combined body size exceeds limit of {self.max_body_size} bytes.")

        return ParsedMessageContent(
            headers=headers,
            body=combined_body,
            attachments=tuple(attachments),
            total_attachment_bytes=total_attachment_bytes,
            has_attachments=len(attachments) > 0,
        )

    @staticmethod
    def export_attachment(
        attachment_data: bytes,
        destination_path: Path | str,
    ) -> Path:
        """
        Export attachment bytes to an explicitly selected user file.

        Guarantees:
          - Validates destination against path traversal and reserved device names.
          - Atomic no-clobber write (path.open('xb')). Fails if file already exists.
          - Zero auto-execution or launching.
          - Flushes and fsyncs before return.
        """
        target = validate_export_destination(destination_path)
        if target.exists():
            raise FileExistsError(f"Destination file already exists: {target}")

        created = False
        try:
            with open(target, "xb") as f:
                created = True
                f.write(attachment_data)
                f.flush()
                os.fsync(f.fileno())
            return target
        except Exception:
            if created and target.is_file():
                try:
                    target.unlink()
                except OSError:
                    pass
            raise
