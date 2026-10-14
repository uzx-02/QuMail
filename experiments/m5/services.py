"""Development application boundary over unchanged M3 vault and M4 durable services."""
import base64
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from email.utils import format_datetime
import hashlib
import json
import time
from experiments.m3.types import EmailAddress, BoundaryError
from experiments.m3.vault import Vault, PROFILE as CRYPTO_PROFILE
from experiments.m4.services import PrepareMessage, SubmitOutbox
from experiments.m4.vault_adapter import VaultOutbox, AccountTransaction
from experiments.m4.model import Failure as OutboxFailure
from .model import *
from . import mime
from .provider import Provider


class ScopedIdentity:
    """Unchanged M3 helper/schema, called through the cancellable pipe boundary."""
    def __init__(self,original,budget): self.client=Provider(original.executable); self.budget=budget
    def call(self,op,**values):
        if op!='inspect': raise Failure(Code.PROFILE)
        return self.client.call(op,self.budget,**values)


def encode_draft(draft,date):
    mime.validate(draft)
    return json.dumps(dict(to=draft.to,cc=draft.cc,subject=draft.subject,body=draft.body,
        attachments=[dict(name=a.name,media_type=a.media_type,data=base64.b64encode(a.data).decode()) for a in draft.attachments],
        in_reply_to=draft.in_reply_to,references=draft.references,archive=draft.archive,date=date),separators=(',',':')).encode()


def decode_draft(raw):
    try:
        data=json.loads(raw)
        draft=Draft(tuple(data['to']),tuple(data['cc']),data['subject'],data['body'],
            tuple(Attachment(a['name'],a['media_type'],base64.b64decode(a['data'],validate=True)) for a in data['attachments']),
            data['in_reply_to'],tuple(data['references']),data['archive'])
        mime.validate(draft)
        return draft,data['date']
    except Failure: raise
    except Exception: raise Failure(Code.INVALID) from None


class MessageAccount(AccountTransaction):
    def binding(self,key,recipients,profile):
        if profile!=PROFILE or not 1<=len(recipients)<=MAX_RECIPIENTS: raise Failure(Code.PROFILE)
        return replace(super().binding(key,recipients,CRYPTO_PROFILE),profile=PROFILE)


class Repository(VaultOutbox):
    @contextmanager
    def transaction(self,lease,deadline):
        scoped=Vault(self.vault.path,self.vault.store,ScopedIdentity(self.vault.provider,Budget(lease.cancelled,deadline)))
        with VaultOutbox(scoped,self.access).transaction(lease,deadline) as account:
            yield MessageAccount(account._vault,account.context,account._data)


class MessageBuilder:
    def __init__(self,provider,budget): self.provider,self.budget=provider,budget
    def build(self,account,binding,plaintext,message_id):
        self.budget.check()
        draft,date=decode_draft(plaintext)
        if tuple(EmailAddress(v) for v in draft.to+draft.cc)!=binding.recipients: raise Failure(Code.IDENTITY)
        inner=mime.build_inner(account.sender.value,draft,message_id,date)
        v=account._vault; ctx=account.context; data=account._data
        key=v.key(data,ctx,binding.key,active=True)
        recipients=[v.recipient(data,a) for a in binding.recipients]
        if draft.archive and account.sender.value not in draft.to+draft.cc:
            recipients.append(bytes(key['public']))
        # Every encryption input is public, including the explicit archival recipient.
        armor=self.provider.call('seal',self.budget,certificate=bytes(key['secret']),
            recipients=recipients,data=inner)['data']
        self.budget.check()
        return mime.build_outer(account.sender.value,draft,message_id,date,armor)


class Compose:
    def __init__(self,vault,access,provider):
        self.vault,self.access,self.provider=vault,access,provider
        self.repository=Repository(vault,access)

    def draft(self,lease,draft,budget):
        budget.check(); self.access.check(lease,budget.deadline)
        raw=encode_draft(draft,format_datetime(datetime.now(timezone.utc)))
        return PrepareMessage(self.repository,MessageBuilder(self.provider,budget)).draft(lease,raw,until=budget.deadline)

    def prepare(self,lease,operation,key,budget):
        budget.check()
        with self.repository.transaction(lease,budget.deadline) as account:
            from experiments.m4.codec import unpack
            draft,_=decode_draft(unpack(account.row(operation)['draft']))
        recipients=tuple(EmailAddress(v) for v in draft.to+draft.cc)
        return PrepareMessage(self.repository,MessageBuilder(self.provider,budget)).prepare(
            lease,operation,key,recipients,PROFILE,until=budget.deadline)


class OpenMessage:
    def __init__(self,vault,access,provider): self.vault,self.access,self.provider=vault,access,provider

    def open(self,lease,key_handle,wire,signer_public,budget):
        budget.check(); self.access.check(lease,budget.deadline)
        outer,armor=mime.parse_outer(wire)
        data=self.vault._read(lease.context)
        key=self.vault.key(data,lease.context,key_handle)
        # Candidate certificate is explicit public input, never trusted from outer From.
        try: signer=ScopedIdentity(self.vault.provider,budget).call('inspect',certificate=signer_public)
        except BoundaryError: raise Failure(Code.IDENTITY) from None
        budget.check()
        result=self.provider.call('open',budget,certificate=bytes(key['secret']),sender=signer_public,data=armor)
        if result.get('verified') is not True or result.get('signer')!=signer['fingerprint']: raise Failure(Code.PROVIDER)
        raw=result['data']; sender,draft,ident,date,snapshots=mime.parse_inner(raw)
        if sender not in signer['addresses']: raise Failure(Code.IDENTITY)
        local=data['address']; archive=local==sender and draft.archive
        if local not in draft.to+draft.cc and not archive: raise Failure(Code.IDENTITY)
        budget.check(); self.access.check(lease,budget.deadline)
        # Authenticated persistent replay state commits before returning any content.
        replay_key=signer['fingerprint']+'/'+ident
        digest=hashlib.sha256(raw).hexdigest()
        try:
            with self.vault.transaction(lease.context) as current:
                self.access.check(lease,budget.deadline); budget.check()
                history=current.setdefault('m5_seen_v1',{})
                prior=history.get(replay_key)
                state=Replay.FRESH if prior is None else Replay.DUPLICATE if prior['digest']==digest else Replay.CONFLICT
                if prior is None:
                    if len(history)>=MAX_HISTORY: raise Failure(Code.LIMIT)
                    history[replay_key]=dict(digest=digest,first_seen=int(time.time()))
                contact=current['contacts'].get(sender)
                trust='unverified'
                if sender==local and signer['fingerprint']==current['root']:
                    trust='local_enrolled_identity'
                elif contact:
                    trust=contact['state']
                    if contact['fingerprint']!=signer['fingerprint']: trust='changed_blocked'
                    elif contact['signing']!=signer['signing']: trust='changed_blocked'
        except BoundaryError: raise Failure(Code.STORAGE) from None
        self.access.check(lease,budget.deadline); budget.check()
        return OpenedMessage(sender,draft.to,draft.cc,draft.subject,date,ident,draft.body,draft.attachments,
            draft.in_reply_to,draft.references,signer['fingerprint'],True,trust,
            mime.mismatches(outer,snapshots),state,archive)
