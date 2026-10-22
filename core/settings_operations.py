"""Bounded Settings work: immutable requests, worker-owned DBs, GUI publication.

No Qt widgets or mutable IdentityService enter the worker. Commit authorization is
a short synchronized reservation; disk I/O never holds the GUI's session mutex.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass,field,replace
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import secrets
import threading
import time
import uuid

from core.account_session import AccountView,Ticket
from core.identity_service import persist_new
from experiments.m3.types import BoundaryError,Code,EmailAddress,RootIdentity,UserId,AccountId
from experiments.m3.vault import Vault,LIMIT,BACKUP,protect,encode,safe_path


class Stopped(Exception): pass


def current(session,request):
    with session._mutex:
        if request.operation in ('read','outcomes'):
            snap=session.snapshot; ticket=request.ticket
            return (not snap.locked and not ticket.cancelled.is_set() and
                    snap.generation==ticket.generation and snap.active==ticket.active)
        return session.current(request.ticket)


@dataclass(frozen=True,repr=False)
class Request:
    operation: str
    path: Path
    ident: str|None
    ticket: object
    owner: object
    args: tuple=()
    ident_op: str=field(default_factory=lambda:uuid.uuid4().hex)
    deadline: float=field(default_factory=lambda:time.monotonic()+120)


@dataclass(repr=False)
class Result:
    request: Request
    state: str
    accounts: tuple=()
    contacts: tuple=()
    selected: object=None
    vault: object=None
    recovery: object=None
    outcomes: tuple=()
    error: object=None


@dataclass(repr=False)
class Recovery:
    package: bytes
    secret: bytes
    destination: str
    transfer: bool
    revision: int


class Guard:
    def __init__(self,session,request):
        self.session,self.request=session,request
        self.reserved=False; self.committed=False

    def check(self):
        with self.session._mutex:
            if not current(self.session,self.request) or time.monotonic()>=self.request.deadline:
                raise Stopped()

    def reserve(self):
        with self.session._mutex:
            self.check()
            self.reserved=True
        # Cancellation after this point cannot promise rollback of this effect.


class CheckedProvider:
    def __init__(self,provider,guard): self.provider,self.guard=provider,guard
    def call(self,*args,**kwargs):
        self.guard.check()
        result=self.provider.call(*args,**kwargs)
        self.guard.check()
        return result


class ScopedVault(Vault):
    """Only this worker owns this object. Every connection is opened/closed here."""
    def __init__(self,request,store,provider,guard):
        self.guard=guard; self.request=request; self.receipt='committed'
        self.subject=None
        super().__init__(request.path,store,CheckedProvider(provider,guard))
        if request.ident is not None and self.ident!=request.ident: raise BoundaryError(Code.OWNERSHIP)

    @contextmanager
    def connection(self):
        self.guard.check()
        with super().connection() as db: yield db

    def commit(self,db):
        # Receipt is encrypted with the account and committed atomically with it.
        req=self.request; master=self.store.get(self.ident)
        owner=req.owner.context.account if req.owner and req.operation not in ('enroll','restore') else None
        for (ident,) in db.execute('SELECT id FROM accounts').fetchall():
            account=AccountId(ident)
            if owner is not None and account!=owner: continue
            revision,data=self.load(db,account,master)
            if owner is None and data['subject']!=self.subject: continue
            receipts=[r for r in data.get('settings_outcomes',[]) if r['id']!=req.ident_op]
            receipts.append(dict(id=req.ident_op,operation=req.operation,state=self.receipt))
            data['settings_outcomes']=receipts[-16:]
            db.execute('UPDATE accounts SET blob=? WHERE id=?',
                (protect(master,encode(data),self.aad(ident,revision)),ident))
        self.guard.reserve()
        super().commit(db)
        self.guard.committed=True


def read_bounded(path):
    with safe_path(path).open('rb') as file: data=file.read(LIMIT+129)
    if len(data)>LIMIT+128: raise BoundaryError(Code.LIMIT)
    return data


def execute(request,session,store,provider,google):
    guard=Guard(session,request); req=request; op=req.operation
    try:
        guard.check()
        if op=='create':
            guard.reserve()
            v=Vault.create(req.path,store,CheckedProvider(provider,guard))
            guard.committed=True
        else: v=ScopedVault(req,store,provider,guard)
        ctx=req.owner.context if req.owner else None
        key=req.owner.key if req.owner else None
        args=req.args
        recovery=None; outcomes=()
        if op in ('enroll','restore','refresh','reauthorize'):
            if google is None: raise BoundaryError(Code.IDENTITY)
            if op=='refresh': result=google.refresh(req.ticket.cancelled,ctx,req.owner.address,v.oauth(ctx))
            else: result=google.authorize(req.ticket.cancelled,args[0],ctx.subject if op=='reauthorize' else None)
            guard.check(); v.subject=result.identity.subject
            if op in ('refresh','reauthorize'): v.store_oauth(ctx,result.identity,result.tokens)
            elif op=='enroll': ctx,_=v.enroll(result.identity,result.identity.addresses[0],UserId.new(),tokens=result.tokens)
            else: ctx=v.restore(read_bounded(args[1]),args[2],result.identity,explicit=True,tokens=result.tokens)
            del result
        elif op=='import': v.import_contact(ctx,EmailAddress(args[0]),read_bounded(args[1]))
        elif op=='verify': v.pin_contact(ctx,EmailAddress(args[0]),RootIdentity(args[1]),args[2])
        elif op=='rotate': v.rotate(ctx,key)
        elif op=='revoke': v.revoke(ctx,key)
        elif op=='replace': v.replace_root(ctx)
        elif op=='activate': v.activate_restored_root(ctx,True)
        elif op=='export':
            public=v.export_public(ctx,key)
            with v.transaction(ctx) as data:
                exports=data.setdefault('settings_exports',{})
                exports[req.ident_op]=dict(path=args[0],sha256=hashlib.sha256(public).hexdigest(),state='write_intent',transfer=False)
                if len(exports)>16: raise BoundaryError(Code.LIMIT)
                v.receipt='write_intent'
            guard.reserve(); persist_new(args[0],public)
            with v.transaction(ctx) as data:
                data['settings_exports'][req.ident_op]['state']='written'
                v.receipt='public_written'
        elif op=='prepare_backup':
            master=v.store.get(v.ident)
            with v.connection() as db: revision,data=v.load(db,ctx.account,master)
            v.check(data,ctx,active=args[1])
            secret=secrets.token_bytes(32)
            # No durable effect or file before explicit GUI custody acknowledgment.
            snapshot={k:value for k,value in data.items() if k not in ('oauth','settings_outcomes','settings_exports')}
            recovery=Recovery(BACKUP+protect(secret,encode(snapshot),BACKUP),secret,args[0],args[1],revision)
        elif op=='write_backup':
            package,destination,transfer,revision=args
            digest=hashlib.sha256(package).hexdigest()
            # Record owner-scoped intent before external file side effect. No secret.
            with v.transaction(ctx,active=transfer) as data:
                with v.connection() as db: actual=db.execute('SELECT revision FROM accounts WHERE id=?',(ctx.account.value,)).fetchone()[0]
                if actual!=revision: raise BoundaryError(Code.CONFLICT)
                data.setdefault('settings_exports',{})[req.ident_op]=dict(path=destination,sha256=digest,state='write_intent',transfer=transfer)
                if len(data['settings_exports'])>16: raise BoundaryError(Code.LIMIT)
                v.receipt='write_intent'
            guard.reserve(); persist_new(destination,package)
            # Failed/cancelled persistence cannot suspend the source. Cancellation
            # before this final commit leaves an inspectable intent and active source.
            with v.transaction(ctx,active=transfer) as data:
                data['settings_exports'][req.ident_op]['state']='written'
                if transfer:
                    data['state']='suspended_for_transfer'
                    data['events'].append('explicit_device_transfer_persisted')
                else: data['events'].append('explicit_recovery_backup')
                v.receipt='transfer_written' if transfer else 'backup_written'
        elif op=='outcomes':
            data=v._read(ctx)
            rows=list(data.get('settings_outcomes',[]))
            for ident,record in data.get('settings_exports',{}).items():
                guard.check()
                try: matched=hashlib.sha256(read_bounded(record['path'])).hexdigest()==record['sha256']
                except (OSError,BoundaryError): matched=False
                rows.append(dict(id=ident,operation='export',state=record['state'],
                    package_matches=matched,source_lifecycle=data['state']))
            outcomes=tuple(rows)
        elif op not in ('read','unlock','create'): raise BoundaryError(Code.INVALID)
        guard.check()
        accounts=tuple(AccountView(*row) for row in v.summaries())
        selected=next((row for row in accounts if row.context==ctx),None) if ctx else (accounts[0] if accounts else None)
        contacts=tuple(v.contact_summaries(selected.context)) if selected else ()
        guard.check()
        # Publication receives an ordinary vault with no request/provider guard.
        plain=Vault(req.path,store,provider)
        return Result(req,'committed' if guard.committed else 'ready',accounts,contacts,selected,plain,recovery,outcomes)
    except BaseException as error:
        # Never forward traceback/provider text/private values. Receipt survives
        # stale GUI results; COMMIT failure/reservation must not claim rollback.
        state='inspect_outcome' if guard.reserved or guard.committed else ('cancelled' if isinstance(error,Stopped) else 'failed')
        code=error.code if isinstance(error,BoundaryError) else Code.STORE
        return Result(req,state,error=code)


class Operations:
    def __init__(self,service):
        self.service=service  # Used by GUI dispatch/publication only.
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='qumail-settings')
        self.future=None; self.request=None; self.closed=False

    @property
    def busy(self): return self.future is not None

    def start(self,operation,*args):
        if self.closed or self.busy: raise BoundaryError(Code.LIMIT)
        service=self.service; snap=service.session.snapshot
        if operation not in ('unlock','create') and snap.locked: raise BoundaryError(Code.STORE)
        ticket=Ticket(snap.generation,snap.active) if operation in ('read','outcomes') else service.session.begin()
        request=Request(operation,service.path.absolute(),service.vault.ident if service.vault else None,
                        ticket,snap.active,tuple(args),deadline=time.monotonic()+(240 if operation in ('enroll','restore','refresh','reauthorize') else 120))
        self.request=request
        self.future=self.pool.submit(execute,request,service.session,service.store,service.provider,service.google)
        return request

    def take(self):
        if self.future is None or not self.future.done(): return None
        future=self.future; self.future=None; self.request=None
        return future.result()

    def cancel(self):
        with self.service.session._mutex:
            if self.request: self.request.ticket.cancelled.set()
            self.service.session.invalidate()

    def close(self):
        self.closed=True; self.cancel()
        future=self.future; self.future=None; self.request=None
        # Drop retained results after completion even when the GUI no longer polls.
        def discard(f):
            if f.cancelled(): return
            result=f.result()
            result.recovery=None; result.vault=None; result.accounts=(); result.contacts=()
            result.request=replace(result.request,args=())
        if future: future.add_done_callback(discard)
        self.pool.shutdown(wait=False,cancel_futures=True)
