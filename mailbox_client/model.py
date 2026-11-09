from dataclasses import dataclass
from enum import Enum
from experiments.m3.types import AccountContext

MAX_WIRE = 256 * 1024  # Preserve the M5 qualified message ceiling.
MAX_HEADER = 8192
PAGE_SIZE = 30


class Code(str, Enum):
    AUTH = 'authorize_selected_google_account_with_mail_scope'
    CANCELLED = 'cancelled_or_account_changed'
    TRANSPORT = 'mailbox_connection_failed'
    PROTOCOL = 'invalid_mailbox_response'
    LIMIT = 'mailbox_resource_limit'
    STALE = 'mailbox_identity_changed_refresh_required'
    MISSING = 'message_no_longer_available'
    SIGNER = 'select_imported_signer_certificate_in_settings'


class Failure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, repr=False)
class Credential:
    context: AccountContext
    address: str
    token: str


@dataclass(frozen=True, repr=False)
class MessageKey:
    account: AccountContext
    mailbox: str
    uidvalidity: int
    uid: int

    def __post_init__(self):
        if self.mailbox != 'INBOX' or not all(type(v) is int and 0 < v < 2**32 for v in (self.uidvalidity, self.uid)):
            raise Failure(Code.PROTOCOL)


@dataclass(frozen=True, repr=False)
class Header:
    key: MessageKey
    sender: str
    subject: str
    date: str
    size: int
    seen: bool


@dataclass(frozen=True, repr=False)
class Page:
    uidvalidity: int
    headers: tuple[Header, ...]
    before: int | None


@dataclass(frozen=True, repr=False)
class Display:
    key: MessageKey | None
    subject: str
    body: str
    security: str
    seen: bool
    protected: object | None = None  # Immutable M5 OpenedMessage, only after verification.
    author_claim: str = ''
    owner: AccountContext | None = None
    indicator: object | None = None

    @property
    def thread(self):
        message = self.protected
        if message is None or not message.verified_confidential: return ''
        return (message.references or (message.in_reply_to or message.message_id,))[0]
