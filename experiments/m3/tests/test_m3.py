"""Disposable real Windows storage/provider tests; OAuth evidence is synthetic."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import time
import pytest
from experiments.m3 import identity
from experiments.m3.provider import Provider
from experiments.m3.secure_store import WindowsCredentialStore
from experiments.m3.types import *
from experiments.m3.vault import Vault

ROOT=Path(__file__).resolve().parents[3]


def synthetic_identity(subject='alice',address='alice@example.invalid'):
    # Internal claims fixture only. It cannot establish Google/Yahoo acceptance.
    return identity.validated_google_claims(dict(iss='https://accounts.google.com',aud='test-client',
        sub=subject,email=address,hd='example.invalid',email_verified=True,nonce='n'*32,exp=int(time.time())+3600),
        'test-client','n'*32)


@pytest.fixture
def provider():
    return Provider(ROOT/'tmp/m2/target/debug/qumail-m3-provider.exe')


@pytest.fixture
def vault(tmp_path,provider):
    store=WindowsCredentialStore()
    v=Vault.create(tmp_path/'vault.sqlite',store,provider)
    try: yield v
    finally:
        store.delete(v.ident)
        with pytest.raises(BoundaryError): store.get(v.ident)


def enroll(v,subject='alice'):
    ident=synthetic_identity(subject,f'{subject}@example.invalid')
    return v.enroll(ident,ident.addresses[0],UserId.new())


def pin(v,ctx,address,public):
    root=v.import_contact(ctx,address,public)
    v.pin_contact(ctx,address,root,'in-person')


def test_real_windows_store_lifecycle():
    store=WindowsCredentialStore(); ident=OpaqueId.new().value
    key=secrets.token_bytes(32)
    try:
        store.put(ident,key)
        assert secrets.compare_digest(store.get(ident),key)
        changed=secrets.token_bytes(32); store.put(ident,changed)
        assert secrets.compare_digest(store.get(ident),changed)
    finally: store.delete(ident)
    with pytest.raises(BoundaryError): store.get(ident)


def test_two_accounts_same_provider_opaque_ownership(vault):
    a,ak=enroll(vault); b,bk=enroll(vault,'bob')
    assert a.account!=b.account and a.device!=b.device
    for context,key in [(a,bk),(b,ak),(replace(a,subject=b.subject),ak),(replace(a,device=b.device),ak)]:
        with pytest.raises(BoundaryError): vault.export_public(context,key)
    with pytest.raises(BoundaryError): enroll(vault)
    public=vault.export_public(a,ak)
    assert vault.provider.call('inspect',certificate=public)['fingerprint']
    raw=vault.path.read_bytes()
    assert b'alice@example.invalid' not in raw and b'https://accounts.google.com' not in raw


def test_first_contact_substitution_and_reverification(vault):
    a,ak=enroll(vault); b,bk=enroll(vault,'bob'); address=EmailAddress('bob@example.invalid')
    bp=vault.export_public(b,bk); root=vault.import_contact(a,address,bp)
    with pytest.raises(BoundaryError): vault.seal_for_test(a,ak,address,b'fixture')
    with pytest.raises(BoundaryError): vault.pin_contact(a,address,RootIdentity('0'*64),'in-person')
    with pytest.raises(BoundaryError): vault.pin_contact(a,address,root,'directory')
    vault.pin_contact(a,address,root,'independent-voice')
    cipher=vault.seal_for_test(a,ak,address,b'fixture')
    assert vault.open_for_test(b,bk,vault.export_public(a,ak),cipher)==b'fixture'
    new=vault.replace_root(b)
    vault.import_contact(a,address,vault.export_public(b,new))
    with pytest.raises(BoundaryError): vault.seal_for_test(a,ak,address,b'fixture')
    pin(vault,a,address,vault.export_public(b,new))
    assert vault.seal_for_test(a,ak,address,b'fixture')
    vault.revoke_contact(a,address)
    with pytest.raises(BoundaryError): vault.seal_for_test(a,ak,address,b'fixture')


def test_invalid_address_secret_import_and_corrupted_certificate(vault):
    a,ak=enroll(vault)
    material=vault.provider.call('generate',address='bob@example.invalid')
    with pytest.raises(BoundaryError): vault.import_contact(a,EmailAddress('eve@example.invalid'),bytes(material['public']))
    with pytest.raises(BoundaryError): vault.import_contact(a,EmailAddress('bob@example.invalid'),bytes(material['secret']))
    corrupted=bytearray(material['public']); corrupted[len(corrupted)//2]^=255
    with pytest.raises(BoundaryError): vault.import_contact(a,EmailAddress('bob@example.invalid'),bytes(corrupted))


def test_rotation_revocation_expiry_and_archive(vault):
    a,ak=enroll(vault); b,bk=enroll(vault,'bob'); addr=EmailAddress('bob@example.invalid')
    ap=vault.export_public(a,ak); original_public=vault.export_public(b,bk); pin(vault,a,addr,original_public)
    old=vault.seal_for_test(a,ak,addr,b'history')
    new=vault.rotate(b,bk)
    updated=vault.export_public(b,new); pin(vault,a,addr,updated)
    with pytest.raises(BoundaryError): vault.import_contact(a,addr,original_public)
    fresh=vault.seal_for_test(a,ak,addr,b'fresh')
    assert vault.open_for_test(b,new,ap,fresh)==b'fresh'
    assert vault.open_for_test(b,bk,ap,old)==b'history'
    with pytest.raises(BoundaryError): vault.seal_for_test(b,bk,EmailAddress('alice@example.invalid'),b'fixture')
    revocation=vault.revoke(b,new)
    vault.import_contact(a,addr,revocation)
    with pytest.raises(BoundaryError): vault.seal_for_test(a,ak,addr,b'fixture')
    with pytest.raises(BoundaryError): vault.provider.call('inspect',certificate=revocation)
    with pytest.raises(BoundaryError): vault.seal_for_test(b,new,addr,b'fixture')
    assert vault.open_for_test(b,new,ap,fresh)==b'fresh'
    with vault.transaction(a) as data: data['keys'][ak.value]['expires']=1
    with pytest.raises(BoundaryError): vault.seal_for_test(a,ak,addr,b'fixture')
    with pytest.raises(BoundaryError): vault.destroy_archive_key(b,bk)
    vault.destroy_archive_key(b,bk,accept_loss=True)
    with pytest.raises(BoundaryError): vault.open_for_test(b,bk,ap,old)


def test_clean_restore_actual_historical_keys_and_one_device(vault,tmp_path,provider):
    a,ak=enroll(vault); b,bk=enroll(vault,'bob'); addr=EmailAddress('bob@example.invalid')
    ap=vault.export_public(a,ak); pin(vault,a,addr,vault.export_public(b,bk))
    cipher=vault.seal_for_test(a,ak,addr,secrets.token_bytes(32))
    expected=vault.open_for_test(b,bk,ap,cipher)
    with pytest.raises(BoundaryError): vault.export_recovery(b)
    backup,recovery=vault.export_recovery(b,explicit=True)
    with pytest.raises(BoundaryError): vault.seal_for_test(b,bk,addr,b'fixture')
    restored=Vault.create(tmp_path/'clean.sqlite',vault.store,provider)
    try:
        ident=synthetic_identity('bob','bob@example.invalid')
        with pytest.raises(BoundaryError): restored.restore(backup,secrets.token_bytes(32),ident,True)
        altered=bytearray(backup); altered[-1]^=1
        with pytest.raises(BoundaryError): restored.restore(bytes(altered),recovery,ident,True)
        with pytest.raises(BoundaryError): restored.restore(backup,recovery,synthetic_identity(),True)
        ctx=restored.restore(backup,recovery,ident,True)
        assert ctx.device!=b.device and ctx.account!=b.account
        assert secrets.compare_digest(restored.open_for_test(ctx,bk,ap,cipher),expected)
        with pytest.raises(BoundaryError): restored.seal_for_test(ctx,bk,addr,b'fixture')
        new=restored.replace_root(ctx)
        # Old pin cannot silently accept root replacement.
        vault.import_contact(a,addr,restored.export_public(ctx,new))
        with pytest.raises(BoundaryError): vault.seal_for_test(a,ak,addr,b'fixture')
        with pytest.raises(BoundaryError): restored.restore(backup,recovery,ident,True)
    finally: vault.store.delete(restored.ident)


def test_secure_store_absence_blocks_existing_access(vault):
    a,ak=enroll(vault)
    vault.store.delete(vault.ident)
    with pytest.raises(BoundaryError) as error: vault.export_public(a,ak)
    assert error.value.code is Code.STORE
    with pytest.raises(BoundaryError): enroll(vault,'bob')
    assert not list(vault.path.parent.glob('*.key'))


def test_mock_store_failure_no_database_or_provider(tmp_path):
    class Failing:
        def put(self,*args): raise BoundaryError(Code.STORE)
    class Never:
        def call(self,*args,**kwargs): pytest.fail('provider reached')
    with pytest.raises(BoundaryError): Vault.create(tmp_path/'absent.sqlite',Failing(),Never())
    assert not (tmp_path/'absent.sqlite').exists()


def test_restore_commit_denied_leaves_clean_vault(vault,tmp_path,provider,monkeypatch):
    from contextlib import contextmanager
    a,ak=enroll(vault)
    backup,recovery=vault.export_recovery(a,True)
    clean=Vault.create(tmp_path/'restore.sqlite',vault.store,provider)
    original=clean.connection
    @contextmanager
    def deny_commit():
        with original() as db:
            db.set_authorizer(lambda action,arg,*rest: sqlite3.SQLITE_DENY
                if action==sqlite3.SQLITE_TRANSACTION and arg=='COMMIT' else sqlite3.SQLITE_OK)
            yield db
    try:
        monkeypatch.setattr(clean,'connection',deny_commit)
        with pytest.raises(BoundaryError): clean.restore(backup,recovery,synthetic_identity(),True)
        monkeypatch.setattr(clean,'connection',original)
        with original() as db: assert db.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]==0
        ctx=clean.restore(backup,recovery,synthetic_identity(),True)
        assert clean.export_public(ctx,ak)
    finally: clean.store.delete(clean.ident)


def test_parallel_and_interrupted_transaction(vault):
    a,ak=enroll(vault)
    def append(index):
        with vault.transaction(a) as data: data['events'].append('event-'+str(index))
    with ThreadPoolExecutor(max_workers=4) as executor: list(executor.map(append,range(12)))
    data=vault._read(a)
    assert len([x for x in data['events'] if x.startswith('event-')])==12
    with pytest.raises(RuntimeError):
        with vault.transaction(a) as data:
            data['state']='bad'; raise RuntimeError('synthetic interruption')
    assert vault._read(a)['state']=='active'
    # Real abrupt child exit with uncommitted encrypted-row replacement.
    script="import sqlite3,sys,os; d=sqlite3.connect(sys.argv[1]); d.execute('BEGIN IMMEDIATE'); d.execute(\"UPDATE accounts SET blob=x'00'\"); os._exit(17)"
    proc=subprocess.run([sys.executable,'-c',script,str(vault.path)],capture_output=True)
    assert proc.returncode==17
    assert vault._read(a)['state']=='active'


def test_record_corruption_and_cross_account_swap(vault):
    a,ak=enroll(vault); b,bk=enroll(vault,'bob')
    with sqlite3.connect(vault.path) as db:
        row=db.execute('SELECT blob FROM accounts WHERE id=?',(a.account.value,)).fetchone()[0]
        db.execute('UPDATE accounts SET blob=? WHERE id=?',(row,b.account.value))
    with pytest.raises(BoundaryError) as error: vault.export_public(b,bk)
    assert error.value.code is Code.CORRUPT
    assert vault.export_public(a,ak)


def test_real_sqlite_full_rolls_back(vault):
    a,ak=enroll(vault)
    master=vault.store.get(vault.ident)
    with vault.connection() as db:
        pages=db.execute('PRAGMA page_count').fetchone()[0]
        db.execute(f'PRAGMA max_page_count={pages}')
        db.execute('BEGIN IMMEDIATE')
        from experiments.m3.vault import protect,encode
        rev,data=vault.load(db,a.account,master)
        data['events'].append(secrets.token_hex(100000))
        blob=protect(master,encode(data),vault.aad(a.account.value,rev+1))
        with pytest.raises(sqlite3.OperationalError):
            db.execute('UPDATE accounts SET revision=?,blob=? WHERE id=?',(rev+1,blob,a.account.value))
        if db.in_transaction: db.execute('ROLLBACK')
    assert vault._read(a)['state']=='active'
    assert vault._read(a)['events']==[]


@pytest.mark.parametrize('bad',['../secret','C:\\keys','a/b','..','x'*1000,'\0','../../secrets/oauth_master.key'])
def test_hostile_identifiers(bad):
    for kind in (AccountId,DeviceId,KeyHandle):
        with pytest.raises(BoundaryError): kind(bad)


@pytest.mark.parametrize('field,value',[('iss','https://attacker.invalid'),('aud','other'),('azp','other'),
    ('nonce','wrong'),('sub','other'),('email_verified',False),('exp',1),('hd',None),('hd','unrelated.invalid')])
def test_synthetic_oauth_rejection(field,value):
    claims=dict(iss='https://accounts.google.com',aud='test',nonce='n'*32,sub='alice',
        email='alice@example.invalid',hd='example.invalid',email_verified=True,exp=int(time.time())+60)
    claims[field]=value
    with pytest.raises(BoundaryError): identity.validated_google_claims(claims,'test','n'*32,'alice')


def test_maintained_google_signature_verifier_synthetic_issuer(monkeypatch):
    from google.auth import jwt,crypt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    pem=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
    public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    class Response:
        status=200
        data=json.dumps({'fixture':public.decode()}).encode()
    monkeypatch.setattr(identity,'Request',lambda:lambda *args,**kw:Response())
    signer=crypt.RSASigner.from_string(pem,key_id='fixture')
    now=int(time.time())
    claims=dict(iss='https://accounts.google.com',aud='client',nonce='n'*32,sub='alice',iat=now,
        email='alice@example.invalid',hd='example.invalid',email_verified=True,exp=now+60)
    token=jwt.encode(signer,claims).decode()
    result=identity.google_identity(token,'client','n'*32,'s'*32,'s'*32,'alice')
    assert result.subject=='alice'
    with pytest.raises(BoundaryError): identity.google_identity(token+'x','client','n'*32,'s'*32,'s'*32)
    with pytest.raises(BoundaryError): identity.google_identity(token,'client','n'*32,'s'*32,'wrong')
    with pytest.raises(BoundaryError): identity.yahoo_identity()


def test_enrollment_address_not_authorized(vault):
    with pytest.raises(BoundaryError): vault.enroll(synthetic_identity(),EmailAddress('other@example.invalid'),UserId.new())
    with pytest.raises(BoundaryError): vault.enroll(replace(synthetic_identity(),expires=1),EmailAddress('alice@example.invalid'),UserId.new())


def test_account_scoped_oauth_records(vault):
    a,ak=enroll(vault); b,bk=enroll(vault,'bob')
    tokens={'access_token':secrets.token_hex(32),'scopes':['synthetic'],'expiry':int(time.time())+60}
    vault.store_oauth(a,synthetic_identity(),tokens)
    assert vault.oauth(b) is None
    assert secrets.compare_digest(vault.oauth(a)['access_token'],tokens['access_token'])
    with pytest.raises(BoundaryError): vault.store_oauth(b,synthetic_identity(),tokens)
    with pytest.raises(BoundaryError): vault.oauth(replace(a,account=b.account))
    assert tokens['access_token'].encode() not in vault.path.read_bytes()


def test_provider_failure_no_plaintext_or_success(vault):
    a,ak=enroll(vault); b,bk=enroll(vault,'bob'); addr=EmailAddress('bob@example.invalid')
    pin(vault,a,addr,vault.export_public(b,bk))
    msg=vault.seal_for_test(a,ak,addr,b'synthetic')
    for altered in (msg[:-1],msg[:32],msg[:-1]+bytes([msg[-1]^1])):
        with pytest.raises(BoundaryError): vault.open_for_test(b,bk,vault.export_public(a,ak),altered)
