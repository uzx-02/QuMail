"""Qt-free application contracts. Payload-bearing objects never render secrets."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, ContextManager, Any
import threading
import time
from core.vault.types import AccountContext, EmailAddress, KeyHandle, OpaqueId


class OperationId(OpaqueId): pass


class State(str, Enum):
    DRAFT = 'Draft'
    PREPARED = 'Prepared'
    SUBMITTING = 'Submitting'
    ACCEPTED = 'Accepted'
    UNKNOWN = 'Unknown'
    FAILED = 'Failed'


class Error(str, Enum):
    INVALID = 'invalid_request'
    ACCOUNT = 'account_locked_or_changed'
    POLICY = 'profile_or_recipient_rejected'
    CREDENTIAL = 'credential_unavailable_or_expired'
    STORAGE = 'storage_failure'
    PROVIDER = 'envelope_builder_failure'
    TRANSITION = 'invalid_transition'
    DUPLICATE = 'explicit_duplicate_risk_acknowledgment_required'
    CANCELLED = 'cancelled_before_submission'
    LIMIT = 'resource_limit'
    TRANSPORT = 'transport_failure'
    BUSY = 'operation_owned_by_active_worker'


class Failure(Exception):
    def __init__(self, code: Error):
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, repr=False)
class Lease:
    context: AccountContext
    generation: int
    cancelled: threading.Event = field(default_factory=threading.Event)


@dataclass(frozen=True, repr=False)
class CredentialHandle:
    context: AccountContext


@dataclass(frozen=True, repr=False)
class Binding:
    key: KeyHandle
    recipients: tuple[EmailAddress, ...]
    roots: tuple[str, ...]
    profile: str
    recipient_keys: tuple[tuple[str, str], ...]


@dataclass(frozen=True, repr=False)
class PreparedEnvelope:
    operation: OperationId
    account: AccountContext
    message_id: str
    binding: Binding
    serialized: bytes
    digest: str
    sender: EmailAddress


class Outcome(str, Enum):
    ACCEPTED = 'final_server_acceptance'
    REJECTED = 'definitive_rejection'
    UNKNOWN = 'possible_acceptance'


@dataclass(frozen=True)
class DeliveryResult:
    operation: OperationId
    state: State
    reason: str
    attempt: int


class EnvelopeBuilder(Protocol):
    def build(self, account: 'AccountUnit', binding: Binding, plaintext: bytes, message_id: str) -> bytes: ...


class Transport(Protocol):
    simulation_only: bool
    def submit(self, envelope: PreparedEnvelope, credential: CredentialHandle,
               cancel: threading.Event, deadline: float) -> Outcome: ...


class AccountAccess:
    """Explicit, Qt-independent unlock/selection lease; no global provider cache."""
    def __init__(self):
        self._lock = threading.RLock()
        self._generation = 0
        self._lease = None

    def select(self, context: AccountContext | None):
        with self._lock:
            if self._lease: self._lease.cancelled.set()
            self._generation += 1
            self._lease = Lease(context, self._generation) if context else None
            return self._lease

    def check(self, lease: Lease, deadline: float):
        with self._lock:
            if lease is not self._lease or self._lease is None:
                raise Failure(Error.ACCOUNT)
            if lease.cancelled.is_set() or time.monotonic() >= deadline:
                raise Failure(Error.CANCELLED)


class OutboxRepository(Protocol):
    def transaction(self, lease: Lease, deadline: float) -> ContextManager['AccountUnit']: ...
    def ownership(self, context: AccountContext, operation: OperationId) -> ContextManager[None]: ...
    def completion(self, context: AccountContext) -> ContextManager['AccountUnit']: ...


class AccountUnit(Protocol):
    sender: EmailAddress
    records: dict[str, Any]
    def row(self, operation: OperationId) -> dict: ...
    def binding(self, key: KeyHandle, recipients: tuple[EmailAddress, ...], profile: str) -> Binding: ...
    def check_prepared(self, envelope: PreparedEnvelope) -> None: ...
    def credential(self) -> CredentialHandle: ...
    def archive_references(self, binding: Binding) -> dict: ...
    def envelope(self, operation: OperationId) -> PreparedEnvelope: ...


class Reconciler(Protocol):
    simulation_only: bool
    def lookup(self, envelope: PreparedEnvelope, attempt: int) -> Outcome: ...


MAX_DRAFT = 64 * 1024
MAX_ENVELOPE = 1024 * 1024
MAX_OPERATIONS = 256
MAX_ATTEMPTS = 3
