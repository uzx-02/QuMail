import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import time
import pytest
from core.identity_service import IdentityService
from experiments.m3.tests.test_m3 import vault, provider, enroll, pin, synthetic_identity
from experiments.m3.tests.conftest import qapp
from experiments.m3.types import EmailAddress, BoundaryError
from experiments.m4.model import AccountAccess
from experiments.m5.model import Budget, Draft
from experiments.m5.provider import Provider
from experiments.m5.services import Compose
from mailbox_client.model import *
from mailbox_client.gmail import GmailMailbox, LimitedIMAP, MAIL_SCOPE, field
from mailbox_client.service import MailboxService, Credentials, conventional
from .imap_fixture import Server

RAW = b'From: sender@example.invalid\r\nSubject: fixture\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nControlled fixture body'
ROOT = Path(__file__).resolve().parents[2]


def budget(): return Budget(threading.Event(), time.monotonic()+10)


@pytest.fixture
def setup(vault):
    a, ak = enroll(vault); b, bk = enroll(vault, 'bob')
    for ctx, name in [(a,'alice'), (b,'bob')]:
        vault.store_oauth(ctx, synthetic_identity(name, name+'@example.invalid'),
            dict(access_token='synthetic-mail-token', refresh_token='synthetic-refresh', expiry=int(time.time())+3600,
                 scopes=[MAIL_SCOPE]))
    access = AccountAccess(); lease = access.select(a)
    native = Provider(ROOT/'tmp/m2/target/debug/qumail-m5-provider.exe')
    return vault, a, ak, b, bk, access, lease, native


def test_tls_peek_explicit_flags_and_uid_rollover(setup, tmp_path):
    v,a,ak,b,bk,access,lease,native = setup
    messages = {'alice@example.invalid': {9:dict(raw=RAW,seen=False)}}
    with Server(tmp_path/'tls', messages) as server:
        service = MailboxService(v, access, None, GmailMailbox(server.factory), native)
        page = service.headers(lease,budget()); row = page.headers[0]
        assert row.key.uid == 9 and not row.seen
        result = service.open(lease,row.key,ak,None,budget())
        assert result.body == 'Controlled fixture body' and not result.seen
        assert not messages['alice@example.invalid'][9]['seen'] and 'STORE' not in server.events
        assert 'SELECT' not in server.events and 'EXAMINE' in server.events
        assert service.set_seen(lease,row.key,True,budget())
        assert not service.set_seen(lease,row.key,False,budget())
        assert v._read(a)['m6_mailbox_v1']['rows'][0]['seen'] is False
        server.validity += 1
        with pytest.raises(Failure) as error: service.open(lease,row.key,ak,None,budget())
        assert error.value.code is Code.STALE
        refreshed = service.headers(lease,budget())
        assert refreshed.headers[0].key != row.key
        assert v._read(a)['m6_mailbox_v1']['uidvalidity'] == server.validity
        assert 'CLOSE' not in server.events and 'EXPUNGE' not in server.events


def test_two_accounts_same_uid_no_cross_account_cache(setup,tmp_path):
    v,a,ak,b,bk,access,lease,native = setup
    messages = {'alice@example.invalid':{9:dict(raw=RAW,seen=False)},
                'bob@example.invalid':{9:dict(raw=RAW.replace(b'fixture',b'bob-only'),seen=True)}}
    with Server(tmp_path/'tls',messages) as server:
        service = MailboxService(v,access,None,GmailMailbox(server.factory),native)
        first = service.headers(lease,budget()).headers[0]
        other = access.select(b)
        second = service.headers(other,budget()).headers[0]
        assert first.key != second.key and first.key.uid == second.key.uid
        with pytest.raises(Failure): service.open(other,first.key,bk,None,budget())
        assert v._read(a)['m6_mailbox_v1']['rows'][0]['subject'] == 'fixture'
        assert v._read(b)['m6_mailbox_v1']['rows'][0]['subject'] == 'bob-only'
        assert b'bob-only' not in v.path.read_bytes()


