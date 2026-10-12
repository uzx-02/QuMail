"""Real loopback sockets/TLS; disposable roots and synthetic credentials only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import pytest
from experiments.m3.tests.test_m3 import provider, vault, enroll, pin, synthetic_identity
from experiments.m3.types import EmailAddress, BoundaryError
from experiments.m3.vault import Vault, PROFILE
from experiments.m4.model import *
from experiments.m4.services import PrepareMessage, SubmitOutbox
from experiments.m4.vault_adapter import VaultOutbox
from experiments.m4.smtp_transport import LoopbackSMTP, VaultMailCredentials, BoundedSMTP
from experiments.m4.smtp_fixture import SMTPServer, SyntheticResolver, SMTPFixtureBuilder
from experiments.m4.tests.test_outbox import deny_commit


@pytest.fixture
def case(vault):
    a, ak = enroll(vault); b, bk = enroll(vault,'bob')
    address=EmailAddress('bob@example.invalid'); pin(vault,a,address,vault.export_public(b,bk))
    access=AccountAccess(); lease=access.select(a); repo=VaultOutbox(vault,access)
    prepare=PrepareMessage(repo,SMTPFixtureBuilder()); op=prepare.draft(lease,b'disposable TLS fixture')
    envelope=prepare.prepare(lease,op,ak,(address,),PROFILE)
    return vault,a,ak,b,bk,access,lease,repo,op,envelope


def transport(server,context):
    resolver=SyntheticResolver(context)
    return LoopbackSMTP('127.0.0.1',server.port,resolver,fixture_context=server.client_context),resolver


@pytest.mark.parametrize('mode,cert,expected',[
    ('success','valid',State.ACCEPTED),('close-after-accept','valid',State.ACCEPTED),
    ('missing-starttls','valid',State.FAILED),('tls-reject','valid',State.FAILED),
    ('success','untrusted',State.FAILED),('success','expired',State.FAILED),('success','wrong-host',State.FAILED),
    ('auth-reject','valid',State.FAILED),('recipient-reject','valid',State.FAILED),
    ('data-reject','valid',State.FAILED),('final-reject','valid',State.FAILED),
    ('disconnect-data','valid',State.UNKNOWN),('final-loss','valid',State.UNKNOWN),('oversized','valid',State.FAILED),
])
def test_socket_tls_observed_outcomes(case,tmp_path,mode,cert,expected):
    v,a,ak,b,bk,access,lease,repo,op,envelope=case
    with SMTPServer(tmp_path/'certs',mode,cert) as server:
        adapter,resolver=transport(server,a)
        got=SubmitOutbox(repo,adapter).submit(lease,op)
        assert got.state is expected
        tls_failed=cert!='valid' or mode in ('missing-starttls','tls-reject','oversized')
        if tls_failed:
            assert resolver.calls==0 and not any(e.startswith('AUTH') for e in server.events)
        else:
            assert resolver.calls==1
            assert server.events.index('EHLO-TLS') < server.events.index('AUTH-TLS')
            assert 'AUTH-CLEAR' not in server.events
        if server.digests: assert server.digests==[envelope.digest]
        print('SOCKET_OBSERVATION',json.dumps(dict(case=mode,certificate=cert,result=got.state.value,
            resolved=resolver.calls,auth=sum(e.startswith('AUTH') for e in server.events),
            data_payloads=len(server.digests),persisted_bytes_match=all(x==envelope.digest for x in server.digests))))


@pytest.mark.parametrize('stage',['greeting','ehlo','tls','ehlo-tls','auth','mail','rcpt','data','final'])
@pytest.mark.parametrize('stop',['timeout','cancel'])
def test_real_stage_deadline_and_cancellation(case,tmp_path,stage,stop):
    v,a,ak,b,bk,access,lease,repo,op,envelope=case
    with SMTPServer(tmp_path/'certs','stall-'+stage) as server:
        adapter,resolver=transport(server,a); submit=SubmitOutbox(repo,adapter)
        start=time.monotonic()
        with ThreadPoolExecutor() as pool:
            future=pool.submit(submit.submit,lease,op,until=start+(1.2 if stop=='timeout' else 10))
            assert server.paused.wait(3)
            if stop=='cancel': lease.cancelled.set()
            result=future.result(timeout=3)
        assert time.monotonic()-start<3
        assert result.state is (State.UNKNOWN if stage=='final' else State.FAILED)
        if stage in ('greeting','ehlo','tls','ehlo-tls'): assert resolver.calls==0
        server.release.set()


def test_all_recipients_required_and_smtp_dot_framing(case,tmp_path):
    *_,lease,repo,op,envelope=case
    # Direct immutable protocol fixture: multiple recipient-set framing; M5 remains absent.
    binding=replace(envelope.binding,recipients=(EmailAddress('one@example.invalid'),EmailAddress('two@example.invalid')))
    payload=b'From: fixture@example.invalid\r\n\r\n.dot\r\n..two\r\n'
    e=replace(envelope,binding=binding,serialized=payload,digest=hashlib.sha256(payload).hexdigest())
    for mode in ('second-recipient-reject','success'):
        with SMTPServer(tmp_path/mode,mode) as server:
            adapter,resolver=transport(server,e.account)
            got=adapter.submit(e,CredentialHandle(e.account),threading.Event(),time.monotonic()+4)
            if mode=='success': assert got is Outcome.ACCEPTED and server.digests==[e.digest]
            else: assert got is Outcome.REJECTED and not any(x.startswith('DATA') for x in server.events)


def test_real_retry_exact_bytes_and_result_commit_failure(case,tmp_path):
    v,a,ak,b,bk,access,lease,repo,op,envelope=case
    with SMTPServer(tmp_path/'certs') as server:
        adapter,_=transport(server,a); submit=SubmitOutbox(repo,adapter)
        with deny_commit(v,2): assert submit.submit(lease,op).state is State.UNKNOWN
        assert server.digests==[envelope.digest]
        assert submit.recover(lease)==(op,)
        assert len(server.digests)==1
        with pytest.raises(Failure): submit.retry(lease,op)
        submit.retry(lease,op,acknowledge_duplicate_risk=True)
        assert submit.submit(lease,op).state is State.ACCEPTED
        assert server.digests==[envelope.digest,envelope.digest]


def test_tls_before_vault_mail_scope_resolution(case,tmp_path):
    v,a,ak,b,bk,access,lease,repo,op,envelope=case
    v.store_oauth(a,synthetic_identity(),dict(access_token='synthetic-only',expiry=time.time()+60,scopes=['openid']))
    with SMTPServer(tmp_path/'certs') as server:
        adapter=LoopbackSMTP('127.0.0.1',server.port,VaultMailCredentials(v),fixture_context=server.client_context)
        assert SubmitOutbox(repo,adapter).submit(lease,op).state is State.FAILED
        assert 'EHLO-TLS' in server.events and not any(e.startswith('AUTH') for e in server.events)


def test_scope_account_and_destination_guards(case,tmp_path):
    v,a,ak,b,bk,access,lease,repo,op,envelope=case
    for host in ['192.0.2.1','smtp.example.invalid','::1']:
        with pytest.raises((Failure,ValueError)): LoopbackSMTP(host,25,SyntheticResolver(a))
    import ssl
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); context.check_hostname=False
    with pytest.raises(Failure): LoopbackSMTP('127.0.0.1',25,SyntheticResolver(a),fixture_context=context)
    with SMTPServer(tmp_path/'certs') as server:
        adapter,resolver=transport(server,b)
        assert SubmitOutbox(repo,adapter).submit(lease,op).state is State.FAILED
        assert resolver.calls==0 and not any(e.startswith('AUTH') for e in server.events)


def test_accepted_survives_cleanup_exception(case,tmp_path,monkeypatch):
    *_,lease,repo,op,envelope=case
    original=BoundedSMTP.close
    def close(smtp): original(smtp); raise OSError('injected cleanup exception')
    monkeypatch.setattr(BoundedSMTP,'close',close)
    with SMTPServer(tmp_path/'certs') as server:
        adapter,_=transport(server,envelope.account)
        assert SubmitOutbox(repo,adapter).submit(lease,op).state is State.ACCEPTED


def test_deterministic_vault_creation_and_exception_close(tmp_path,provider,monkeypatch):
    from experiments.m3.secure_store import WindowsCredentialStore
    import experiments.m3.vault as module
    connections=[]; fail=[False]; original=sqlite3.connect
    class Tracked(sqlite3.Connection):
        def executescript(self,*args):
            if fail[0]: raise sqlite3.OperationalError('controlled initialization failure')
            return super().executescript(*args)
    def connect(*args,**kwargs):
        connection=original(*args,**kwargs,factory=Tracked); connections.append(connection); return connection
    monkeypatch.setattr(module.sqlite3,'connect',connect)
    store=WindowsCredentialStore(); vault=Vault.create(tmp_path/'good.sqlite',store,provider)
    try:
        for c in connections:
            with pytest.raises(sqlite3.ProgrammingError): c.execute('SELECT 1')
        (tmp_path/'good.sqlite').rename(tmp_path/'closed.sqlite')  # No gc.collect.
        fail[0]=True
        with pytest.raises(sqlite3.OperationalError): Vault.create(tmp_path/'bad.sqlite',store,provider)
        for c in connections:
            with pytest.raises(sqlite3.ProgrammingError): c.execute('SELECT 1')
        (tmp_path/'bad.sqlite').rename(tmp_path/'failed-closed.sqlite')
    finally: store.delete(vault.ident)


@pytest.mark.parametrize('pause',['network','result-commit'])
def test_real_process_ownership_network_unlock_and_kill(case,tmp_path,pause):
    v,a,ak,b,bk,access,lease,repo,op,envelope=case
    marker=tmp_path/'boundary.txt'
    with SMTPServer(tmp_path/'certs','stall-final' if pause=='network' else 'success') as server:
        request=dict(path=str(v.path),account=a.account.value,device=a.device.value,issuer=a.issuer,
            subject=a.subject,key=ak.value,recipient=envelope.binding.recipients[0].value,operation=op.value,
            mode='smtp',point='none' if pause=='network' else '2-before',marker=str(marker),
            ca=str(tmp_path/'certs'/'ca.pem'),port=server.port)
        command=[sys.executable,'-m','experiments.m4.tests.crash_worker']
        child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            child.stdin.write(json.dumps(request).encode()); child.stdin.close()
            assert server.accepted.wait(5)
            if pause=='network':
                # The server has the real DATA payload; caller is waiting on response.
                # Another account/vault mutation must succeed while I/O is in flight.
                with v.transaction(a) as data: data['events'].append('concurrent_local_event')
                with v.transaction(b) as data: data['events'].append('other_account_event')
                probe=subprocess.run(command,input=json.dumps(dict(request,mode='probe')),capture_output=True,text=True,timeout=8)
                assert probe.returncode==0
                assert json.loads(probe.stdout)==dict(recovered=0,busy=True)
                assert len(server.digests)==1
            else:
                until=time.monotonic()+5
                while not marker.exists() and time.monotonic()<until: time.sleep(.02)
                assert marker.exists()
            child.kill(); child.wait(timeout=5)
        finally:
            if child.poll() is None: child.kill(); child.wait(timeout=5)
            server.release.set()
        adapter,_=transport(server,a); submit=SubmitOutbox(repo,adapter)
        assert submit.recover(lease)==(op,)
        assert submit.inspect(lease,op).state is State.UNKNOWN
        assert server.digests==[envelope.digest]
        assert submit.envelope(lease,op)==envelope
        print('PROCESS_SOCKET_OBSERVATION',pause,'payload matched; recovery Unknown; no automatic resend')
