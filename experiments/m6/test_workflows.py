"""Real provider/secure-store/TLS tests; synthetic identities, no Google contact."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import socket
import threading
import time
import pytest
from .test_mailbox import setup, vault, provider, qapp, budget, RAW
from experiments.m3.tests.test_m3 import pin
from experiments.m3.types import EmailAddress
from experiments.m4.model import State, Failure, Error, AccountAccess
from experiments.m4.smtp_fixture import SMTPServer
from experiments.m4.smtp_transport import LoopbackSMTP
from experiments.m4.services import SubmitOutbox
from experiments.m5.model import Draft, Attachment, Budget
from mailbox_client.model import Display, MessageKey
from mailbox_client.workflows import Workflows, import_attachment
from mailbox_client.smtp import GmailSMTP
from mailbox_client.service import conventional


@pytest.fixture
def prepared(setup):
    v,a,ak,b,bk,access,lease,native=setup
    pin(v,a,EmailAddress('bob@example.invalid'),v.export_public(b,bk))
    pin(v,b,EmailAddress('alice@example.invalid'),v.export_public(a,ak))
    work=Workflows(v,access,native)
    draft=Draft(('bob@example.invalid',),(),'Workflow fixture','Private workflow text',
                (Attachment('note.txt','text/plain',b'private attachment'),))
    operation=work.save(lease,draft,budget())
    return setup,work,draft,operation


def local_transport(server):
    return lambda resolver:LoopbackSMTP('127.0.0.1',server.port,resolver,fixture_context=server.client_context)


def test_real_compose_outbox_archive_and_recipient_open(prepared,tmp_path):
    (v,a,ak,b,bk,access,lease,native),work,draft,op=prepared
    assert work.load(lease,op,budget())==draft
    edited=replace(draft,subject='Saved edit')
    assert work.save(lease,edited,budget(),op)==op
    assert 'Every recipient' in work.recipients(lease,edited,budget())
    envelope=work.prepare(lease,op,ak,budget())
    with pytest.raises(Failure): work.save(lease,draft,budget(),op)
    assert work.outbox(lease,budget())[0].state is State.PREPARED
    with SMTPServer(tmp_path/'smtp') as server:
        work.transport_factory=local_transport(server)
        delivery=work.submit(lease,op,budget())
        assert delivery.state is State.ACCEPTED and server.digests==[envelope.digest]
        assert 'AUTH-TLS' in server.events and 'AUTH-CLEAR' not in server.events
    archive=work.archive(lease,op,budget())
    assert archive.protected.archive and archive.body==draft.body and archive.protected.attachments==draft.attachments
    out=tmp_path/'saved.txt'
    work.export(lease,archive,0,out,budget())
    assert out.read_bytes()==draft.attachments[0].data
    local=access.select(b)
    opened=work.opener.open(local,bk,envelope.serialized,v.export_public(a,ak),budget())
    assert opened.signature_valid and opened.verified_confidential and not opened.archive
    assert b'Private workflow text' not in v.path.read_bytes()
    assert b'private attachment' not in v.path.read_bytes()
    with pytest.raises(Failure): work.outbox(lease,budget())
    assert work.outbox(local,budget())==()
    print('Real M5 cryptography + account vault + local STARTTLS: frozen digest Accepted; sender archive and recipient verified.')


def test_unknown_retry_retains_bytes_and_requires_ack(prepared,tmp_path):
    (v,a,ak,b,bk,access,lease,native),work,draft,op=prepared
    envelope=work.prepare(lease,op,ak,budget())
    with SMTPServer(tmp_path/'loss',mode='final-loss') as server:
        work.transport_factory=local_transport(server)
        assert work.submit(lease,op,budget()).state is State.UNKNOWN
        assert server.digests==[envelope.digest]
    with pytest.raises(Failure): work.retry(lease,op,budget())
    work.retry(lease,op,budget(),True)
    assert work.offline.envelope(lease,op).serialized==envelope.serialized
    with SMTPServer(tmp_path/'retry') as server:
        work.transport_factory=local_transport(server)
        assert work.submit(lease,op,budget()).state is State.ACCEPTED
        assert server.digests==[envelope.digest]
    with pytest.raises(Failure): work.retry(lease,op,budget(),True)


def test_disabled_submission_and_changed_recipient_block(prepared):
    (v,a,ak,b,bk,access,lease,native),work,draft,op=prepared
    work.prepare(lease,op,ak,budget())
    with pytest.raises(Failure): work.submit(lease,op,budget())
    assert work.outbox(lease,budget())[0].attempt==0
    work.cancel_saved(lease,op,budget())
    with v.transaction(a) as data: data['contacts']['bob@example.invalid']['state']='changed_blocked'
    with pytest.raises(Exception): work.retry(lease,op,budget())
    with pytest.raises(Exception): work.recipients(lease,draft,budget())
    new=work.save(lease,draft,budget())
    with pytest.raises(Exception): work.prepare(lease,new,ak,budget())
    assert next(row for row in work.outbox(lease,budget()) if row.operation==new).state is State.DRAFT


def test_cancel_saved_draft_and_interrupted_intent(prepared):
    (v,a,ak,b,bk,access,lease,native),work,draft,op=prepared
    work.cancel_saved(lease,op,budget()); assert work.outbox(lease,budget())==()
    op=work.save(lease,draft,budget()); work.prepare(lease,op,ak,budget())
    # Synthetic crash-state injection tests recovery, not a real process crash.
    with work.repository.transaction(lease,budget().deadline) as account:
        row=account.row(op); row['state']='Submitting'
        row['attempts'].append(dict(state='Submitting',identity='synthetic-intent'))
    assert work.outbox(lease,budget())[0].state is State.UNKNOWN
    with pytest.raises(Failure): work.retry(lease,op,budget())


@pytest.mark.parametrize('change',['cancel','account','lock'])
def test_cancel_or_switch_during_real_submission(prepared,tmp_path,change):
    (v,a,ak,b,bk,access,lease,native),work,draft,op=prepared
    work.prepare(lease,op,ak,budget())
    with SMTPServer(tmp_path/'stall',mode='stall-final') as server, ThreadPoolExecutor(1) as pool:
        work.transport_factory=local_transport(server); bound=budget()
        future=pool.submit(work.submit,lease,op,bound)
        assert server.paused.wait(5)
        start=time.monotonic()
        if change=='cancel': bound.cancel.set()
        else: access.select(b if change=='account' else None)
        observed=future.result(timeout=2)
        assert time.monotonic()-start<1 and observed.state is State.UNKNOWN
        server.release.set()
    current=access.select(a)
    assert work.outbox(current,budget())[0].state is State.UNKNOWN
    assert not v._read(b).get('m4_outbox_v1')


@pytest.mark.parametrize('name',['../escape.txt','file:stream','CON.txt','folder./bad','trailing.'])
def test_attachment_unsafe_export_paths(prepared,tmp_path,name):
    (v,a,ak,b,bk,access,lease,native),work,draft,op=prepared
    work.prepare(lease,op,ak,budget()); archive=work.archive(lease,op,budget())
    with pytest.raises(Exception): work.export(lease,archive,0,tmp_path/name,budget())


def test_attachment_limits_no_clobber_and_unverified_rejection(prepared,tmp_path):
    (v,a,ak,b,bk,access,lease,native),work,draft,op=prepared
    huge=tmp_path/'huge.txt'; huge.write_bytes(b'x'*16385)
    with pytest.raises(Exception): import_attachment(huge)
    small=tmp_path/'small.txt'; small.write_bytes(b'x'*4097)
    attachment=import_attachment(small)
    with pytest.raises(Exception): work.save(lease,replace(draft,attachments=(attachment,)*4),budget())
    work.prepare(lease,op,ak,budget()); archive=work.archive(lease,op,budget())
    target=tmp_path/'existing.txt'; target.write_bytes(b'keep')
    with pytest.raises(Exception): work.export(lease,archive,0,target,budget())
    assert target.read_bytes()==b'keep'
    unverified=conventional(RAW,MessageKey(a,'INBOX',1,1),False)
    with pytest.raises(Failure): work.export(lease,unverified,0,tmp_path/'no.txt',budget())
    access.select(b)
    with pytest.raises(Failure): work.export(lease,archive,0,tmp_path/'no.txt',budget())


def test_reply_forward_policy_and_authenticated_thread(prepared):
    (v,a,ak,b,bk,access,lease,native),work,draft,op=prepared
    envelope=work.prepare(lease,op,ak,budget())
    local=access.select(b)
    opened=work.opener.open(local,bk,envelope.serialized,v.export_public(a,ak),budget())
    display=Display(MessageKey(b,'INBOX',17,10),opened.subject,opened.body,'signature valid',False,opened)
    reply=work.derive(local,display,budget())
    assert reply.to==('alice@example.invalid',) and reply.in_reply_to==opened.message_id
    assert reply.references==(opened.message_id,) and display.thread==opened.message_id
    replyop=work.save(local,reply,budget())
    newenv=work.prepare(local,replyop,bk,budget())
    sender=access.select(a)
    verified=work.opener.open(sender,ak,newenv.serialized,v.export_public(b,bk),budget())
    assert verified.in_reply_to==opened.message_id and verified.signature_valid
    local=access.select(b)
    with pytest.raises(Failure): work.derive(local,display,budget(),forward=True)
    forwarded=work.derive(local,display,budget(),forward=True,recipients=('alice@example.invalid',),confirmed=True)
    assert not forwarded.references and not forwarded.in_reply_to
    assert forwarded.attachments==draft.attachments and 'did not endorse' in forwarded.body
    fop=work.save(local,forwarded,budget()); work.prepare(local,fop,bk,budget())
    bad=replace(display,protected=replace(opened,identity_trust='changed_blocked'))
    assert not bad.thread
    with pytest.raises(Failure): work.derive(local,bad,budget())
    plain=conventional(RAW+b'\r\n',MessageKey(b,'INBOX',17,11),False)
    assert not plain.thread
    with pytest.raises(Failure): work.derive(local,plain,budget())
    confirmed=work.derive(local,plain,budget(),recipients=('alice@example.invalid',),confirmed=True)
    assert 'unverified' in confirmed.body and not confirmed.references
    with v.transaction(b) as data: data['contacts']['alice@example.invalid']['state']='changed_blocked'
    cop=work.save(local,confirmed,budget())
    with pytest.raises(Exception): work.prepare(local,cop,bk,budget())


@pytest.mark.parametrize('mode,cert,state',[
    ('success','valid',State.ACCEPTED),('final-loss','valid',State.UNKNOWN),
    ('auth-challenge','valid',State.FAILED),('missing-starttls','valid',State.FAILED),
    ('recipient-reject','valid',State.FAILED),('success','wrong-host',State.FAILED),
    ('success','expired',State.FAILED),('success','untrusted',State.FAILED)])
def test_gmail_adapter_actual_tls_protocol_no_external_connection(prepared,tmp_path,monkeypatch,mode,cert,state):
    (v,a,ak,b,bk,access,lease,native),work,draft,op=prepared
    envelope=work.prepare(lease,op,ak,budget())
    original=socket.create_connection; destinations=[]
    with SMTPServer(tmp_path/'gmail',mode=mode,cert_mode=cert,dns_name='smtp.gmail.com') as server:
        def connect(address,timeout):
            assert address==('smtp.gmail.com',587)
            destinations.append(address)
            return original(('127.0.0.1',server.port),timeout)
        monkeypatch.setattr(socket,'create_connection',connect)
        def factory(resolver):
            transport=GmailSMTP(resolver)
            assert transport.context.check_hostname
            transport.context=server.client_context  # Disposable CA; hostname validation stays enabled.
            return transport
        work.transport_factory=factory
        assert work.submit(lease,op,budget()).state is state
        assert destinations==[('smtp.gmail.com',587)]
        if state in (State.ACCEPTED,State.UNKNOWN): assert server.digests==[envelope.digest]
        if cert!='valid' or mode=='missing-starttls': assert 'AUTH-TLS' not in server.events
        if mode=='auth-challenge': assert 'EMPTY-CHALLENGE' in server.events and 'MAIL-TLS' not in server.events
    print('Gmail adapter protocol fixture:',mode,cert,state.value,'; socket redirected to loopback, not Google.')


def test_gmail_identity_scope_and_external_opt_in_gate(prepared,tmp_path):
    (v,a,ak,b,bk,access,lease,native),work,draft,op=prepared
    with pytest.raises(Failure): SubmitOutbox(work.repository,GmailSMTP(None))
    with pytest.raises(Failure): LoopbackSMTP('8.8.8.8',587,None)
    work.prepare(lease,op,ak,budget())
    with v.transaction(a) as data: data['oauth']['scopes']=['openid','email']
    with SMTPServer(tmp_path/'scope') as server:
        work.transport_factory=local_transport(server)
        assert work.submit(lease,op,budget()).state is State.FAILED
        assert 'AUTH-TLS' not in server.events and 'MAIL-TLS' not in server.events


def drain(window,qapp):
    end=time.monotonic()+10
    while (window.pending or window.actions.pending) and time.monotonic()<end:
        qapp.processEvents(); window.poll(); window.actions.poll(); time.sleep(.01)
    assert not window.pending and not window.actions.pending


def test_integrated_ui_compose_archive_clear_account_boundary(prepared,qapp):
    from core.identity_service import IdentityService
    from ui.mailbox_window import MailboxWindow
    (v,a,ak,b,bk,access,lease,native),work,draft,op=prepared
    identity=IdentityService(v.path,v.provider,v.store); identity.unlock(); identity.reload(a)
    window=MailboxWindow(identity)
    try:
        window.actions.install(draft)
        window.actions.start('save'); drain(window,qapp)
        saved=window.actions.operation; assert saved
        window.actions.start('list'); drain(window,qapp)
        window.actions.table.selectRow(next(i for i,row in enumerate(window.actions.rows) if row.operation==saved))
        window.actions.start('prepare'); drain(window,qapp)
        assert 'durably frozen' in window.actions.status.text()
        window.actions.start('archive'); drain(window,qapp)
        assert window.display.protected.archive and window.attachments.count()==1
        identity.select(b.account)
        assert not window.content.toPlainText() and window.display is None
        assert not window.actions.body.toPlainText() and not window.actions.rows
        window.actions.start('list'); drain(window,qapp); assert not window.actions.rows
    finally: window.close(); window.pool.shutdown(wait=True)


@pytest.mark.parametrize('change',['account','cancel','lock'])
def test_late_composer_result_cannot_restore_plaintext(prepared,qapp,change):
    from core.identity_service import IdentityService
    from ui.mailbox_window import MailboxWindow
    (v,a,ak,b,bk,access,lease,native),work,draft,op=prepared
    identity=IdentityService(v.path,v.provider,v.store); identity.unlock(); identity.reload(a)
    entered=threading.Event(); release=threading.Event()
    class Delayed:
        def load(self,*args): entered.set(); release.wait(4); return draft
    window=MailboxWindow(identity,workflow_factory=lambda:Delayed())
    try:
        window.actions.rows=work.outbox(lease,budget())
        window.actions.table.setRowCount(1); window.actions.table.selectRow(0)
        window.actions.start('load'); assert entered.wait(2)
        if change=='account': identity.select(b.account)
        elif change=='lock': identity.lock()
        else: window.cancel()
        release.set(); drain(window,qapp)
        assert not window.actions.body.toPlainText() and not window.content.toPlainText()
    finally: release.set(); window.close(); window.pool.shutdown(wait=True)

def test_export_failure_cleanup_and_cancelled_budget(prepared,tmp_path,monkeypatch):
    import mailbox_client.workflows as module
    (v,a,ak,b,bk,access,lease,native),work,draft,op=prepared
    work.prepare(lease,op,ak,budget()); archive=work.archive(lease,op,budget())
    target=tmp_path/'failed-export.txt'
    def failed_sync(fd): raise OSError('controlled fsync failure')
    monkeypatch.setattr(module.os,'fsync',failed_sync)
    with pytest.raises(Failure): work.export(lease,archive,0,target,budget())
    assert not target.exists()
    cancelled=budget(); cancelled.cancel.set()
    with pytest.raises(Exception): work.export(lease,archive,0,target,cancelled)
    assert not target.exists()


def test_ui_submit_dispatch_uses_durable_protocol_and_explicit_confirmation(prepared,qapp,tmp_path,monkeypatch):
    from core.identity_service import IdentityService
    from ui.mailbox_window import MailboxWindow
    from PyQt6.QtWidgets import QMessageBox
    (v,a,ak,b,bk,access,lease,native),work,draft,op=prepared
    envelope=work.prepare(lease,op,ak,budget())
    identity=IdentityService(v.path,v.provider,v.store); identity.unlock(); identity.reload(a)
    decisions=[]
    with SMTPServer(tmp_path/'ui-submit') as server:
        window=MailboxWindow(identity)
        window.actions.factory=lambda:Workflows(v,window.access,native,transport_factory=local_transport(server))
        def confirm(*args): decisions.append(True); return QMessageBox.StandardButton.Yes
        monkeypatch.setattr(QMessageBox,'question',confirm)
        try:
            window.actions.start('list'); drain(window,qapp)
            window.actions.table.selectRow(0)
            window.actions.start('submit'); drain(window,qapp)
            assert len(decisions)==1 and 'Accepted:' in window.actions.status.text()
            assert server.digests==[envelope.digest]
            window.actions.start('list'); drain(window,qapp)
            assert window.actions.rows[0].state is State.ACCEPTED
            assert window.actions.rows[0].attempt==1
        finally: window.close(); window.pool.shutdown(wait=True)


def test_conventional_forward_cannot_assert_verified_thread(prepared):
    (v,a,ak,b,bk,access,lease,native),work,draft,op=prepared
    raw=RAW.replace(b'Content-Type:',b'References: <forged@example.invalid>\r\nIn-Reply-To: <forged@example.invalid>\r\nContent-Type:')
    display=conventional(raw,MessageKey(a,'INBOX',1,1),False)
    forwarded=work.derive(lease,display,budget(),forward=True,recipients=('bob@example.invalid',),confirmed=True)
    assert 'unverified' in forwarded.body and not forwarded.references and not display.thread
    assert not forwarded.in_reply_to and not forwarded.attachments

def test_ui_groups_only_verified_opened_references(prepared,qapp):
    from core.identity_service import IdentityService
    from ui.mailbox_window import MailboxWindow
    from mailbox_client.model import Header
    (v,a,ak,b,bk,access,lease,native),work,draft,op=prepared
    work.prepare(lease,op,ak,budget()); archive=work.archive(lease,op,budget())
    identity=IdentityService(v.path,v.provider,v.store); identity.unlock(); identity.reload(a)
    window=MailboxWindow(identity)
    try:
        keys=[MessageKey(a,'INBOX',17,i) for i in (3,2,1)]
        window.rows=tuple(Header(key,'transport claim','outer','',1,False) for key in keys)
        window.render_rows()
        for key in keys[:2]:
            window.show_display(replace(archive,key=key,protected=replace(archive.protected,references=('<thread@example.invalid>',))))
        window.show_display(Display(keys[2],'outer','unverified','unverified',False))
        window.group_threads()
        assert [row.key.uid for row in window.rows]==[2,3,1]
        assert window.table.item(2,4).text()=='' and window.display is None
        assert len(window.threads)==2 and not any(row.seen for row in window.rows)
        identity.select(b.account); assert not window.threads
    finally: window.close(); window.pool.shutdown(wait=True)