def test_real_m5_protected_message_through_imap(setup,tmp_path):
    v,a,ak,b,bk,access,lease,native = setup
    pin(v,a,EmailAddress('bob@example.invalid'),v.export_public(b,bk))
    pin(v,b,EmailAddress('alice@example.invalid'),v.export_public(a,ak))
    compose = Compose(v,access,native)
    draft = Draft(('bob@example.invalid',),(),'protected fixture','Authenticated body')
    operation = compose.draft(lease,draft,budget())
    envelope = compose.prepare(lease,operation,ak,budget())
    local = access.select(b)
    messages = {'bob@example.invalid':{12:dict(raw=envelope.serialized,seen=False)}}
    with Server(tmp_path/'tls',messages) as server:
        service = MailboxService(v,access,None,GmailMailbox(server.factory),native)
        row = service.headers(local,budget()).headers[0]
        assert row.subject == 'Encrypted message'
        automatic = service.open(local,row.key,bk,None,budget())
        assert automatic.protected.signature_valid and automatic.protected.sender=='alice@example.invalid'
        result = service.open(local,row.key,bk,'alice@example.invalid',budget())
        assert result.body == draft.body and 'independently_verified' in result.security
        assert not messages['bob@example.invalid'][12]['seen']
        messages['bob@example.invalid'][12]['raw'] = envelope.serialized[:-100]
        with pytest.raises(Exception): service.open(local,row.key,bk,'alice@example.invalid',budget())
        print('Real M5 verify via TLS IMAP; no implicit Seen; malformed modern message never falls back.')


@pytest.mark.parametrize('mode',['wrong-host','untrusted','expired'])
def test_tls_failure_before_auth(setup,tmp_path,mode):
    _,a,_,_,_,_,_,_ = setup
    with Server(tmp_path/'tls',{},mode) as server:
        with pytest.raises(Failure): GmailMailbox(server.factory).headers(Credential(a,'alice@example.invalid','synthetic-mail-token'),budget())
        assert 'AUTHENTICATE' not in server.events


def test_cancel_blocked_socket_no_cache(setup,tmp_path):
    v,a,ak,b,bk,access,lease,native = setup
    with Server(tmp_path/'tls',{'alice@example.invalid':{1:dict(raw=RAW,seen=False)}}) as server:
        server.pause = True
        service = MailboxService(v,access,None,GmailMailbox(server.factory),native)
        scope = budget()
        with ThreadPoolExecutor() as pool:
            future = pool.submit(service.headers,lease,scope)
            assert server.paused.wait(3)
            start = time.monotonic(); scope.cancel.set()
            with pytest.raises(Failure): future.result(timeout=2)
            assert time.monotonic()-start < 1
        assert 'm6_mailbox_v1' not in v._read(a)


def test_paging_and_deleted_uid(setup,tmp_path):
    _,a,_,_,_,_,_,_ = setup
    messages = {'alice@example.invalid':{i:dict(raw=RAW,seen=False) for i in range(1,36)}}
    with Server(tmp_path/'tls',messages) as server:
        mailbox = GmailMailbox(server.factory); credential = Credential(a,'alice@example.invalid','synthetic-mail-token')
        first = mailbox.headers(credential,budget()); second = mailbox.headers(credential,budget(),(first.uidvalidity,first.before))
        assert len(first.headers)==30 and len(second.headers)==5
        assert len({r.key.uid for r in first.headers+second.headers})==35
        del messages['alice@example.invalid'][35]
        with pytest.raises(Failure) as error: mailbox.fetch(credential,first.headers[0].key,budget())
        assert error.value.code is Code.MISSING


