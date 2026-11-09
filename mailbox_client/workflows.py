"""Mailbox application boundary over M3 ownership, M5 MIME and M4 durability."""
import os
from pathlib import Path
import re
from experiments.m3.types import EmailAddress
from experiments.m3.vault import safe_path
from experiments.m4.codec import pack, unpack
from experiments.m4.model import OperationId, State, Failure, Error
from experiments.m4.services import SubmitOutbox, result
from experiments.m4.smtp_transport import MailCredential
from experiments.m5 import mime
from experiments.m5.model import Attachment, Draft, Budget, MAX_ATTACHMENT_BYTES
from experiments.m5.services import Compose, OpenMessage, encode_draft, decode_draft
from .model import Display
from .service import Credentials
from .smtp import GmailSMTP


def export_path(value):
    path = Path(value)
    if (not path.is_absolute() or str(path).startswith(('\\\\', '//')) or
        any(part in ('.', '..') or part.endswith(('.', ' ')) or
            re.search(r'[<>:"|?*\x00-\x1f]', part) or
            re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part)
            for part in path.parts[1:])):
        raise Failure(Error.INVALID)
    return safe_path(path)


def import_attachment(value):
    path = export_path(value)
    with path.open('rb') as stream: data = stream.read(MAX_ATTACHMENT_BYTES+1)
    media = {'.txt':'text/plain', '.png':'image/png', '.pdf':'application/pdf'}.get(path.suffix.lower(), 'application/octet-stream')
    attachment = Attachment(path.name, media, data)
    mime.validate(Draft(('check@example.invalid',), (), '', '', (attachment,)))
    return attachment


class CombinedCancel:
    def __init__(self, *events): self.events = events
    def is_set(self): return any(event.is_set() for event in self.events)


class ScopedCredential:
    def __init__(self, credentials, lease, budget):
        self.credentials, self.lease, self.budget = credentials, lease, budget

    def resolve(self, handle, sender, cancel, deadline):
        if handle.context != self.lease.context: raise Failure(Error.ACCOUNT)
        value = self.credentials.resolve(self.lease, Budget(cancel, deadline))
        if value.address != sender.value: raise Failure(Error.CREDENTIAL)
        return MailCredential(value.address, value.token)


class OperationTransport:
    """Preserve durable completion while cancellation also stops socket work."""
    simulation_only = False
    def __init__(self, transport, budget):
        self.transport, self.budget = transport, budget
    def submit(self, envelope, credential, cancel, deadline):
        return self.transport.submit(envelope, credential,
            CombinedCancel(cancel, self.budget.cancel), min(deadline, self.budget.deadline))


