# crypto/tqr.py — TQR (Tiered Quantum Resilience) dispatcher.
# Single responsibility: sole public entry point into the crypto layer.
# Routes encrypt/decrypt calls to the correct level module based on TQR level,
# handles automatic Level 3 downgrade for non-QuMail recipients, and manages
# all KME key requests on behalf of level1 and level2 (they never call kme_client).
# Do not perform any encryption logic here — delegate entirely to level modules.
# Do not import from transport/, ui/, mime/, portal/, or certificates/.

from kme.key_models   import KeyRequest, QuantumKey
from kme.kme_client   import kme_client          # shared singleton
from crypto           import level1_otp
from crypto           import level2_aes


# -------------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------------

_VALID_TQR_LEVELS: tuple[int, ...] = (1, 2, 3)
_LEVEL2_KEY_BITS:  int             = 256   # AES-256 fixed key width — never changes
_OTP_MIN_BYTES:    int             = 16    # KME floor is 128 bits — pad short plaintexts


# -------------------------------------------------------------------------
# Custom Exceptions
# -------------------------------------------------------------------------

class TQRLevelError(Exception):
    """Raised when an unsupported or invalid TQR level is requested."""
    pass


class TQRKeyError(Exception):
    """Raised when the KME fails to deliver a key required for Level 1 or Level 2."""
    pass


class TQREncryptionError(Exception):
    """Raised when the delegated level module raises an unexpected error at encrypt time."""
    pass


class TQRDecryptionError(Exception):
    """Raised when the delegated level module raises an unexpected error at decrypt time."""
    pass


class TQRMissingPrivateKeyError(Exception):
    """
    Raised when decrypt() is called for a Level 3 message but no private_key is supplied.
    In v1, Level 3 decryption inside the QuMail client requires the private key that was
    stored by portal_server.py at send time. The caller (inbox_view.py) must retrieve and
    pass it in — tqr.py cannot access the portal layer directly.
    """
    pass


# -------------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------------

def _request_key(sae_id: str, key_size_bits: int) -> QuantumKey:
    """
    Request a fresh QKD key from the KME via the shared kme_client singleton.
    Only called at encrypt time for Level 1 and Level 2 — Level 3 needs no KME key.

    Raises TQRKeyError if the KME request fails for any reason.
    """
    try:
        request = KeyRequest(sae_id=sae_id, key_size=key_size_bits)
        return kme_client.request_key(request)
    except Exception as exc:
        raise TQRKeyError(
            f"KME key request failed for SAE '{sae_id}' "
            f"(requested {key_size_bits} bits): {exc}"
        ) from exc


def _retrieve_key(key_id: str) -> QuantumKey:
    """
    Retrieve a previously issued key by UUID from the KME.
    Only called at decrypt time for Level 1 and Level 2 — the key_id is extracted
    from the MIME metadata by decapsulator.py and passed through via tqr.decrypt().

    Raises TQRKeyError if the key is not found or the KME is unreachable.
    """
    try:
        return kme_client.retrieve_key(key_id)
    except Exception as exc:
        raise TQRKeyError(
            f"KME key retrieval failed for key_id '{key_id}': {exc}"
        ) from exc


def _resolve_level(requested_level: int, recipient_is_qumail: bool) -> int:
    """
    Resolve the effective TQR level, applying automatic downgrade if needed.

    If the recipient is not a registered QuMail endpoint, the level is forced
    to 3 (ML-KEM) regardless of what the user selected. This is the TQR downgrade
    defined in ARCHITECTURE.md and the project abstract (§5).

    Raises TQRLevelError if the requested level is not in _VALID_TQR_LEVELS.
    """
    if requested_level not in _VALID_TQR_LEVELS:
        raise TQRLevelError(
            f"Invalid TQR level: {requested_level}. "
            f"Must be one of {_VALID_TQR_LEVELS}."
        )
    if not recipient_is_qumail:
        return 3   # Automatic TQR downgrade — non-QuMail recipient
    return requested_level


def _pad_plaintext(plaintext: bytes) -> tuple[bytes, int]:
    """
    Pad plaintext to at least _OTP_MIN_BYTES so the KME key size request never
    falls below its 128-bit floor. Zero bytes are appended; the pad length is
    returned separately so it can be stored in metadata and stripped at decrypt time.

    If the plaintext already meets the minimum, pad_length is 0 and the
    plaintext is returned unchanged.
    """
    deficit = _OTP_MIN_BYTES - len(plaintext)
    if deficit <= 0:
        return plaintext, 0
    return plaintext + b"\x00" * deficit, deficit


def _unpad_plaintext(plaintext: bytes, pad_length: int) -> bytes:
    """
    Strip pad_length zero bytes from the end of a decrypted OTP plaintext.
    If pad_length is 0 (message was already long enough), returns unchanged.
    """
    if pad_length <= 0:
        return plaintext
    return plaintext[:-pad_length]


# -------------------------------------------------------------------------
# Encrypt
# -------------------------------------------------------------------------