def test_literal_and_message_limits(setup,tmp_path):
    _,a,_,_,_,_,_,_ = setup
    bare = object.__new__(LimitedIMAP); bare.literal_limit=MAX_WIRE; bare.remaining=2*MAX_WIRE
    with pytest.raises(Failure): bare.read(MAX_WIRE+1)  # Before any file access/allocation.
    messages = {'alice@example.invalid':{1:dict(raw=RAW+b'x'*MAX_WIRE,seen=False)}}
    with Server(tmp_path/'tls',messages) as server:
        mailbox=GmailMailbox(server.factory); credential=Credential(a,'alice@example.invalid','synthetic-mail-token')
        page=mailbox.headers(credential,budget())
        with pytest.raises(Failure) as error: mailbox.fetch(credential,page.headers[0].key,budget())
        assert error.value.code is Code.LIMIT


def test_scope_gate_and_cancelled_refresh(setup):
    v,a,ak,b,bk,access,lease,native=setup
    with v.transaction(a) as data: data['oauth']['scopes']=['openid']
    with pytest.raises(Failure): Credentials(v,access,None).resolve(lease,budget())
    with v.transaction(a) as data:
        data['oauth']['scopes']=[MAIL_SCOPE]; data['oauth']['expiry']=1
    class Google:
        scopes=(MAIL_SCOPE,)
        def refresh(self,*args):
            access.select(b)
            from transport.development_google import Authorization
            return Authorization(synthetic_identity(),dict(access_token='must-not-install',expiry=2000000000,scopes=[MAIL_SCOPE]))
    with pytest.raises(Exception): Credentials(v,access,Google()).resolve(lease,budget())
    assert v.oauth(a)['access_token']=='synthetic-mail-token'
    assert v.oauth(b)['access_token']=='synthetic-mail-token'


@pytest.mark.parametrize('raw,expected',[
    (b'Content-Type: text/html\r\n\r\n<img src="https://example.invalid/tracker"><script>alert(1)</script>', 'No plain-text'),
    (b'Subject: <b>untrusted</b>\r\nContent-Type: text/plain\r\n\r\n<script>literal text</script>', '<script>literal'),
])
def test_plain_text_only(setup,raw,expected):
    _,a,_,_,_,_,_,_=setup
    message=conventional(raw,MessageKey(a,'INBOX',1,1),False)
    assert expected in message.body and 'not cryptographically verified' in message.security


@pytest.mark.parametrize('change',['account','selection','cancel','lock'])
def test_ui_late_worker_never_displays_other_selection(setup,qapp,change):
    from ui.mailbox_window import MailboxWindow
    v,a,ak,b,bk,access,lease,native=setup
    identity=IdentityService(v.path,v.provider,v.store); identity.unlock(); identity.reload(a)
    entered=threading.Event(); release=threading.Event()
    class Slow:
        def headers(self,*args):
            entered.set(); release.wait(3)
            return Page(17,(Header(MessageKey(a,'INBOX',17,1),'a','must not display','',1,False),),None)
    window=MailboxWindow(identity,lambda:Slow())
    try:
        window.start('headers'); assert entered.wait(2)
        if change=='account': identity.select(b.account)
        elif change=='selection': window.selection_changed()
        elif change=='lock': identity.lock()
        else: window.cancel()
        release.set(); end=time.monotonic()+3
        while window.pending and time.monotonic()<end: qapp.processEvents(); window.poll(); time.sleep(.01)
        assert not window.pending and not window.rows and not window.content.toPlainText()
    finally:
        release.set(); window.close(); window.pool.shutdown(wait=True)


def test_mailbox_entry_point_is_opt_in(monkeypatch):
    import main
    calls=[]
    monkeypatch.setattr(main,'_launch_mailbox',lambda *a:calls.append(a) or 0)
    main.main(['--dev-mailbox','--dev-vault','explicit.sqlite'])
    assert calls==[('explicit.sqlite',None)]
    with pytest.raises(SystemExit): main.main(['--dev-mailbox','--dev-simulator','--dev-vault','explicit.sqlite'])


