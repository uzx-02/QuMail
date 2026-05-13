# kme/kme_client.py — REST client for communicating with the KME (virtual or live).
# This is the ONLY file in QuMail that talks directly to the KME.
# All crypto and transport modules request keys exclusively through this file.
# In v2, only the base URL in core/config.py changes — this file stays identical.

import requests

from core.config import KME_BASE_URL, KME_KEY_SIZE, KME_TIMEOUT_SEC
from kme.key_models import KeyRequest, QuantumKey


class KMEConnectionError(Exception):
    """Raised when the KME is unreachable or returns an unexpected error."""
    pass


class KMEClient:

    def __init__(self, base_url: str = KME_BASE_URL):
        self.base_url = base_url

    # -----------------------------------------------------------------------
    # Liveness check
    # -----------------------------------------------------------------------

    def is_online(self) -> bool:
        """Return True if the KME responds to a status ping, False otherwise."""
        try:
            resp = requests.get(
                f"{self.base_url}/api/v1/status",
                timeout=KME_TIMEOUT_SEC
            )
            return resp.status_code == 200
        except requests.exceptions.RequestException:
            return False

    # -----------------------------------------------------------------------
    # Key request
    # -----------------------------------------------------------------------

    def request_key(self, key_request: KeyRequest) -> QuantumKey:
        """
        Request a fresh quantum key from the KME for a given SAE ID.
        Raises KMEConnectionError if the KME is unreachable or returns an error.
        """
        try:
            resp = requests.post(
                f"{self.base_url}/api/v1/keys",
                json={
                    "sae_id":   key_request.sae_id,
                    "key_size": key_request.key_size,
                },
                timeout=KME_TIMEOUT_SEC,
            )
        except requests.exceptions.RequestException as e:
            raise KMEConnectionError(f"KME unreachable: {e}") from e

        if resp.status_code != 200:
            raise KMEConnectionError(f"KME key request failed: {resp.status_code} — {resp.text}")

        return QuantumKey.from_dict(resp.json())

    # -----------------------------------------------------------------------
    # Key retrieval (recipient side)
    # -----------------------------------------------------------------------

    def retrieve_key(self, key_id: str) -> QuantumKey:
        """
        Retrieve a previously issued key by its UUID.
        Called by the recipient's QuMail instance before decryption.
        Raises KMEConnectionError if key is not found or KME is unreachable.
        """
        try:
            resp = requests.get(
                f"{self.base_url}/api/v1/keys/{key_id}",
                timeout=KME_TIMEOUT_SEC,
            )
        except requests.exceptions.RequestException as e:
            raise KMEConnectionError(f"KME unreachable: {e}") from e

        if resp.status_code == 404:
            raise KMEConnectionError(f"Key not found in KME: {key_id}")
        if resp.status_code != 200:
            raise KMEConnectionError(f"KME retrieval failed: {resp.status_code} — {resp.text}")

        return QuantumKey.from_dict(resp.json())

    # -----------------------------------------------------------------------
    # SAE registration
    # -----------------------------------------------------------------------

    def register_sae(self, email: str) -> str:
        """
        Register an email address as a QuMail SAE with the KME.
        Returns the assigned SAE ID string.
        Raises KMEConnectionError on failure.
        """
        try:
            resp = requests.post(
                f"{self.base_url}/api/v1/sae/register",
                json={"email": email},
                timeout=KME_TIMEOUT_SEC,
            )
        except requests.exceptions.RequestException as e:
            raise KMEConnectionError(f"KME unreachable: {e}") from e

        if resp.status_code not in (200, 201):
            raise KMEConnectionError(f"SAE registration failed: {resp.status_code} — {resp.text}")

        return resp.json()["sae_id"]

    # -----------------------------------------------------------------------
    # SAE lookup (used by transport/recipient_check.py)
    # -----------------------------------------------------------------------

    def lookup_sae(self, email: str) -> tuple[bool, str | None]:
        """
        Check whether a recipient email is a registered QuMail SAE.
        Returns (True, sae_id) if registered, (False, None) if not.
        Raises KMEConnectionError if KME is unreachable.
        """
        try:
            resp = requests.get(
                f"{self.base_url}/api/v1/sae/lookup",
                params={"email": email},
                timeout=KME_TIMEOUT_SEC,
            )
        except requests.exceptions.RequestException as e:
            raise KMEConnectionError(f"KME unreachable: {e}") from e

        if resp.status_code != 200:
            raise KMEConnectionError(f"SAE lookup failed: {resp.status_code} — {resp.text}")

        data = resp.json()
        return data["registered"], data.get("sae_id")


# ---------------------------------------------------------------------------
# Shared instance — import this rather than instantiating KMEClient directly
# ---------------------------------------------------------------------------

kme_client = KMEClient()
