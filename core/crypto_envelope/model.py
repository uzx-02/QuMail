"""Immutable, private-by-default development message results and qualified budgets."""
from dataclasses import dataclass
from enum import Enum
import threading
import time

PROFILE_V1 = 'QM-OPENPGP-PQ-v1'
PROFILE_LEGACY_M5 = 'QM-OPENPGP-PQ-1-EXPERIMENT-M5'
SUPPORTED_PROFILES = (PROFILE_V1, PROFILE_LEGACY_M5)
PROFILE = PROFILE_V1
MAX_WIRE = 256*1024
MAX_INNER = 64*1024
MAX_HEADERS = 8*1024
MAX_PARTS = 6
MAX_DEPTH = 2
MAX_BODY = 8*1024
MAX_ATTACHMENTS = 4
MAX_ATTACHMENT_BYTES = 16*1024
MAX_RECIPIENTS = 3  # Plus one explicit sender archival key; Bcc unavailable.
MAX_HISTORY = 256


class Code(str, Enum):
    INVALID = 'invalid_message'
    PROFILE = 'unsupported_profile'
    LIMIT = 'resource_limit'
    CANCELLED = 'cancelled_or_stale'
    PROVIDER = 'provider_failed_no_verified_output'
    IDENTITY = 'identity_or_recipient_mismatch'
    STORAGE = 'authenticated_storage_failure'


class Failure(Exception):
    def __init__(self, code): self.code=code; super().__init__(code.value)


@dataclass(frozen=True, repr=False)
class Budget:
    cancel: threading.Event
    deadline: float
    def check(self):
        if self.cancel.is_set() or time.monotonic()>=self.deadline: raise Failure(Code.CANCELLED)


@dataclass(frozen=True, repr=False)
class Attachment:
    name: str
    media_type: str
    data: bytes


@dataclass(frozen=True, repr=False)
class Draft:
    to: tuple[str, ...]
    cc: tuple[str, ...]
    subject: str
    body: str
    attachments: tuple[Attachment, ...] = ()
    in_reply_to: str = ''
    references: tuple[str, ...] = ()
    archive: bool = True
    bcc: tuple[str, ...] = ()


class Replay(str, Enum):
    FRESH='fresh'
    DUPLICATE='duplicate_delivery'
    CONFLICT='protected_identity_conflict'


@dataclass(frozen=True, repr=False)
class OpenedMessage:
    sender: str
    to: tuple[str, ...]
    cc: tuple[str, ...]
    subject: str
    date: str
    message_id: str
    body: str
    attachments: tuple[Attachment, ...]
    in_reply_to: str
    references: tuple[str, ...]
    signer_root: str
    signature_valid: bool
    identity_trust: str
    mismatches: tuple[str, ...]
    replay: Replay
    archive: bool

    @property
    def verified_confidential(self):
        return self.signature_valid and self.identity_trust in ('independently_verified','local_enrolled_identity') and self.replay is not Replay.CONFLICT