def test_ui_header_first_plain_display_explicit_flags(setup,qapp):
    from ui.mailbox_window import MailboxWindow
    v,a,ak,b,bk,access,lease,native=setup
    identity=IdentityService(v.path,v.provider,v.store); identity.unlock(); identity.reload(a)
    key=MessageKey(a,'INBOX',17,1); calls=[]
    class Controlled:
        def headers(self,*args):
            calls.append('headers')
            return Page(17,(Header(key,'outer author','<b>outer subject</b>','',12,False),),None)
        def open(self,*args):
            calls.append('open'); return Display(key,'<b>plain subject</b>','<img src="https://example.invalid/no-fetch">','Unverified conventional',False)
        def set_seen(self,lease,key,seen,budget): calls.append(('flag',seen)); return seen
    window=MailboxWindow(identity,lambda:Controlled())
    def drain():
        end=time.monotonic()+3
        while window.pending and time.monotonic()<end: qapp.processEvents(); window.poll(); time.sleep(.01)
        assert not window.pending
    try:
        window.show(); qapp.processEvents()
        window.start('headers'); drain()
        assert calls==['headers'] and not window.content.toPlainText()
        window.table.selectRow(0); qapp.processEvents()
        assert calls==['headers']
        window.start('open'); drain()
        assert calls==['headers','open'] and '<img src=' in window.content.toPlainText()
        assert not window.rows[0].seen
        window.start('read'); drain(); assert window.rows[0].seen
        window.start('unread'); drain(); assert not window.rows[0].seen
        assert calls[-2:]==[('flag',True),('flag',False)]
    finally: window.close(); window.pool.shutdown(wait=True)


@pytest.mark.parametrize('granted',[True,False])
def test_synthetic_google_mail_scope_authorization(monkeypatch,granted):
    from transport import development_google as google
    from experiments.m3.tests.test_integration import CONFIG
    observed=[]
    class Listener:
        redirect='http://127.0.0.1:12345/'
        def __init__(self,state): pass
        def wait(self,cancel): return 'synthetic-code'
        def close(self): pass
    class Flow:
        code_verifier='synthetic-pkce'
        oauth2session=type('Session',(),{'close':lambda self:None})()
        @classmethod
        def from_client_config(cls,config,scopes,**kw):
            observed.extend(scopes); flow=cls(); flow.state=kw['state']; return flow
        def authorization_url(self,**kw): return 'https://example.invalid/synthetic',self.state
        def fetch_token(self,**kw):
            return dict(id_token='synthetic-id',access_token='synthetic-access',expires_at=2000000000,
                        scope=list(google.SCOPES)+([MAIL_SCOPE] if granted else []))
    monkeypatch.setattr(google,'Loopback',Listener); monkeypatch.setattr(google,'InstalledAppFlow',Flow)
    monkeypatch.setattr(google,'google_identity',lambda *a,**k:synthetic_identity())
    auth=google.GoogleAuthorization(CONFIG,google.SCOPES+(MAIL_SCOPE,))
    if granted:
        result=auth.authorize(threading.Event(),'alice@example.invalid',opener=lambda _:True)
        assert MAIL_SCOPE in result.tokens['scopes']
    else:
        with pytest.raises(BoundaryError): auth.authorize(threading.Event(),'alice@example.invalid',opener=lambda _:True)
    assert observed==list(google.SCOPES)+[MAIL_SCOPE]


def test_no_content_type_conventional_fetch_and_empty_inbox(setup,tmp_path):
    v,a,ak,b,bk,access,lease,native=setup
    messages={'alice@example.invalid':{1:dict(raw=b'Subject: plain default\r\n\r\nPlain body',seen=False)}}
    with Server(tmp_path/'tls',messages) as server:
        service=MailboxService(v,access,None,GmailMailbox(server.factory),native)
        row=service.headers(lease,budget()).headers[0]
        assert service.open(lease,row.key,ak,None,budget()).body=='Plain body'
        messages['alice@example.invalid'].clear()
        page=service.headers(lease,budget())
        assert not page.headers and page.before is None
