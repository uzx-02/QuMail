from concurrent.futures import Future
import time
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import threading
from urllib.parse import parse_qs,urlsplit
import pytest
import requests
from experiments.m3.tests.test_m3 import vault,provider,enroll,synthetic_identity,pin
from experiments.m3.types import *
from experiments.m3.vault import Vault
from core.identity_service import IdentityService
from transport import development_google as google
from ui.identity_settings import IdentitySettings

CONFIG={'installed':dict(client_id='synthetic.apps.googleusercontent.com',client_secret='synthetic-config',
                        auth_uri=google.AUTH,token_uri=google.TOKEN)}

def result(subject='alice'):
    return google.Authorization(synthetic_identity(subject,subject+'@example.invalid'),
        dict(access_token='synthetic-only',refresh_token='synthetic-refresh',expiry=2000000000,scopes=list(google.SCOPES)))

@pytest.fixture
def service(vault):
    service=IdentityService(vault.path,vault.provider,vault.store,google.GoogleAuthorization(CONFIG))
    service.unlock()
    yield service
    service.lock()

def add(service,subject):
    ticket=service.session.begin()
    assert service.accept_authorization(ticket,result(subject))
    return service.session.snapshot.active

def test_coherent_notifications_switch_lock_cancel(service,qapp):
    observed=[]
    service.session.changed.connect(lambda s:observed.append((s,service.session.snapshot)))
    a=add(service,'alice'); b=add(service,'bob')
    assert all(event==installed for event,installed in observed)
    assert a.context.account!=b.context.account
    ticket=service.session.begin(); service.select(a.context.account)
    assert not service.accept_authorization(ticket,result('late'))
    assert len(service.vault.summaries())==2
    assert service.session.snapshot.active==a
    ticket=service.session.begin(); service.session.invalidate()
    assert not service.accept_authorization(ticket,result('cancelled'))
    service.lock()
    assert service.session.snapshot.locked and service.session.snapshot.active is None
    with pytest.raises(BoundaryError): service.contacts()
    service.unlock(); assert len(service.session.snapshot.accounts)==2

def test_stale_refresh_and_identity_mismatch(service):
    a=add(service,'alice'); b=add(service,'bob')
    service.select(a.context.account); ticket=service.session.begin()
    with pytest.raises(BoundaryError): service.accept_authorization(ticket,result('bob'),'refresh')
    assert service.vault.oauth(a.context)['access_token']=='synthetic-only'
    ticket=service.session.begin(); service.select(b.context.account)
    assert not service.accept_authorization(ticket,result('alice'),'refresh')
    assert service.session.snapshot.active==b

def test_atomic_enrollment_vault_failure(service,monkeypatch):
    before=service.session.snapshot
    ticket=service.session.begin()
    monkeypatch.setattr(service.store,'get',lambda *args:(_ for _ in ()).throw(BoundaryError(Code.STORE)))
    with pytest.raises(BoundaryError): service.accept_authorization(ticket,result())
    assert service.session.snapshot.active is None
    import sqlite3
    with sqlite3.connect(service.path) as db: assert db.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]==0

def drain_settings(window,qapp):
    end=time.monotonic()+10
    while (window.operations.busy or window.needs_read) and time.monotonic()<end:
        qapp.processEvents(); window.poll(); time.sleep(.005)
    assert not window.operations.busy and not window.needs_read


def test_settings_controls_and_stale_worker_display(service,qapp,monkeypatch):
    a=add(service,'alice'); b=add(service,'bob')
    window=IdentitySettings(service)
    window.show(); qapp.processEvents()
    assert 'sending disabled' in window.windowTitle()
    assert not any('send' in name.lower() for name in window.buttons)
    index=next(i for i in range(window.accounts.count()) if window.accounts.itemData(i)==a.context.account)
    window.accounts.setCurrentIndex(index); qapp.processEvents()
    assert service.session.snapshot.active==a and 'alice@example.invalid' in window.details.text()
    drain_settings(window,qapp)
    entered=threading.Event(); release=threading.Event()
    def delayed(*args):
        entered.set(); assert release.wait(3); return result('late')
    monkeypatch.setattr(service.google,'authorize',delayed)
    window.address.setText('late@example.invalid'); window.start_auth()
    assert entered.wait(2)
    window.buttons['Lock'].click(); qapp.processEvents()
    release.set(); drain_settings(window,qapp)
    assert window.details.text()=='No account selected' and window.contacts.rowCount()==0
    assert service.vault is None
    window.close(); window.dispose(); window.pool.shutdown(wait=True); qapp.processEvents()

