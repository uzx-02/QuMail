# crypto/level1_otp.py — Level 1 TQR encryption: One-Time Pad using a QKD-delivered key.
# Single responsibility: XOR-based OTP encrypt and decrypt, operating on a QuantumKey
# passed in by tqr.py. Key acquisition is NOT this module's concern.
# Do not call kme_client here — tqr.py requests the key and passes it in pre-sized.
# Do not import from transport/, ui/, mime/, portal/, or certificates/.
# Do not implement Level 2 or Level 3 logic here.

from kme.key_models import QuantumKey


# -------------------------------------------------------------------------
# Custom Exceptions
# -------------------------------------------------------------------------

class OTPKeyLengthError(Exception):
    """
    Raised when the QKD key length does not exactly match the plaintext or
    ciphertext length. True OTP requires a 1:1 byte correspondence.
    If raised at encrypt time, the caller (tqr.py) requested the wrong key_size.
    """
    pass


class OTPEncryptionError(Exception):
    """Raised when the XOR encrypt operation fails for an unexpected reason."""
    pass


class OTPDecryptionError(Exception):
    """Raised when the XOR decrypt operation fails for an unexpected reason."""
    pass


# -------------------------------------------------------------------------
# Encrypt
# -------------------------------------------------------------------------

def encrypt(plaintext: bytes, key: QuantumKey) -> dict:
    """
    Encrypt plaintext using One-Time Pad XOR with a QKD-delivered key.

    The key must be exactly the same length as the plaintext. This is enforced
    strictly — OTP is only information-theoretically secure when this holds.
    tqr.py is responsible for requesting a key with key_size = len(plaintext) * 8
    before calling this function.

    Returns a dict:
        {
            "ciphertext": bytes,
            "metadata": {
                "tqr_level":        1,
                "algorithm":        "OTP",
                "key_id":           str,   ← UUID for cert logging and KME retrieval
                "sae_id":           str,
                "issued_at":        str,   ← UTC ISO timestamp from KME
                "plaintext_length": int,   ← bytes; used by decrypt to validate
            }
        }
    """
    if len(key.key_value) != len(plaintext):
        raise OTPKeyLengthError(
            f"OTP requires key length == plaintext length. "
            f"Got key={len(key.key_value)} bytes, plaintext={len(plaintext)} bytes. "
            f"Ensure tqr.py passes key_size = len(plaintext) * 8 to KeyRequest."
        )

    try:
        ciphertext = bytes(p ^ k for p, k in zip(plaintext, key.key_value))
    except Exception as exc:
        raise OTPEncryptionError(f"OTP XOR encrypt failed: {exc}") from exc

    return {
        "ciphertext": ciphertext,
        "metadata": {
            "tqr_level":        1,
            "algorithm":        "OTP",
            "key_id":           key.key_id,
            "sae_id":           key.sae_id,
            "issued_at":        key.issued_at,
            "plaintext_length": len(plaintext),
        },
    }


# -------------------------------------------------------------------------
# Decrypt
# -------------------------------------------------------------------------

def decrypt(ciphertext: bytes, key: QuantumKey) -> bytes:
    """
    Decrypt OTP ciphertext by XOR-ing with the same QKD key used at encryption.

    The key must be exactly the same length as the ciphertext. tqr.py retrieves
    the correct key from kme_client using the key_id stored in the MIME metadata,
    then passes it here. This module never contacts the KME directly.

    Returns the recovered plaintext as bytes.
    """
    if len(key.key_value) != len(ciphertext):
        raise OTPKeyLengthError(
            f"OTP requires key length == ciphertext length. "
            f"Got key={len(key.key_value)} bytes, ciphertext={len(ciphertext)} bytes."
        )

    try:
        plaintext = bytes(c ^ k for c, k in zip(ciphertext, key.key_value))
    except Exception as exc:
        raise OTPDecryptionError(f"OTP XOR decrypt failed: {exc}") from exc

    return plaintext
