"""Windows-local usability and bounded connection evidence, not human approval."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import errno
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QPushButton
from .test_mailbox import setup,vault,provider,qapp,budget
from .test_workflows import prepared,drain
from core.identity_service import IdentityService
from experiments.m3.tests.test_integration import CONFIG
from experiments.m3.types import BoundaryError
from experiments.m5.model import Budget
from mailbox_client.gmail import LimitedIMAP
from mailbox_client.model import Header,MessageKey,Page
from mailbox_client import connection
from transport import bounded_worker,bounded_google
from ui.mailbox_window import MailboxWindow


def wait_for(predicate,seconds=5):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end: time.sleep(.01)
    assert predicate()


@pytest.mark.parametrize('mode',['dns','oauth'])
def test_real_worker_cancel_reaps_blocked_dns_or_refresh(tmp_path,monkeypatch,mode,setup):
    v,a,ak,b,bk,access,lease,native=setup
    marker=tmp_path/'worker-started.txt'; processes=[]
    original=subprocess.Popen
    def observe(*args,**kwargs):
        process=original(*args,**kwargs); processes.append(process); return process
    monkeypatch.setattr(bounded_worker.subprocess,'Popen',observe)
    command=[sys.executable,'-m','experiments.m6.blocking_worker',mode,str(marker)]
    cancel=threading.Event()
    with ThreadPoolExecutor(1) as pool:
        if mode=='dns':
            future=pool.submit(bounded_worker.call,dict(op='dns',host='imap.gmail.com',port=993),cancel,time.monotonic()+8,command=command)
        else:
            original_call=bounded_worker.call
            monkeypatch.setattr(bounded_google,'call',lambda request,cancel,deadline:original_call(request,cancel,deadline,command=command))
            google=bounded_google.BoundedGoogleAuthorization(CONFIG)
            future=pool.submit(google.refresh,cancel,a,'alice@example.invalid',v._read(a)['oauth'])
        wait_for(marker.exists)
        started=time.monotonic(); cancel.set()
        with pytest.raises((TimeoutError,BoundaryError)): future.result(timeout=2)
        assert time.monotonic()-started<1
    assert len(processes)==1 and processes[0].poll() is not None
    assert processes[0].stdin.closed and processes[0].stdout.closed
    assert 'synthetic-mail-token' not in repr(processes[0].args)
    assert not any(t.name in ('qumail-private-reader','qumail-private-writer') for t in threading.enumerate())
    print(mode,'controlled blocking worker cancelled/reaped under 1 second; no external connection.')


def test_dns_worker_wall_deadline_and_response_limit(tmp_path):
    marker=tmp_path/'deadline.txt'
    with pytest.raises(TimeoutError):
        bounded_worker.call(dict(op='dns',host='imap.gmail.com',port=993),threading.Event(),time.monotonic()+1,
            command=[sys.executable,'-m','experiments.m6.blocking_worker','dns',str(marker)])
    assert marker.exists()
    with pytest.raises(OSError):
        bounded_worker.call({},threading.Event(),time.monotonic()+3,
            command=[sys.executable,'-c','import sys; sys.stdin.read(); sys.stdout.write("x"*1100000)'])


def test_bounded_connect_cancels_pending_socket_and_closes(monkeypatch):
    closed=[]
    class Pending:
        def setblocking(self,value): pass
        def connect_ex(self,address): return errno.EINPROGRESS
        def close(self): closed.append(True)
    monkeypatch.setattr(connection.socket,'socket',lambda *a:Pending())
    monkeypatch.setattr(connection.select,'select',lambda *a:(time.sleep(.02) or ([],[],[])))
    bound=Budget(threading.Event(),time.monotonic()+.12)
    with pytest.raises(Exception): connection.connect('127.0.0.1',12345,bound)
    assert closed==[True]


@pytest.mark.parametrize('stage',['tls','greeting'])
def test_real_imap_setup_cancel_before_auth_closes_socket(tmp_path,stage):
    from experiments.m4.smtp_fixture import certificates
    server_context,client_context=certificates(tmp_path/'tls')
    listener=socket.socket(); listener.bind(('127.0.0.1',0)); listener.listen()
    entered=threading.Event(); release=threading.Event(); closed=threading.Event()
    def server():
        raw,_=listener.accept()
        try:
            sock=server_context.wrap_socket(raw,server_side=True) if stage=='greeting' else raw
            with sock:
                entered.set(); release.wait(3)
                sock.settimeout(1)
                while sock.recv(4096): pass
                closed.set()
        except OSError: closed.set()
    thread=threading.Thread(target=server); thread.start()
    bound=Budget(threading.Event(),time.monotonic()+8)
    try:
        with ThreadPoolExecutor(1) as pool:
            future=pool.submit(LimitedIMAP,'127.0.0.1',listener.getsockname()[1],ssl_context=client_context,timeout=8,budget=bound)
            assert entered.wait(3)
            started=time.monotonic(); bound.cancel.set()
            with pytest.raises(Exception): future.result(timeout=2)
            assert time.monotonic()-started<1
        release.set(); thread.join(3); assert closed.is_set() and not thread.is_alive()
    finally: release.set(); listener.close(); thread.join(3)
    print('Real IMAP',stage,'cancellation before AUTH; socket closed.')


def test_application_google_boundary_is_isolated():
    from core.identity_service import GoogleAuthorization
    assert GoogleAuthorization is bounded_google.BoundedGoogleAuthorization


def make_window(setup):
    v,a,ak,b,bk,access,lease,native=setup
    identity=IdentityService(v.path,v.provider,v.store); identity.unlock(); identity.reload(a)
    return MailboxWindow(identity)


def test_keyboard_names_focus_enter_escape_and_locked_states(prepared,qapp):
    setup,work,draft,op=prepared
    window=make_window(setup)
    try:
        window.show(); window.actions.show(); qapp.processEvents()
        actions=window.actions
        for widget in (window.accounts,window.table,window.content,window.signers,window.attachments,
                       actions.to,actions.cc,actions.subject,actions.body,actions.files,actions.table,window.settings.address):
            assert widget.accessibleName()
        assert all(b.accessibleName() and not b.autoDefault() for b in actions.findChildren(QPushButton))
        actions.install(draft); actions.to.setFocus(); qapp.processEvents()
        for expected in (actions.cc,actions.subject,actions.body,actions.archive):
            QTest.keyClick(qapp.focusWidget(),Qt.Key.Key_Tab); qapp.processEvents()
            assert qapp.focusWidget() is expected
        actions.subject.setFocus(); QTest.keyClick(actions.subject,Qt.Key.Key_Return)
        assert actions.body.toPlainText()==draft.body and not actions.pending
        assert not actions.buttons['Submit once'].isEnabled()
        QTest.keyClick(actions,Qt.Key.Key_Escape); qapp.processEvents()
        assert not actions.isVisible() and not actions.body.toPlainText() and window.display is None
        QTest.keyClick(window.buttons['Compose / outbox'],Qt.Key.Key_Space); qapp.processEvents()
        assert actions.isVisible()
        window.identity.lock(); window.update_controls()
        assert not window.buttons['Refresh headers'].isEnabled() and window.buttons['Settings'].isEnabled()
        assert not actions.to.isEnabled() and not actions.editor_buttons[-1].isEnabled()
    finally: window.close(); window.pool.shutdown(wait=True)


def test_busy_navigation_and_outbox_state_controls(prepared,qapp):
    setup,work,draft,op=prepared
    v,a,ak,b,bk,access,lease,native=setup
    window=make_window(setup); entered=threading.Event(); release=threading.Event()
    class Slow:
        def headers(self,*a): entered.set(); release.wait(3); return Page(17,(),None)
    window.service_factory=lambda:Slow()
    try:
        window.start('headers'); assert entered.wait(2)
        assert not window.buttons['Refresh headers'].isEnabled()
        assert window.buttons['Lock'].isEnabled() and window.buttons['Cancel'].isEnabled()
        release.set(); drain(window,qapp)
        window.actions.start('list')
        assert not window.actions.table.isEnabled()
        drain(window,qapp)
        work.prepare(lease,op,ak,budget())
        window.actions.rows=work.outbox(lease,budget()); window.actions.table.setRowCount(1); window.actions.table.selectRow(0)
        window.actions.update_controls()
        assert not window.actions.buttons['Edit draft'].isEnabled()
        assert window.actions.buttons['Open archive'].isEnabled()
        assert not window.actions.buttons['Submit once'].isEnabled()
        window.actions.rows=(replace(window.actions.rows[0],state=__import__('experiments.m4.model',fromlist=['State']).State.UNKNOWN),)
        window.actions.update_controls()
        assert window.actions.buttons['Explicit retry'].isEnabled()
        assert not window.actions.buttons['Discard / cancel saved'].isEnabled()
    finally: release.set(); window.close(); window.pool.shutdown(wait=True)


def test_settings_close_reopen_retains_executor_and_timer(setup,qapp):
    window=make_window(setup)
    settings=window.settings
    try:
        settings.show(); qapp.processEvents(); settings.close(); qapp.processEvents()
        assert settings.timer.isActive() and not settings.disposed
        window.identity.unlock(); settings.show(); qapp.processEvents()
        assert settings.pool.submit(lambda:True).result(timeout=1)
        assert settings.isVisible() and not window.identity.session.snapshot.locked
    finally: window.close(); window.pool.shutdown(wait=True)
    assert settings.disposed and not settings.timer.isActive()


def test_errors_give_remedy_without_private_diagnostics():
    from ui.mail_accessibility import error_message
    from mailbox_client.model import Failure,Code
    for code in (Code.AUTH,Code.SIGNER,Code.TRANSPORT):
        message=error_message(Failure(code))
        assert 'Settings' in message or 'Check' in message or 'Inspect' in message
    assert 'private-token' not in error_message(ValueError('private-token'))

def test_worker_success_decodes_scoped_result_and_honors_outer_deadline(setup,monkeypatch):
    from mailbox_client.service import Credentials
    from mailbox_client.gmail import MAIL_SCOPE
    from transport.development_google import SCOPES
    v,a,ak,b,bk,access,lease,native=setup
    with v.transaction(a) as data: data['oauth']['expiry']=1
    original=bounded_worker.call
    command=[sys.executable,'-c', '''
import runpy,time
from transport.development_google import GoogleAuthorization,Authorization
from experiments.m3.types import VerifiedProviderIdentity,EmailAddress
def refresh(self,cancel,context,address,tokens):
    expiry=int(time.time())+3600
    identity=VerifiedProviderIdentity(context.issuer,context.subject,(EmailAddress(address),),expiry,'synthetic worker identity')
    return Authorization(identity,dict(access_token='synthetic-worker-result',refresh_token='synthetic-refresh',expiry=expiry,scopes=list(self.scopes)))
GoogleAuthorization.refresh=refresh
runpy.run_module('transport.network_worker',run_name='__main__')
''']
    observed=[]
    def dispatch(request,cancel,deadline):
        observed.append(deadline)
        return original(request,cancel,deadline,command=command)
    monkeypatch.setattr(bounded_google,'call',dispatch)
    google=bounded_google.BoundedGoogleAuthorization(CONFIG,SCOPES+(MAIL_SCOPE,))
    bound=Budget(threading.Event(),time.monotonic()+6)
    result=Credentials(v,access,google).resolve(lease,bound)
    assert observed==[bound.deadline] and result.context==a and result.token=='synthetic-worker-result'
    assert v.oauth(a)['access_token']=='synthetic-worker-result'
    assert v.oauth(b)['access_token']=='synthetic-mail-token'


def test_window_shutdown_cancels_real_refresh_worker_without_install(setup,qapp,tmp_path,monkeypatch):
    from transport.development_google import SCOPES
    from mailbox_client.gmail import MAIL_SCOPE
    v,a,ak,b,bk,access,lease,native=setup
    with v.transaction(a) as data: data['oauth']['expiry']=1
    marker=tmp_path/'closing-worker.txt'; original=bounded_worker.call
    command=[sys.executable,'-m','experiments.m6.blocking_worker','oauth',str(marker)]
    monkeypatch.setattr(bounded_google,'call',lambda request,cancel,deadline:original(request,cancel,deadline,command=command))
    window=make_window(setup)
    window.identity.google=bounded_google.BoundedGoogleAuthorization(CONFIG,SCOPES+(MAIL_SCOPE,))
    try:
        window.start('headers'); wait_for(marker.exists)
        started=time.monotonic(); window.close(); qapp.processEvents()
        assert time.monotonic()-started<1 and not window.content.toPlainText()
        window.pool.shutdown(wait=True)
        assert time.monotonic()-started<1
        assert v.oauth(a)['access_token']=='synthetic-mail-token'
        assert not any(t.name in ('qumail-private-reader','qumail-private-writer') for t in threading.enumerate())
    finally: window.close(); window.pool.shutdown(wait=True)
