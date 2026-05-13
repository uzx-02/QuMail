# kme/key_models.py — Data models for QKD key objects.
# No logic here. Pure data structures passed between kme_client and crypto modules.
# Do not import from any other QuMail module here.

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class QuantumKey:
    """
    Represents a single QKD-delivered key as per ETSI GS QKD 014.
    key_id   : UUID uniquely identifying this key — logged in the encryption cert.
    key_value: Raw key bytes. Length matches requested size (default 32 bytes = 256 bits).
    sae_id   : SAE ID of the recipient this key is bound to.
    issued_at: UTC timestamp of key issuance from the KME.
    """
    key_id:    str
    key_value: bytes
    sae_id:    str
    issued_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        """Serialize for JSON transport or certificate logging."""
        return {
            "key_id":    self.key_id,
            "key_value": self.key_value.hex(),   # bytes → hex string for JSON safety
            "sae_id":    self.sae_id,
            "issued_at": self.issued_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QuantumKey":
        """Deserialize from JSON response returned by the virtual node."""
        return cls(
            key_id=    data["key_id"],
            key_value= bytes.fromhex(data["key_value"]),
            sae_id=    data["sae_id"],
            issued_at= data["issued_at"],
        )


@dataclass
class KeyRequest:
    """
    Parameters sent to the KME when requesting a key.
    sae_id  : SAE ID of the intended recipient.
    key_size: Key size in bits. Must match message requirements.
    """
    sae_id:   str
    key_size: int = 256   # bits — default per core/config.py KME_KEY_SIZE


@dataclass
class SAERecord:
    """
    Represents a registered SAE (Secure Application Entity) in the virtual KME.
    Used by recipient_check.py to determine if a recipient is a QuMail user.
    sae_id : Unique identifier for the SAE (mapped to an email address).
    email  : Email address this SAE is registered to.
    active : Whether this SAE is currently active.
    """
    sae_id: str
    email:  str
    active: bool = True
