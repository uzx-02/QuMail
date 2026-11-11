from dataclasses import dataclass, field
from enum import Enum
import re
import uuid


class Code(str, Enum):
    INVALID = "invalid_input"
    IDENTITY = "identity_binding_failed"
    GOOGLE_BROWSER = "google_browser_start_failed"
    GOOGLE_CALLBACK = "google_callback_failed_or_expired"
    GOOGLE_TOKEN = "google_token_exchange_failed"
    GOOGLE_CLAIMS = "google_verified_identity_failed"
    GOOGLE_CLOCK = "google_token_time_invalid"
    GOOGLE_KEYS = "google_verification_keys_unavailable"
    GOOGLE_SIGNATURE = "google_token_signature_or_format_invalid"
    GOOGLE_AUDIENCE = "google_token_audience_mismatch"
    GOOGLE_NONCE = "google_token_nonce_mismatch"
    GOOGLE_AUTHORITY = "google_token_authority_or_claims_invalid"
    GOOGLE_ADDRESS = "google_expected_address_mismatch"
    GOOGLE_SCOPES = "google_required_consent_missing"
    TRUST = "unverified_or_changed_recipient"
    OWNERSHIP = "account_or_device_mismatch"
    STORE = "secure_store_unavailable"
    CORRUPT = "authenticated_record_invalid"
    CONFLICT = "transaction_conflict"
    LIFECYCLE = "key_not_active"
    PROVIDER = "provider_failure"
    LIMIT = "resource_limit"


class BoundaryError(Exception):
    def __init__(self, code: Code):
        self.code = code
        super().__init__(code.value)  # Never include provider payloads or secrets.


@dataclass(frozen=True)
class OpaqueId:
    value: str

    def __post_init__(self):
        if not isinstance(self.value, str) or not re.fullmatch(r"[0-9a-f]{32}", self.value):
            raise BoundaryError(Code.INVALID)

    @classmethod
    def new(cls):
        return cls(uuid.uuid4().hex)


class UserId(OpaqueId): pass
class AccountId(OpaqueId): pass
class DeviceId(OpaqueId): pass
class KeyHandle(OpaqueId): pass
class SaeId(OpaqueId): pass


@dataclass(frozen=True)
class EmailAddress:
    value: str

    def __post_init__(self):
        if not isinstance(self.value, str) or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+", self.value) or len(self.value)>254:
            raise BoundaryError(Code.INVALID)
        local, domain = self.value.rsplit('@', 1)
        object.__setattr__(self, 'value', local+'@'+domain.lower())


@dataclass(frozen=True)
class RootIdentity:
    fingerprint: str

    def __post_init__(self):
        if not re.fullmatch(r"[A-F0-9]{64}", self.fingerprint):
            raise BoundaryError(Code.INVALID)


class Trust(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "independently_verified"
    CHANGED = "changed_blocked"
    REVOKED = "revoked"


@dataclass(frozen=True, repr=False)
class AccountContext:
    account: AccountId
    device: DeviceId
    issuer: str
    subject: str = field(repr=False)


@dataclass(frozen=True, repr=False)
class VerifiedProviderIdentity:
    issuer: str
    subject: str
    addresses: tuple[EmailAddress, ...]
    expires: int
    evidence: str  # Only produced at an authenticated provider adapter boundary.


@dataclass(frozen=True)
class RecipientTrust:
    address: EmailAddress
    root: RootIdentity
    state: Trust
    method: str
    verified_at: int
