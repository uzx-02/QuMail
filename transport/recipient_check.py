# transport/recipient_check.py — Recipient QuMail endpoint detection.
# Single responsibility: query the KME to determine whether a recipient email address
# has a registered SAE ID, and return a structured result for tqr.py to act on.
# This module does not perform encryption, send email, or trigger the TQR downgrade
# itself — it only reports the recipient's status. tqr.py owns the downgrade decision.
# Do not import from crypto/, ui/, mime/, portal/, or certificates/.

from dataclasses import dataclass

from kme.kme_client import kme_client          # shared singleton


# -------------------------------------------------------------------------
# Custom Exceptions
# -------------------------------------------------------------------------

class RecipientCheckError(Exception):
    """
    Raised when the KME lookup fails for a reason other than the recipient
    simply not being registered (e.g. KME unreachable, malformed response).
    A recipient not found in the KME is NOT an error — it returns is_qumail=False.
    """
    pass


# -------------------------------------------------------------------------
# Result Model
# -------------------------------------------------------------------------

@dataclass
class RecipientStatus:
    """
    Result of a recipient endpoint check.

    is_qumail : True if the recipient has a registered SAE ID in the KME.
                False triggers automatic TQR downgrade to Level 3 in tqr.py.
    email     : The queried email address, echoed back for caller convenience.
    sae_id    : The recipient's SAE ID if found; None if not registered.
    """
    is_qumail: bool
    email:     str
    sae_id:    str | None


# -------------------------------------------------------------------------
# Check
# -------------------------------------------------------------------------

def check_recipient(email: str) -> RecipientStatus:
    """
    Query the KME for a registered SAE ID matching the given email address.

    Calls kme_client.lookup_sae(email), which returns (registered: bool, sae_id: str | None).
    If registered is False, is_qumail is set to False and sae_id is None — this is
    normal operating behaviour for non-QuMail recipients, not an error condition.

    Raises RecipientCheckError only if the KME itself is unreachable or returns
    a malformed response — i.e. the check could not be completed at all.

    Args:
        email: Recipient's email address as a plain string.

    Returns:
        RecipientStatus dataclass — consumed by tqr.encrypt() via compose_window.py.
    """
    try:
        registered, sae_id = kme_client.lookup_sae(email)
    except Exception as exc:
        raise RecipientCheckError(
            f"KME SAE lookup failed for '{email}'. "
            f"Check KME connection status. Detail: {exc}"
        ) from exc

    return RecipientStatus(
        is_qumail=registered,
        email=    email,
        sae_id=   sae_id,
    )