def test_settings_trust_changed_revoked_expired(service,qapp,monkeypatch):
    a=add(service,'alice'); b=add(service,'bob'); service.select(a.context.account)
    address='bob@example.invalid'
    public=service.vault.export_public(b.context,b.key)
    root=service.import_certificate(address,public)
    window=IdentitySettings(service); window.show(); window.refresh_contacts(); drain_settings(window,qapp)
    assert window.contacts.item(0,2).text()==Trust.UNVERIFIED.value
    service.verify_fingerprint(address,root.fingerprint,'in-person'); window.refresh_contacts(); drain_settings(window,qapp)
    assert window.contacts.item(0,2).text()==Trust.VERIFIED.value
    real=service.provider.call
    def expired(op,**kwargs): return {'state':'expired'} if op=='status' else real(op,**kwargs)
    monkeypatch.setattr(service.provider,'call',expired); window.refresh_contacts(); drain_settings(window,qapp)
    assert window.contacts.item(0,2).text()=='expired'  # Labeled display fixture, not time travel.
    monkeypatch.setattr(service.provider,'call',real)
    new=service.vault.replace_root(b.context)
    service.import_certificate(address,service.vault.export_public(b.context,new)); window.refresh_contacts(); drain_settings(window,qapp)
    assert window.contacts.item(0,2).text()==Trust.CHANGED.value
    revoked=service.vault.revoke(b.context,new); service.import_certificate(address,revoked); window.refresh_contacts(); drain_settings(window,qapp)
    assert window.contacts.item(0,2).text()==Trust.REVOKED.value
    window.close(); window.dispose(); window.pool.shutdown(wait=True)

def test_backup_transfer_failed_persistence_and_restore(service,tmp_path,provider):
    view=add(service,'alice')
    ordinary=tmp_path/'backup.bin'
    secret=service.backup(ordinary)
    assert service.session.snapshot.active.lifecycle=='active'
    with pytest.raises(BoundaryError): service.backup(ordinary,transfer=True,confirmed=True)
    assert service.session.snapshot.active.lifecycle=='active'
    with pytest.raises(BoundaryError): service.backup(tmp_path/'no.bin',transfer=True)
    transfer=tmp_path/'transfer.bin'; transfer_secret=service.backup(transfer,transfer=True,confirmed=True)
    assert service.session.snapshot.active.lifecycle=='suspended_for_transfer'
    clean=Vault.create(tmp_path/'restore.sqlite',service.store,provider)
    try:
        restored=clean.restore(ordinary.read_bytes(),secret,result().identity,explicit=True)
        assert clean._read(restored)['state']=='archive_only'
        with pytest.raises(BoundaryError): clean.activate_restored_root(restored)
        clean.activate_restored_root(restored,True)
        assert clean._read(restored)['root']==view.root
        assert clean._read(restored)['state']=='active'
        replacement=clean.replace_root(restored)
        assert clean._read(restored)['root']!=view.root
    finally: service.store.delete(clean.ident)

@pytest.mark.parametrize('path,host',[('/wrong?state=s&code=c','127.0.0.1:123'),('/?state=x&code=c','127.0.0.1:123'),
    ('/?state=s&code=c&code=d','127.0.0.1:123'),('/?state=s&code=c','127.0.0.1:124'),
    ('/?state=s&code=c','attacker.invalid'),('/?state=s&error=access_denied','127.0.0.1:123')])
def test_callback_rejects_host_port_path_state_duplicates(path,host):
    with pytest.raises(BoundaryError): google.callback_code(path,host,'127.0.0.1:123','s')

def test_real_loopback_callback_and_cancellation():
    listener=google.Loopback('s'*32); cancel=threading.Event()
    def browser():
        with requests.Session() as session:
            session.trust_env=False
            response=session.get(listener.redirect,params={'state':'s'*32,'code':'synthetic'},timeout=3)
            assert response.status_code==200
    thread=threading.Thread(target=browser); thread.start()
    try: assert listener.wait(cancel,3)=='synthetic'
    finally: thread.join(); listener.close()
    second=google.Loopback('s'*32); cancel.set()
    try:
        with pytest.raises(BoundaryError): second.wait(cancel,3)
    finally: second.close()

