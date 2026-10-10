"""Transactional isolated development vault; production mail never calls this module."""
import base64
from contextlib import contextmanager
import json
from pathlib import Path
import secrets
import sqlite3
import stat
import time
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from .types import (AccountContext, AccountId, BoundaryError, Code, DeviceId, EmailAddress,
    KeyHandle, OpaqueId, RootIdentity, Trust, UserId, VerifiedProviderIdentity)

LIMIT=8*1024*1024
PROFILE='M2-EXPERIMENT-RFC9980-AES256-GCM'
PROVIDER='Sequoia 2.4.1 / OpenSSL 3.5.9'
BACKUP=b'QuMail-M3-Recovery-v1\0'


def encode(value):
    data=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
    if len(data)>LIMIT: raise BoundaryError(Code.LIMIT)
    return data


def protect(key, plain, aad):
    nonce=secrets.token_bytes(12)
    return nonce+AESGCM(key).encrypt(nonce,plain,aad)


def unprotect(key, blob, aad):
    if not isinstance(blob,bytes) or not 28<=len(blob)<=LIMIT+28:
        raise BoundaryError(Code.CORRUPT)
    try: return AESGCM(key).decrypt(blob[:12],blob[12:],aad)
    except (InvalidTag,ValueError): raise BoundaryError(Code.CORRUPT) from None


def safe_path(path):
    path=Path(path).absolute()
    for part in [*path.parents,path]:
        if part.exists() or part.is_symlink():
            s=part.lstat()
            if stat.S_ISLNK(s.st_mode) or getattr(s,'st_file_attributes',0)&0x400:
                raise BoundaryError(Code.INVALID)
    return path


