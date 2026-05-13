# portal/portal_crypto.py — Decryption bridge for the secure web portal.
# Single responsibility: accept ciphertext, metadata, and a private key from
# portal_server.py and return plaintext by delegating to tqr.decrypt().
# This file exists as an isolation layer — portal_server.py never imports
# from crypto/ directly, keeping the dependency boundary clean.
# Do not import from transport/, mime/, certificates/, kme/, or ui/.

from crypto.tqr import decrypt, TQRDecryptionError, TQRMissingPrivateKeyError


# -------------------------------------------------------------------------
# Custom Exceptions
# -------------------------------------------------------------------------

class PortalDecryptionError(Exception):
    """
    Raised when decryption fails during the portal retrieval flow.
    Wraps TQR-layer exceptions so portal_server.py has a single
    exception type to catch and report to the browser.
    """
    pass


# -------------------------------------------------------------------------
# Public interface
# -------------------------------------------------------------------------

def decrypt_for_portal(
    ciphertext:  bytes,
    metadata:    dict,
    private_key: bytes,
) -> bytes:
    """
    Decrypt a portal-destined message and return the plaintext.

    Called exclusively by portal_server.py from the /retrieve POST route
    after a non-QuMail recipient opens their portal link. The session
    is marked consumed by portal_server.py immediately after this returns.

    All three TQR levels are supported in principle, but in practice this
    path is only reached for Level 3 messages — Level 1 and Level 2 require
    both sender and recipient to be registered QuMail SAEs, so the portal
    flow is never triggered for those levels. The private_key argument is
    always populated here; tqr.decrypt() will raise if it is somehow absent.

    Args:
        ciphertext:  Encrypted bytes from the portal session store.
        metadata:    Crypto metadata dict from the portal session store.
                     Must contain 'tqr_level' and all level-specific fields.
        private_key: ML-KEM private key from the portal session store.
                     Passed directly to tqr.decrypt() as private_key=.

    Returns:
        Recovered plaintext as bytes. The caller (portal_server.py) encodes
        this as base64 JSON for transmission to portal.html.

    Raises:
        PortalDecryptionError: If tqr.decrypt() fails for any reason.
    """
    try:
        return decrypt(
            ciphertext=  ciphertext,
            metadata=    metadata,
            private_key= private_key,
        )
    except (TQRDecryptionError, TQRMissingPrivateKeyError) as exc:
        raise PortalDecryptionError(
            f"Portal decryption failed: {exc}"
        ) from exc
    except Exception as exc:
        raise PortalDecryptionError(
            f"Unexpected error during portal decryption: {exc}"
        ) from exc
