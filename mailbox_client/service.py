"""Account-scoped mailbox operations. Header cache is inside the existing vault."""
from email.parser import BytesParser, BytesHeaderParser
from email.policy import default
import time
from experiments.m5.legacy import classify, Kind
from experiments.m5.services import OpenMessage
from .model import *
from .gmail import MAIL_SCOPE, field


class Credentials:
    def __init__(self, vault, access, google):
        self.vault, self.access, self.google = vault, access, google

    def resolve(self, lease, budget):
        self.access.check(lease, budget.deadline); budget.check()
        data = self.vault._read(lease.context)
        tokens = data.get('oauth')
        if lease.context.issuer != 'https://accounts.google.com' or not tokens or MAIL_SCOPE not in tokens.get('scopes', ()):
            raise Failure(Code.AUTH)
        if tokens.get('expiry', 0) <= time.time()+60:
            if self.google is None or MAIL_SCOPE not in self.google.scopes: raise Failure(Code.AUTH)
            result = self.google.refresh(budget.cancel, lease.context, data['address'], tokens)
            self.access.check(lease, budget.deadline); budget.check()
            # Exact owned context; M3 checks subject/issuer/address. Never install another selection.
            self.vault.store_oauth(lease.context, result.identity, result.tokens)
            tokens = result.tokens
        if MAIL_SCOPE not in tokens.get('scopes', ()) or tokens.get('expiry', 0) <= time.time():
            raise Failure(Code.AUTH)
        self.access.check(lease, budget.deadline); budget.check()
        return Credential(lease.context, data['address'], tokens['access_token'])


def conventional(raw, key, seen):
    if len(raw) > MAX_WIRE or raw.lower().count(b'content-type:') > 64:
        raise Failure(Code.LIMIT)
    try:
        message = BytesParser(policy=default).parsebytes(raw)
        bodies = []; count = 0
        def visit(part, depth):
            nonlocal count
            count += 1
            if depth > 8 or count > 64: raise Failure(Code.LIMIT)
            if part.defects: raise Failure(Code.PROTOCOL)
            if part.get_content_disposition() == 'attachment': return
            if part.get_content_maintype() == 'message': return
            if part.is_multipart():
                for child in part.iter_parts(): visit(child, depth+1)
            elif part.get_content_type() == 'text/plain':
                data = part.get_payload(decode=True) or b''
                bodies.append(data.decode(part.get_content_charset() or 'utf-8', errors='replace'))
        visit(message, 1)
        body = '\n\n'.join(bodies)
        if len(body.encode('utf-8')) > MAX_WIRE: raise Failure(Code.LIMIT)
        return Display(key, field(message, 'Subject'), body or '[No plain-text body. HTML and attachments are not rendered.]',
                       'Conventional mail: author and content are not cryptographically verified.', seen)
    except Failure: raise
    except Exception: raise Failure(Code.PROTOCOL) from None


class MailboxService:
    def __init__(self, vault, access, google, mailbox, provider, resolver=None):
        self.vault, self.access, self.mailbox = vault, access, mailbox
        self.resolver = resolver or Credentials(vault, access, google)
        self.opener = OpenMessage(vault, access, provider)

    def check(self, lease, budget, key=None):
        self.access.check(lease, budget.deadline); budget.check()
        if key is not None and key.account != lease.context: raise Failure(Code.STALE)

    def headers(self, lease, budget, before=None):
        self.check(lease, budget)
        page = self.mailbox.headers(self.resolver.resolve(lease, budget), budget, before)
        self.check(lease, budget)
        if len(page.headers) > PAGE_SIZE: raise Failure(Code.LIMIT)
        with self.vault.transaction(lease.context) as data:
            self.check(lease, budget)
            if any(row.key.account != lease.context or row.key.uidvalidity != page.uidvalidity for row in page.headers):
                raise Failure(Code.STALE)
            # Replace the bounded page; UIDVALIDITY rollover never reuses old UID rows.
            data['m6_mailbox_v1'] = dict(mailbox='INBOX', uidvalidity=page.uidvalidity,
                rows=[dict(uid=r.key.uid, sender=r.sender, subject=r.subject, date=r.date, size=r.size, seen=r.seen)
                      for r in page.headers])
            self.check(lease, budget)
        self.check(lease, budget)
        return page

    def open(self, lease, key, key_handle, signer_address, budget):
        self.check(lease, budget, key)
        raw, seen = self.mailbox.fetch(self.resolver.resolve(lease, budget), key, budget)
        self.check(lease, budget, key)
        head = raw.replace(b'\r\n', b'\n').partition(b'\n\n')[0]
        if len(head) > MAX_HEADER: raise Failure(Code.LIMIT)
        headers = BytesHeaderParser(policy=default).parsebytes(head+b'\n\n')
        if not headers.get_all('Content-Type') and b'-----BEGIN PGP MESSAGE-----' not in raw:
            kind = Kind.CONVENTIONAL  # RFC default text/plain; not an encrypted-error fallback.
        else:
            kind = classify(raw).kind
        if kind is Kind.MODERN:
            data = self.vault._read(lease.context)
            # Explicit local certificate selection, not trust in an outer From header.
            if signer_address == data['address']:
                public = bytes(self.vault.key(data, lease.context, key_handle)['public'])
            else:
                contact = data['contacts'].get(signer_address)
                if contact is None: raise Failure(Code.SIGNER)
                public = bytes(contact['public'])
            opened = self.opener.open(lease, key_handle, raw, public, budget)
            result = Display(key, opened.subject, opened.body,
                f'Signature valid; identity: {opened.identity_trust}; replay: {opened.replay.value}; '
                f'outer mismatches: {", ".join(opened.mismatches) or "none"}; archive: {opened.archive}', seen)
        elif kind is Kind.LEGACY:
            result = Display(key, 'Legacy encrypted message', '[Original bytes retained on server; use the isolated legacy reader.]',
                             'Legacy: unverified compatibility; no modern verification claim.', seen)
        else:
            result = conventional(raw, key, seen)
        self.check(lease, budget, key)
        return result

    def set_seen(self, lease, key, seen, budget):
        self.check(lease, budget, key)
        actual = self.mailbox.set_seen(self.resolver.resolve(lease, budget), key, seen, budget)
        self.check(lease, budget, key)
        with self.vault.transaction(lease.context) as data:
            cache = data.get('m6_mailbox_v1', {})
            if cache.get('uidvalidity') == key.uidvalidity:
                for row in cache.get('rows', []):
                    if row['uid'] == key.uid: row['seen'] = actual
            self.check(lease, budget, key)
        return actual