class Vault:
    def __init__(self, path, secure_store, provider):
        self.path=safe_path(path)
        self.store=secure_store
        self.provider=provider
        # Explicit file path is local configuration, never an address/handle.
        with self.connection() as db:
            row=db.execute('SELECT id FROM vault').fetchone()
        if not row: raise BoundaryError(Code.CORRUPT)
        self.ident=OpaqueId(row[0]).value
        self.store.get(self.ident)  # no cached master key and no fallback

    @classmethod
    def create(cls,path,store,provider):
        path=safe_path(path)
        if path.exists(): raise BoundaryError(Code.CONFLICT)
        path.parent.mkdir(parents=True,exist_ok=True)
        ident=OpaqueId.new().value
        master=secrets.token_bytes(32)
        # OS store and SQLite cannot share a transaction. Store first: a crash can
        # leave an orphan OS entry, never an unwrapped database or usable partial account.
        store.put(ident,master)
        try:
            if store.get(ident)!=master: raise BoundaryError(Code.STORE)
            with path.open('xb'): pass
            with sqlite3.connect(path) as db:
                db.executescript('PRAGMA synchronous=FULL; CREATE TABLE vault(id TEXT PRIMARY KEY);'
                    'CREATE TABLE accounts(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, blob BLOB NOT NULL);')
                db.execute('INSERT INTO vault VALUES(?)',(ident,))
            return cls(path,store,provider)
        except BaseException:
            store.delete(ident)
            # Keep any partial encrypted database for explicit diagnosis; never adopt it.
            raise

    @contextmanager
    def connection(self):
        safe_path(self.path)
        db=sqlite3.connect(self.path,timeout=5,isolation_level=None)
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH,LIMIT+4096)
        db.execute('PRAGMA synchronous=FULL')
        db.execute('PRAGMA busy_timeout=5000')
        try: yield db
        except sqlite3.Error: raise BoundaryError(Code.CONFLICT) from None
        finally: db.close()

    def aad(self,ident,revision):
        return f'QuMail-M3-record-v1/{self.ident}/{ident}/{revision}'.encode()

    def load(self,db,account,master):
        if type(account) is not AccountId: raise BoundaryError(Code.OWNERSHIP)
        row=db.execute('SELECT revision,blob FROM accounts WHERE id=?',(account.value,)).fetchone()
        if not row: raise BoundaryError(Code.OWNERSHIP)
        try:
            data=json.loads(unprotect(master,row[1],self.aad(account.value,row[0])))
            if data['account']!=account.value or data['version']!=1: raise ValueError()
            return row[0],data
        except (ValueError,KeyError,TypeError): raise BoundaryError(Code.CORRUPT) from None

    def check(self,data,ctx,active=False):
        if (type(ctx) is not AccountContext or type(ctx.device) is not DeviceId or
            data['account']!=ctx.account.value or data['device']!=ctx.device.value or
            data['issuer']!=ctx.issuer or data['subject']!=ctx.subject):
            raise BoundaryError(Code.OWNERSHIP)
        if active and data['state']!='active': raise BoundaryError(Code.LIFECYCLE)

    @contextmanager
    def transaction(self,ctx,active=False):
        master=self.store.get(self.ident)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                revision,data=self.load(db,ctx.account,master)
                self.check(data,ctx,active)
                yield data
                blob=protect(master,encode(data),self.aad(ctx.account.value,revision+1))
                db.execute('UPDATE accounts SET revision=?,blob=? WHERE id=?',(revision+1,blob,ctx.account.value))
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK'); raise

    def _read(self,ctx):
        master=self.store.get(self.ident)
        with self.connection() as db:
            _,data=self.load(db,ctx.account,master)
        self.check(data,ctx)
        return data

    def key_record(self,data,material):
        handle=KeyHandle.new()
        now=int(time.time())
        data['keys'][handle.value]=dict(account=data['account'],device=data['device'],
            purpose='root-certification/device-signing/device-encryption',profile=PROFILE,
            provider=PROVIDER,created=now,expires=now+365*86400,state='active',
            fingerprint=material['fingerprint'],signing=material['signing'],
            encryption=material['encryption'],secret=material['secret'],public=material['public'])
        data['active_key']=handle.value
        return handle

    def enroll(self,identity:VerifiedProviderIdentity,address:EmailAddress,user:UserId):
        if (type(identity) is not VerifiedProviderIdentity or identity.expires<=int(time.time()) or
            address not in identity.addresses or not identity.subject or identity.issuer != "https://accounts.google.com" or type(user) is not UserId):
            raise BoundaryError(Code.IDENTITY)
        master=self.store.get(self.ident)  # Block before provider generation if unavailable.
        material=self.provider.call('generate',address=address.value)
        account=AccountId.new(); device=DeviceId.new()
        data=dict(version=1,account=account.value,device=device.value,user=user.value,
            issuer=identity.issuer,subject=identity.subject,addresses=[a.value for a in identity.addresses],
            address=address.value,state='active',keys={},contacts={},events=[],root=material['fingerprint'])
        handle=self.key_record(data,material)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                for row in db.execute('SELECT id FROM accounts').fetchall():
                    _,old=self.load(db,AccountId(row[0]),master)
                    if (old['issuer'],old['subject'])==(identity.issuer,identity.subject):
                        raise BoundaryError(Code.CONFLICT)
                db.execute('INSERT INTO accounts VALUES(?,?,?)',(account.value,1,protect(master,encode(data),self.aad(account.value,1))))
                db.execute('COMMIT')
            except BaseException: db.execute('ROLLBACK'); raise
        return AccountContext(account,device,identity.issuer,identity.subject),handle

    def key(self,data,ctx,handle,active=False):
        if type(handle) is not KeyHandle: raise BoundaryError(Code.OWNERSHIP)
        key=data['keys'].get(handle.value)
        if not key or key['account']!=ctx.account.value or key['device']!=ctx.device.value:
            raise BoundaryError(Code.OWNERSHIP)
        if active and (key['state']!='active' or key['expires']<=int(time.time()) or data['state']!='active'):
            raise BoundaryError(Code.LIFECYCLE)
        if key['state']=='destroyed': raise BoundaryError(Code.LIFECYCLE)
        return key

    def export_public(self,ctx,handle):
        data=self._read(ctx); key=self.key(data,ctx,handle)
        # Re-serialize via provider, never return the encrypted secret record itself.
        return bytes(self.provider.call('public',certificate=bytes(key['secret']))['public'])

    def store_oauth(self,ctx,identity,tokens):
        if (type(identity) is not VerifiedProviderIdentity or identity.expires<=int(time.time()) or
            (identity.issuer,identity.subject)!=(ctx.issuer,ctx.subject) or
            not isinstance(tokens,dict) or set(tokens)-{'access_token','refresh_token','expiry','scopes'} or
            len(encode(tokens))>32768):
            raise BoundaryError(Code.IDENTITY)
        with self.transaction(ctx) as data:
            if not set(data['addresses'])<={a.value for a in identity.addresses}:
                raise BoundaryError(Code.IDENTITY)
            data['oauth']=tokens

    def oauth(self,ctx):
        # Only an authenticated account context may resolve this protected record.
        return self._read(ctx).get('oauth')

    def import_contact(self,ctx,address,public):
        try:
            info=self.provider.call('inspect',certificate=public)
        except BoundaryError:
            revoked=self.provider.call('revocation',certificate=public)
            with self.transaction(ctx) as data:
                old=data['contacts'].get(address.value)
                if not old or old['fingerprint']!=revoked['fingerprint']: raise BoundaryError(Code.TRUST)
                old['state']=Trust.REVOKED.value
            return RootIdentity(revoked['fingerprint'])
        if address.value not in [EmailAddress(a).value for a in info['addresses']]:
            raise BoundaryError(Code.IDENTITY)
        RootIdentity(info['fingerprint'])
        with self.transaction(ctx) as data:
            old=data['contacts'].get(address.value)
            state=Trust.UNVERIFIED.value
            retired=[]
            if old:
                if old['fingerprint']!=info['fingerprint']: state=Trust.CHANGED.value
                elif old['state']==Trust.REVOKED.value: state=Trust.REVOKED.value
                else:
                    state=old['state']; retired=list(old.get('retired_subkeys',[]))
                    if info['signing'] in retired or info['encryption'] in retired:
                        raise BoundaryError(Code.TRUST)
                    for name in ('signing','encryption'):
                        if old[name]!=info[name]: retired.append(old[name])
            data['contacts'][address.value]=dict(fingerprint=info['fingerprint'],public=list(public),
                signing=info['signing'],encryption=info['encryption'],retired_subkeys=retired,
                state=state,method=old['method'] if old and state==Trust.VERIFIED.value else '',
                verified_at=old['verified_at'] if old and state==Trust.VERIFIED.value else 0)
        return RootIdentity(info['fingerprint'])

    def pin_contact(self,ctx,address,fingerprint:RootIdentity,method:str):
        if method not in ('in-person','independent-voice','independent-qr'):
            raise BoundaryError(Code.TRUST)
        with self.transaction(ctx) as data:
            contact=data['contacts'].get(address.value)
            if not contact or contact['fingerprint']!=fingerprint.fingerprint or contact['state']==Trust.REVOKED.value:
                raise BoundaryError(Code.TRUST)
            self.provider.call('inspect',certificate=bytes(contact['public']))
            contact.update(state=Trust.VERIFIED.value,method=method,verified_at=int(time.time()))

    def revoke_contact(self,ctx,address):
        with self.transaction(ctx) as data:
            if address.value not in data['contacts']: raise BoundaryError(Code.TRUST)
            data['contacts'][address.value]['state']=Trust.REVOKED.value

    def recipient(self,data,address):
        contact=data['contacts'].get(address.value)
        if not contact or contact['state']!=Trust.VERIFIED.value: raise BoundaryError(Code.TRUST)
        self.provider.call('inspect',certificate=bytes(contact['public']))
        return bytes(contact['public'])

    def seal_for_test(self,ctx,handle,address,plaintext):
        # Not exposed to production send; transaction holds lifecycle stable through operation.
        with self.transaction(ctx,active=True) as data:
            key=self.key(data,ctx,handle,True)
            result=self.provider.call('seal',certificate=bytes(key['secret']),
                recipient=self.recipient(data,address),data=plaintext)
        return bytes(result['data'])

    def open_for_test(self,ctx,handle,sender_public,ciphertext):
        data=self._read(ctx); key=self.key(data,ctx,handle)
        # Archive uses original certificate snapshots; historical status is separate
        # from authorization to encrypt/sign now. Provider still verifies integrity/signature.
        return bytes(self.provider.call('open',certificate=bytes(key['secret']),sender=sender_public,data=ciphertext)['data'])

    def rotate(self,ctx,handle):
        with self.transaction(ctx,active=True) as data:
            key=self.key(data,ctx,handle,True)
            material=self.provider.call('rotate',certificate=bytes(key['secret']))
            if material['fingerprint']!=data['root']: raise BoundaryError(Code.PROVIDER)
            key['state']='retired'
            new=self.key_record(data,material)
            data['events'].append('device_keys_rotated')
        return new

    def revoke(self,ctx,handle):
        with self.transaction(ctx) as data:
            key=self.key(data,ctx,handle)
            revocation=self.provider.call('revoke',certificate=bytes(key['secret']))
            # Preserve pre-revocation secret snapshot exclusively for archive decryption.
            key['state']='revoked'; key['revocation_public']=revocation['public']
            if handle.value==data['active_key']: data['state']='revoked'
        return bytes(revocation['public'])

    def replace_root(self,ctx):
        with self.transaction(ctx) as data:
            material=self.provider.call('generate',address=data['address'])
            for key in data['keys'].values():
                if key['state']=='active': key['state']='retired'
            data['root']=material['fingerprint']; data['state']='active'
            new=self.key_record(data,material)
            data['events'].append('root_replaced_contacts_must_reverify')
        return new

    def destroy_archive_key(self,ctx,handle,accept_loss=False):
        if accept_loss is not True: raise BoundaryError(Code.LIFECYCLE)
        with self.transaction(ctx) as data:
            key=self.key(data,ctx,handle)
            if key['state']=='active': raise BoundaryError(Code.LIFECYCLE)
            key['secret']=[]; key['state']='destroyed'
            data['events'].append('local_archive_key_destroyed_backups_unchanged')

    def export_recovery(self,ctx,explicit=False):
        if explicit is not True: raise BoundaryError(Code.INVALID)
        recovery=secrets.token_bytes(32)
        with self.transaction(ctx) as data:
            data['state']='suspended_for_transfer'
            data['events'].append('explicit_recovery_export_source_suspended')
            snapshot={k:v for k,v in data.items() if k!='oauth'}
            backup=BACKUP+protect(recovery,encode(snapshot),BACKUP)
        # Commit must succeed before bytes are returned. User stores both separately.
        return backup,recovery

    def restore(self,backup,recovery,identity,explicit=False):
        if explicit is not True or len(recovery)!=32 or not backup.startswith(BACKUP):
            raise BoundaryError(Code.INVALID)
        master=self.store.get(self.ident)
        try:
            data=json.loads(unprotect(recovery,backup[len(BACKUP):],BACKUP))
            if (data['version']!=1 or identity.expires<=int(time.time()) or
                (data['issuer'],data['subject'])!=(identity.issuer,identity.subject) or
                not set(data['addresses']) <= {a.value for a in identity.addresses}):
                raise BoundaryError(Code.IDENTITY)
            oldaccount=AccountId(data['account']); olddevice=DeviceId(data['device'])
            account=AccountId.new(); device=DeviceId.new()
            for handle,key in data['keys'].items():
                KeyHandle(handle)
                if (key['account'],key['device'],key['profile'],key['provider'])!=(oldaccount.value,olddevice.value,PROFILE,PROVIDER):
                    raise BoundaryError(Code.CORRUPT)
                if key['state']!='destroyed':
                    info=self.provider.call('public',certificate=bytes(key['secret']))
                    if info['public']!=key['public'] or info['fingerprint']!=key['fingerprint']:
                        raise BoundaryError(Code.CORRUPT)
                key['account']=account.value; key['device']=device.value
                if key['state']=='active': key['state']='retired'
            data.update(account=account.value,device=device.value,state='archive_only')
            data['events'].append('restored_archive_only_new_root_required')
            with self.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                try:
                    if db.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]: raise BoundaryError(Code.CONFLICT)
                    db.execute('INSERT INTO accounts VALUES(?,?,?)',(account.value,1,protect(master,encode(data),self.aad(account.value,1))))
                    db.execute('COMMIT')
                except BaseException: db.execute('ROLLBACK'); raise
            return AccountContext(account,device,identity.issuer,identity.subject)
        except (KeyError,ValueError,TypeError): raise BoundaryError(Code.CORRUPT) from None