def encrypt(
    plaintext:          bytes,
    tqr_level:          int,
    sae_id:             str,
    recipient_is_qumail: bool,
) -> dict:
    """
    Encrypt plaintext at the specified TQR level, with automatic downgrade
    to Level 3 if the recipient is not a registered QuMail endpoint.

    Args:
        plaintext:           Raw message bytes to encrypt.
        tqr_level:           User-selected or default TQR level (1, 2, or 3).
        sae_id:              Recipient SAE ID — used for KME key binding (L1/L2 only).
        recipient_is_qumail: From recipient_check.py. False triggers Level 3 downgrade.

    Returns the standard crypto output dict:
        {
            "ciphertext": bytes,
            "metadata":   dict,      ← level-specific; always includes "tqr_level"
            "private_key": bytes,    ← Level 3 ONLY. tqr.py extracts and returns
                                       this separately so the caller can route it
                                       to portal_server.py without touching the dict.
        }

    Note: For Level 3, the caller receives a second return value — the private key.
    See return convention described in the Returns section below.

    Effective return:
        Level 1 / 2:  (result_dict, None)
        Level 3:      (result_dict, private_key_bytes)

    tqr.py always returns a 2-tuple so callers have a consistent signature.
    """
    effective_level = _resolve_level(tqr_level, recipient_is_qumail)

    try:
        # --- Level 1: OTP — key sized to padded plaintext, pad_length stored in metadata ---
        if effective_level == 1:
            padded, pad_length = _pad_plaintext(plaintext)
            key    = _request_key(sae_id, key_size_bits=len(padded) * 8)
            result = level1_otp.encrypt(padded, key)
            result["metadata"]["pad_length"] = pad_length
            return result, None

        # --- Level 2: AES-256-GCM — fixed 256-bit QKD key ---
        elif effective_level == 2:
            key    = _request_key(sae_id, key_size_bits=_LEVEL2_KEY_BITS)
            result = level2_aes.encrypt(plaintext, key)
            return result, None

        # --- Level 3: ML-KEM-768 + AES-256-GCM — no KME required ---
        elif effective_level == 3:
            from crypto import level3_mlkem
            import uuid

            public_key, private_key = level3_mlkem.generate_keypair()
            result                  = level3_mlkem.encrypt(plaintext, public_key, private_key)
            # Persist a local key identifier to allow sender-side inbox decryption lookup.
            result["metadata"]["key_id"] = str(uuid.uuid4())

            # Extract private_key from result before returning — it must never
            # be passed to encapsulator.py or included in the MIME structure.
            private_key_out = result.pop("private_key")
            return result, private_key_out

    except (TQRLevelError, TQRKeyError):
        raise
    except Exception as exc:
        raise TQREncryptionError(
            f"TQR Level {effective_level} encryption failed unexpectedly: {exc}"
        ) from exc


# -------------------------------------------------------------------------
# Decrypt
# -------------------------------------------------------------------------

def decrypt(
    ciphertext:  bytes,
    metadata:    dict,
    private_key: bytes | None = None,
) -> bytes:
    """
    Decrypt ciphertext using the TQR level and auxiliary data stored in metadata.

    Args:
        ciphertext:  Raw encrypted bytes from decapsulator.py.
        metadata:    Metadata dict extracted from the MIME control part by
                     decapsulator.py. Must include "tqr_level" and all
                     level-specific fields (key_id, nonce, tag, kem_ciphertext, etc.).
        private_key: Required for Level 3 only. The ML-KEM private key stored
                     by portal_server.py at send time. The caller (inbox_view.py)
                     is responsible for retrieving and passing it here.
                     Ignored for Level 1 and Level 2.

    For Level 1 and Level 2, the exact key issued at send time is retrieved from
    the KME using metadata["key_id"] via kme_client.retrieve_key(). The sae_id
    is not needed at decrypt time — the UUID is the precise lookup handle.

    Returns the recovered plaintext as bytes.
    Raises TQRDecryptionError (or TQRMissingPrivateKeyError for Level 3)
    on any failure.
    """
    level = metadata.get("tqr_level")

    if level not in _VALID_TQR_LEVELS:
        raise TQRLevelError(
            f"Unrecognised tqr_level in metadata: {level!r}. "
            f"Cannot determine decryption path."
        )

    try:
        # --- Level 1: OTP — retrieve exact key by UUID, unpad after decrypt ---
        if level == 1:
            key       = _retrieve_key(metadata["key_id"])
            recovered = level1_otp.decrypt(ciphertext, key)
            return _unpad_plaintext(recovered, metadata.get("pad_length", 0))

        # --- Level 2: AES-256-GCM — retrieve exact key by UUID ---
        elif level == 2:
            key = _retrieve_key(metadata["key_id"])
            return level2_aes.decrypt(
                ciphertext,
                key,
                nonce_hex=metadata["nonce"],
                tag_hex=  metadata["tag"],
            )

        # --- Level 3: ML-KEM-768 + AES-256-GCM — private key from portal store ---
        elif level == 3:
            from crypto import level3_mlkem
            if private_key is None:
                raise TQRMissingPrivateKeyError(
                    "Level 3 decrypt requires the ML-KEM private key. "
                    "Retrieve it from portal_server.py session store and pass it "
                    "as private_key= to tqr.decrypt()."
                )
            return level3_mlkem.decrypt(
                ciphertext,
                private_key,
                kem_ciphertext_hex=metadata["kem_ciphertext"],
                nonce_hex=         metadata["nonce"],
                tag_hex=           metadata["tag"],
            )

    except (TQRLevelError, TQRKeyError, TQRMissingPrivateKeyError):
        raise
    except Exception as exc:
        raise TQRDecryptionError(
            f"TQR Level {level} decryption failed unexpectedly: {exc}"
        ) from exc