def test_google_flow_pkce_and_verified_result(monkeypatch):
    actual=google.InstalledAppFlow
    observed={}
    def fetch(self,**kwargs):
        assert self.code_verifier and kwargs['timeout']==15 and kwargs['allow_redirects'] is False
        assert kwargs['code']=='synthetic'
        return {'id_token':'synthetic-id','access_token':'synthetic-access','refresh_token':'synthetic-refresh',
                'expires_at':2000000000,'scope':list(google.SCOPES)}
    monkeypatch.setattr(actual,'fetch_token',fetch)
    monkeypatch.setattr(google,'google_identity',lambda token,cid,nonce,state,received,subject,request=None:
        result().identity if nonce==observed['nonce'] and state==received==observed['state'] else None)
    threads=[]
    def opener(url):
        query=parse_qs(urlsplit(url).query)
        assert query['code_challenge_method']==['S256'] and len(query['code_challenge'][0])==43
        assert query['scope'][0].split()==list(google.SCOPES)
        observed.update(nonce=query['nonce'][0],state=query['state'][0])
        def callback():
            with requests.Session() as session:
                session.trust_env=False
                session.get(query['redirect_uri'][0],params={'state':query['state'][0],'code':'synthetic'},timeout=3)
        thread=threading.Thread(target=callback); thread.start(); threads.append(thread)
        return True
    authorization=google.GoogleAuthorization(CONFIG).authorize(threading.Event(),'alice@example.invalid',opener=opener)
    for thread in threads: thread.join()
    assert authorization.identity.subject=='alice'

def test_google_cancel_before_browser(monkeypatch):
    cancel=threading.Event(); cancel.set()
    with pytest.raises(BoundaryError): google.GoogleAuthorization(CONFIG).authorize(cancel,'alice@example.invalid',
        opener=lambda url:pytest.fail('browser opened after cancellation'))

def test_refresh_userinfo_subject_mismatch_and_success(monkeypatch):
    observed={'sub':'bob'}
    class FakeCredentials:
        def __init__(self,*args,**kwargs): self.token='synthetic-new'; self.refresh_token='synthetic-refresh'; self.id_token=None
        def refresh(self,request): self.expiry=datetime.now(timezone.utc)+timedelta(hours=1)
    class Session:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def close(self): pass
        def get(self,url,**kwargs):
            assert url==google.USERINFO and kwargs['timeout']==15 and kwargs['allow_redirects'] is False
            return type('Response',(),{'status_code':200,'json':lambda _:dict(sub=observed['sub'],email='alice@example.invalid',email_verified=True)})()
    monkeypatch.setattr(google,'Credentials',FakeCredentials); monkeypatch.setattr(google.requests,'Session',Session)
    context=AccountContext(AccountId.new(),DeviceId.new(),'https://accounts.google.com','alice')
    auth=google.GoogleAuthorization(CONFIG)
    with pytest.raises(BoundaryError): auth.refresh(threading.Event(),context,'alice@example.invalid',result().tokens)
    observed['sub']='alice'
    assert auth.refresh(threading.Event(),context,'alice@example.invalid',result().tokens).identity.subject=='alice'

def test_entry_point_default_and_exclusive_development(monkeypatch):
    import main
    calls=[]
    monkeypatch.setattr(main,'_launch_desktop',lambda:calls.append('legacy') or 0)
    monkeypatch.setattr(main,'_launch_identity',lambda path,client:calls.append(('identity',path,client)) or 0)
    main.main([]); main.main(['--dev-identity','--dev-vault','synthetic.sqlite'])
    assert calls==['legacy',('identity','synthetic.sqlite',None)]
    with pytest.raises(SystemExit): main.main(['--dev-identity','--dev-simulator','--dev-vault','synthetic.sqlite'])