class Workflows:
    def __init__(self, vault, access, provider, google=None, *, gmail_enabled=False, transport_factory=None, discovery=None, trust_engine=None):
        self.vault, self.access = vault, access
        self.compose = Compose(vault, access, provider)
        self.repository = self.compose.repository
        self.opener = OpenMessage(vault, access, provider)
        self.credentials = Credentials(vault, access, google)
        # Factory is a controlled protocol-test seam, never fixture state in UI.
        self.transport_factory = transport_factory or (GmailSMTP if gmail_enabled else None)
        self.offline = SubmitOutbox(self.repository, None)
        from core.key_discovery import CachedKeyDiscoveryService
        from core.trust_engine import TrustPolicyEngine
        self.discovery = discovery or CachedKeyDiscoveryService()
        self.trust_engine = trust_engine or TrustPolicyEngine(self.discovery)

    def check(self, lease, budget):
        self.access.check(lease, budget.deadline); budget.check()

    def save(self, lease, draft, budget, operation=None):
        self.check(lease, budget)
        if operation is None: return self.compose.draft(lease, draft, budget)
        with self.repository.transaction(lease, budget.deadline) as account:
            row = account.row(operation)
            if row['state'] != State.DRAFT.value: raise Failure(Error.TRANSITION)
            _, date = decode_draft(unpack(row['draft']))
            row['draft'] = pack(encode_draft(draft, date))
            self.check(lease, budget)
        return operation

    def load(self, lease, operation, budget):
        with self.repository.transaction(lease, budget.deadline) as account:
            row = account.row(operation)
            if row['state'] != State.DRAFT.value: raise Failure(Error.TRANSITION)
            draft, _ = decode_draft(unpack(row['draft']))
            self.check(lease, budget)
            return draft

    def recipients(self, lease, draft, budget):
        self.check(lease, budget); mime.validate(draft)
        # Use the cancellable M5 repository adapter; no trust from a UI label.
        with self.repository.transaction(lease, budget.deadline) as account:
            for address in draft.to+draft.cc:
                contact = account._data.get('contacts', {}).get(address)
                if not contact:
                    disc = self.discovery.discover(address)
                    if disc.ok and disc.key:
                        account._vault.import_contact(account.context, EmailAddress(address), disc.key.public_key_bytes)
                        if hasattr(self.discovery, "enterprise") and self.discovery.enterprise.is_certified_by_enterprise(address, disc.key.fingerprint):
                            from experiments.m3.types import RootIdentity
                            account._vault.pin_contact(account.context, EmailAddress(address), RootIdentity(disc.key.fingerprint), "enterprise-directory")
                account._vault.recipient(account._data, EmailAddress(address))
            self.check(lease, budget)
        return 'Every recipient has a currently verified certificate. Preparation rechecks all keys.'

    def prepare(self, lease, operation, key, budget):
        self.check(lease, budget)
        return self.compose.prepare(lease, operation, key, budget)

    def outbox(self, lease, budget):
        self.check(lease, budget)
        self.offline.recover(lease)  # An interrupted intent becomes Unknown, never a resend.
        with self.repository.transaction(lease, budget.deadline) as account:
            rows = tuple(result(OperationId(i), row) for i, row in account.records.items())
            self.check(lease, budget)
            return rows

    def submit(self, lease, operation, budget):
        self.check(lease, budget)
        if self.transport_factory is None: raise Failure(Error.TRANSPORT)
        resolver = ScopedCredential(self.credentials, lease, budget)
        transport = OperationTransport(self.transport_factory(resolver), budget)
        return SubmitOutbox(self.repository, transport, allow_external=True).submit(
            lease, operation, until=budget.deadline)

    def retry(self, lease, operation, budget, acknowledge=False):
        self.check(lease, budget)
        self.offline.retry(lease, operation, acknowledge_duplicate_risk=acknowledge)
        return 'Prepared for one explicit retry; original frozen bytes retained. Submit separately.'

    def cancel_saved(self, lease, operation, budget):
        self.check(lease, budget)
        with self.repository.ownership(lease.context, operation):
            with self.repository.transaction(lease, budget.deadline) as account:
                row = account.row(operation)
                if row['state'] == State.DRAFT.value:
                    del account.records[operation.value]
                elif row['state'] == State.PREPARED.value:
                    row.update(state=State.FAILED.value, reason='cancelled_before_submission')
                else: raise Failure(Error.TRANSITION)
                self.check(lease, budget)
        return 'Draft discarded / prepared submission cancelled. No network action.'

    def archive(self, lease, operation, budget):
        self.check(lease, budget)
        with self.repository.transaction(lease, budget.deadline) as account:
            envelope = account.envelope(operation)
            key = self.vault.key(account._data, lease.context, envelope.binding.key)
            public = bytes(key['public'])
        opened = self.opener.open(lease, envelope.binding.key, envelope.serialized, public, budget)
        if not opened.archive: raise Failure(Error.POLICY)
        self.check(lease, budget)
        return Display(None, opened.subject, opened.body,
            f'Sender archive; signature valid; identity: {opened.identity_trust}; replay: {opened.replay.value}',
            False, opened, owner=lease.context)

    def source(self, lease, display, budget):
        self.check(lease, budget)
        if display is None or (display.key.account if display.key else display.owner) != lease.context:
            raise Failure(Error.ACCOUNT)

    def derive(self, lease, display, budget, *, forward=False, recipients=(), confirmed=False):
        self.source(lease, display, budget)
        opened = display.protected
        if forward:
            if not recipients or not confirmed: raise Failure(Error.POLICY)
            to = tuple(recipients); refs = (); reply = ''
            label = 'Forwarded content; original author did not endorse this forwarding.'
            if opened is None: label += ' Original identity/content unverified.'
            else: label += ' Original identity status: '+opened.identity_trust+'.'
        elif opened:
            if not opened.verified_confidential: raise Failure(Error.POLICY)
            to = (opened.sender,); reply = opened.message_id
            refs = tuple(dict.fromkeys((*opened.references, reply)))[-8:]
            label = 'Quoted authenticated message from '+opened.sender
        else:
            if not confirmed or not recipients: raise Failure(Error.POLICY)
            to = tuple(recipients); refs = (); reply = ''
            label = 'Quoted conventional message — original identity/content unverified.'
        draft = Draft(to, (), ('Fwd: ' if forward else 'Re: ')+display.subject,
            label+'\n\n'+display.body, opened.attachments if opened and forward else (),
            reply, refs)
        mime.validate(draft)  # No silent truncation or size-limit bypass when quoting.
        return draft

    def export(self, lease, display, index, destination, budget):
        self.source(lease, display, budget)
        if display.protected is None or not display.protected.signature_valid:
            raise Failure(Error.POLICY)
        attachments = display.protected.attachments
        if type(index) is not int or not 0 <= index < len(attachments): raise Failure(Error.INVALID)
        path = export_path(destination)  # Message filename is never joined into a path.
        self.check(lease, budget)
        created = False
        try:
            with path.open('xb') as stream:  # Atomic no-clobber, including final symlink.
                created = True
                stream.write(attachments[index].data)
                self.check(lease, budget)
                stream.flush(); os.fsync(stream.fileno())
            self.check(lease, budget)
        except Exception:
            if created: path.unlink(missing_ok=True)
            raise Failure(Error.STORAGE) from None
        return 'Attachment saved to the explicitly selected file. It has not been opened.'
