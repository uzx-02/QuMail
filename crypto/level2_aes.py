# crypto/level2_aes.py — Level 2 TQR encryption: AES-256-GCM seeded with a QKD-delivered key.
# Single responsibility: AES-256-GCM encrypt and decrypt using a QuantumKey passed in
# by tqr.py as the raw 256-bit AES key material. Nonce is generated fresh per message.
# Do not call kme_client here — tqr.py requests the key and passes it in.
# Do not import from transport/, ui/, mime/, portal/, or certificates/.
# Do not implement Level 1 or Level 3 logic here.

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from kme.key_models import QuantumKey


# -------------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------------

_NONCE_SIZE_BYTES:  int = 12   # 96-bit nonce — GCM standard recommendation
_AES_KEY_SIZE_BYTES: int = 32  # 256 bits — must match KME_KEY_SIZE in core/config.py


# -------------------------------------------------------------------------
# Custom Exceptions
# -------------------------------------------------------------------------

class AESKeyLengthError(Exception):
    """
    Raised when the QKD key is not exactly 32 bytes (256 bits).
    AES-256 requires a fixed 256-bit key — unlike Level 1, this is a hard
    algorithm constraint, not a message-length constraint.
    tqr.py must always request key_size=256 for Level 2 regardless of plaintext size.
    """
    pass


class AESEncryptionError(Exception):
    """Raised when AES-256-GCM encryption fails for an unexpected reason."""
    pass


class AESDecryptionError(Exception):
    """
    Raised when AES-256-GCM decryption or authentication fails.
    A failed GCM tag verification means the ciphertext has been tampered with
    or the wrong key was used — both are treated as authentication failures.
    """
    pass


# -------------------------------------------------------------------------
# Encrypt
# -------------------------------------------------------------------------

def encrypt(plaintext: bytes, key: QuantumKey) -> dict:
    """
    Encrypt plaintext using AES-256-GCM with a QKD-delivered 256-bit key.

    The QKD key_value is used directly as the AES key — no KDF step. This is
    valid because QKD keys are already quantum-sourced, uniformly random bytes.
    A fresh 12-byte nonce is generated per call using os.urandom.

    The nonce and GCM authentication tag are stored in metadata so that
    decapsulator.py can pass them to decrypt() at the recipient's side.
    The plaintext itself is not length-constrained — AES-GCM handles arbitrary sizes.

    Returns a dict:
        {
            "ciphertext": bytes,       ← raw AES-GCM ciphertext (no nonce prepended)
            "metadata": {
                "tqr_level": 2,
                "algorithm": "AES-256-GCM",
                "key_id":    str,      ← UUID for cert logging and KME retrieval
                "sae_id":   str,
                "issued_at": str,      ← UTC ISO timestamp from KME
                "nonce":     str,      ← hex-encoded 12-byte nonce
                "tag":       str,      ← hex-encoded 16-byte GCM authentication tag
            }
        }
    """
    if len(key.key_value) != _AES_KEY_SIZE_BYTES:
        raise AESKeyLengthError(
            f"AES-256-GCM requires exactly {_AES_KEY_SIZE_BYTES} bytes (256 bits). "
            f"Got {len(key.key_value)} bytes. "
            f"Ensure tqr.py always requests key_size=256 for Level 2."
        )

    try:
        nonce = os.urandom(_NONCE_SIZE_BYTES)
        aesgcm = AESGCM(key.key_value)

        # AESGCM.encrypt() appends the 16-byte GCM tag to the ciphertext.
        # We split them so the tag can be stored and logged independently.
        combined = aesgcm.encrypt(nonce, plaintext, associated_data=None)
        ciphertext, tag = combined[:-16], combined[-16:]

    except AESKeyLengthError:
        raise
    except Exception as exc:
        raise AESEncryptionError(f"AES-256-GCM encrypt failed: {exc}") from exc

    return {
        "ciphertext": ciphertext,
        "metadata": {
            "tqr_level": 2,
            "algorithm": "AES-256-GCM",
            "key_id":    key.key_id,
            "sae_id":    key.sae_id,
            "issued_at": key.issued_at,
            "nonce":     nonce.hex(),
            "tag":       tag.hex(),
        },
    }


# -------------------------------------------------------------------------
# Decrypt
# -------------------------------------------------------------------------

def decrypt(ciphertext: bytes, key: QuantumKey, nonce_hex: str, tag_hex: str) -> bytes:
    """
    Decrypt and authenticate AES-256-GCM ciphertext using the original QKD key.

    tqr.py retrieves the nonce and tag from the MIME metadata (via decapsulator.py)
    and the correct QuantumKey from kme_client using the stored key_id, then passes
    all three here. This module never contacts the KME or MIME layer directly.

    Raises AESDecryptionError if the GCM tag does not verify — this covers both
    wrong-key and tampered-ciphertext scenarios. The caller should treat this as
    a hard failure and not attempt recovery.

    Returns the recovered plaintext as bytes.
    """
    if len(key.key_value) != _AES_KEY_SIZE_BYTES:
        raise AESKeyLengthError(
            f"AES-256-GCM requires exactly {_AES_KEY_SIZE_BYTES} bytes (256 bits). "
            f"Got {len(key.key_value)} bytes."
        )

    try:
        nonce = bytes.fromhex(nonce_hex)
        tag   = bytes.fromhex(tag_hex)

        aesgcm = AESGCM(key.key_value)

        # Re-combine ciphertext + tag for AESGCM.decrypt(), which expects them joined.
        combined  = ciphertext + tag
        plaintext = aesgcm.decrypt(nonce, combined, associated_data=None)

    except AESKeyLengthError:
        raise
    except Exception as exc:
        raise AESDecryptionError(
            f"AES-256-GCM decrypt or authentication failed. "
            f"Ciphertext may be tampered or the wrong key was used. Detail: {exc}"
        ) from exc

    return plaintext