def test_transfer_persistence_and_commit_failures_leave_source_active(service,tmp_path,monkeypatch):
    from contextlib import contextmanager
    import sqlite3
    import core.identity_service as services
    view=add(service,'alice')
    with monkeypatch.context() as patch:
        patch.setattr(services.os,'fsync',lambda *args:(_ for _ in ()).throw(OSError('synthetic disk failure')))
        with pytest.raises(BoundaryError): service.backup(tmp_path/'failed.bin',transfer=True,confirmed=True)
    assert service.vault._read(view.context)['state']=='active'
    original=service.vault.connection
    @contextmanager
    def deny_commit():
        with original() as db:
            db.set_authorizer(lambda action,arg,*rest:sqlite3.SQLITE_DENY
                if action==sqlite3.SQLITE_TRANSACTION and arg=='COMMIT' else sqlite3.SQLITE_OK)
            yield db
    with monkeypatch.context() as patch:
        patch.setattr(service.vault,'connection',deny_commit)
        with pytest.raises(BoundaryError): service.backup(tmp_path/'persisted.bin',transfer=True,confirmed=True)
    assert (tmp_path/'persisted.bin').exists()
    assert service.vault._read(view.context)['state']=='active'


def test_settings_backup_and_transfer_controls(service,qapp,tmp_path,monkeypatch):
    import ui.identity_settings as ui
    add(service,'alice'); window=IdentitySettings(service)
    outputs=iter([str(tmp_path/'ordinary.bin'),str(tmp_path/'transfer.bin')])
    monkeypatch.setattr(ui.QFileDialog,'getSaveFileName',lambda *args: (next(outputs),''))
    monkeypatch.setattr(ui.QMessageBox,'information',lambda *args:None)
    monkeypatch.setattr(ui.QMessageBox,'question',lambda *args:ui.QMessageBox.StandardButton.Yes)
    drain_settings(window,qapp)
    window.buttons['Encrypted backup'].click()
    drain_settings(window,qapp)
    assert not (tmp_path/'ordinary.bin').exists()
    window.acknowledge_backup(window.recovery.secret.hex()); drain_settings(window,qapp)
    assert service.session.snapshot.active.lifecycle=='active'
    window.buttons['Transfer device'].click()
    drain_settings(window,qapp)
    assert not (tmp_path/'transfer.bin').exists()
    window.acknowledge_backup(window.recovery.secret.hex()); drain_settings(window,qapp)
    assert service.session.snapshot.active.lifecycle=='suspended_for_transfer'
    window.close(); window.dispose(); window.pool.shutdown(wait=True)


def test_enrollment_commit_failure_leaves_no_partial_account(service,monkeypatch):
    from contextlib import contextmanager
    import sqlite3
    original=service.vault.connection
    @contextmanager
    def deny_commit():
        with original() as db:
            db.set_authorizer(lambda action,arg,*rest:sqlite3.SQLITE_DENY
                if action==sqlite3.SQLITE_TRANSACTION and arg=='COMMIT' else sqlite3.SQLITE_OK)
            yield db
    ticket=service.session.begin()
    with monkeypatch.context() as patch:
        patch.setattr(service.vault,'connection',deny_commit)
        with pytest.raises(BoundaryError): service.accept_authorization(ticket,result())
    assert service.vault.summaries()==[] and service.session.snapshot.active is None


def test_completed_transfer_recovery_secret_survives_display_failure(service,tmp_path,monkeypatch):
    add(service,'alice')
    monkeypatch.setattr(service,'reload',lambda *args:(_ for _ in ()).throw(BoundaryError(Code.STORE)))
    path=tmp_path/'transfer.bin'
    secret=service.backup(path,transfer=True,confirmed=True)
    assert len(secret)==32 and path.exists() and service.session.snapshot.locked


def test_explicit_client_config_allowlist_and_no_cache(tmp_path):
    file=tmp_path/'synthetic-client.json'
    for auth in google.GOOGLE_CLIENT_AUTH_URIS:
        config={'installed':dict(CONFIG['installed'],auth_uri=auth)}
        file.write_text(json.dumps(config))
        assert google.client_configuration(file)['installed']['auth_uri']==google.AUTH
    file.write_text(json.dumps({'installed':dict(CONFIG['installed'],token_uri='https://attacker.invalid/token')}))
    with pytest.raises(BoundaryError): google.client_configuration(file)
    with pytest.raises(BoundaryError): google.client_configuration(tmp_path/'not-provisioned.json')
