"""Stable development Settings service; intentionally exposes no send operation."""
import os
from pathlib import Path
from core.account_session import AccountView,DevelopmentSession
from experiments.m3.types import BoundaryError,Code,EmailAddress,RootIdentity,UserId
from experiments.m3.vault import Vault,safe_path,LIMIT
from experiments.m3.provider import Provider
from experiments.m3.secure_store import WindowsCredentialStore
from transport.development_google import client_configuration
from transport.bounded_google import BoundedGoogleAuthorization as GoogleAuthorization


def persist_new(path,data):
    path=safe_path(path)
    # Never overwrite an existing backup/public export, including a symlink.
    try:
        with path.open('xb') as file:
            file.write(data); file.flush(); os.fsync(file.fileno())
    except OSError: raise BoundaryError(Code.CONFLICT) from None


class IdentityService:
    def __init__(self,path,provider,store,google=None):
        self.path=Path(path)
        self.provider=provider
        self.store=store
        self.google=google
        self.vault=None
        self.session=DevelopmentSession()

    @classmethod
    def configured(cls,path,helper,client=None):
        return cls(path,Provider(Path(helper)),WindowsCredentialStore(),
                   GoogleAuthorization(client_configuration(client)) if client else None)

    def unlock(self,create=False):
        self.session.invalidate()
        self.vault=None
        try:
            vault=Vault.create(self.path,self.store,self.provider) if create else Vault(self.path,self.store,self.provider)
            accounts=tuple(AccountView(*row) for row in vault.summaries())
            self.vault=vault
            self.session.install(accounts,accounts[0] if accounts else None)
        except Exception:
            self.session.install(locked=True)
            raise BoundaryError(Code.STORE) from None

    def lock(self):
        self.session.install(locked=True)
        self.vault=None

    def require(self):
        if self.session.snapshot.locked or self.vault is None: raise BoundaryError(Code.STORE)
        return self.vault

    def active(self):
        self.require()
        selected=self.session.snapshot.active
        if selected is None: raise BoundaryError(Code.OWNERSHIP)
        return selected

    def reload(self,context=None):
        rows=tuple(AccountView(*row) for row in self.require().summaries())
        context=context or (self.session.snapshot.active.context if self.session.snapshot.active else None)
        selected=next((row for row in rows if row.context==context),None)
        self.session.install(rows,selected)

    def select(self,account):
        self.session.invalidate()
        rows=tuple(AccountView(*row) for row in self.require().summaries())
        selected=next((row for row in rows if row.context.account==account),None)
        if selected is None: raise BoundaryError(Code.OWNERSHIP)
        self.session.install(rows,selected)

    def authorization(self,address,refresh=False,reauthorize=False):
        self.require()
        if not self.google: raise BoundaryError(Code.IDENTITY)
        ticket=self.session.begin()
        if refresh:
            view=self.active(); tokens=self.vault.oauth(view.context)
            work=lambda:self.google.refresh(ticket.cancelled,view.context,view.address,tokens)
        else:
            EmailAddress(address)
            subject=self.active().context.subject if reauthorize else None
            work=lambda:self.google.authorize(ticket.cancelled,address,subject)
        return ticket,work

    def accept_authorization(self,ticket,result,mode='enroll',recovery=None):
        def commit():
            vault=self.require()
            if mode in ('refresh','reauthorize'):
                if ticket.active is None: raise BoundaryError(Code.OWNERSHIP)
                vault.store_oauth(ticket.active.context,result.identity,result.tokens)
                self.reload(ticket.active.context)
            elif mode=='restore':
                if recovery is None: raise BoundaryError(Code.INVALID)
                ctx=vault.restore(*recovery,result.identity,explicit=True,tokens=result.tokens)
                self.reload(ctx)
            elif mode=='enroll':
                ctx,_=vault.enroll(result.identity,result.identity.addresses[0],UserId.new(),tokens=result.tokens)
                self.reload(ctx)
            else: raise BoundaryError(Code.INVALID)
        return self.session.complete(ticket,commit)

    def contacts(self):
        view=self.active()
        return self.vault.contact_summaries(view.context)

    def import_certificate(self,address,public):
        view=self.active()
        return self.vault.import_contact(view.context,EmailAddress(address),public)

    def verify_fingerprint(self,address,fingerprint,method):
        view=self.active()
        self.vault.pin_contact(view.context,EmailAddress(address),RootIdentity(fingerprint),method)

    def export_public(self,path):
        view=self.active()
        persist_new(path,self.vault.export_public(view.context,view.key))

    def backup(self,path,transfer=False,confirmed=False):
        view=self.active()
        if transfer:
            secret=self.vault.transfer(view.context,lambda data:persist_new(path,data),explicit=confirmed)
        else:
            data,secret=self.vault.export_recovery(view.context,explicit=True)
            persist_new(path,data)
        # Export has already committed. A subsequent display refresh failure must
        # not hide its recovery secret or misreport a completed transfer as failed.
        try: self.reload(view.context)
        except BoundaryError: self.lock()
        return secret

    def activate(self,replace_root=False,prior_device_retired=False):
        view=self.active()
        if replace_root: self.vault.replace_root(view.context)
        else: self.vault.activate_restored_root(view.context,prior_device_retired)
        self.reload(view.context)

    def rotate(self):
        view=self.active(); self.vault.rotate(view.context,view.key); self.reload(view.context)

    def revoke(self):
        view=self.active(); self.vault.revoke(view.context,view.key); self.reload(view.context)
