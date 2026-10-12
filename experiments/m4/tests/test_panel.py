import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import subprocess
import sys
import time
import pytest
from PyQt6.QtCore import QTimer
from core.account_session import DevelopmentSession,AccountView
from experiments.m3.tests.conftest import qapp
from experiments.m4.tests.test_smtp import provider,vault,case,transport
from experiments.m4.smtp_fixture import SMTPServer
from experiments.m4.services import SubmitOutbox
from experiments.m4.outbox_panel import OutboxPanel
from experiments.m4.loopback_demo import finish_panel


def test_panel_network_worker_account_switch_and_lock(case,tmp_path,qapp):
    v,a,ak,b,bk,access,lease,repo,op,envelope=case
    views=tuple(AccountView(*row) for row in v.summaries())
    views=tuple(sorted(views,key=lambda row:row.context!=a))
    with SMTPServer(tmp_path/'certs','stall-final') as server:
        adapter,_=transport(server,a)
        panel=OutboxPanel(DevelopmentSession(),access,SubmitOutbox(repo,adapter),
            {a.account.value:op,b.account.value:op},views)
        ticks=[]; timer=QTimer(); timer.timeout.connect(lambda:ticks.append(1)); timer.start(10)
        try:
            panel.start('submit')
            until=time.monotonic()+4
            while not server.accepted.is_set() and time.monotonic()<until:
                qapp.processEvents(); time.sleep(.01)
            assert server.accepted.is_set() and ticks
            panel.select(1); selected=panel.status.text()
            server.release.set()
            until=time.monotonic()+4
            while panel.pending and time.monotonic()<until: qapp.processEvents(); panel.poll(); time.sleep(.01)
            assert not panel.pending and panel.status.text()==selected
            panel.start('inspect'); panel.session.install(locked=True)
            until=time.monotonic()+2
            while panel.pending and time.monotonic()<until: qapp.processEvents(); panel.poll(); time.sleep(.01)
            assert panel.status.text()=='Locked'
        finally: timer.stop(); panel.close(); qapp.processEvents()


@pytest.mark.parametrize('scenario,initial',[('success','Accepted'),('auth-reject','Failed'),('final-loss','Unknown')])
def test_opt_in_loopback_workflows(scenario,initial):
    command=[sys.executable,'-m','experiments.m4.loopback_demo','--loopback','--smoke','--scenario',scenario]
    run=subprocess.run(command,capture_output=True,text=True,timeout=30)
    assert run.returncode==0,'fixture demo failed; inspect private local diagnostics'
    data=json.loads(run.stdout)
    assert data['initial']==initial and data['final']=='Accepted'
    assert data['retained_payloads_equal'] and data['receipt_failure_preserved']


def test_close_waits_for_worker_before_disposable_storage_cleanup(case,tmp_path,qapp):
    v,a,ak,b,bk,access,lease,repo,op,envelope=case
    views=tuple(sorted((AccountView(*row) for row in v.summaries()),key=lambda row:row.context!=a))
    with SMTPServer(tmp_path/'certs','stall-final') as server:
        adapter,_=transport(server,a)
        panel=OutboxPanel(DevelopmentSession(),access,SubmitOutbox(repo,adapter),{a.account.value:op},views)
        panel.start('submit')
        until=time.monotonic()+4
        while not server.accepted.is_set() and time.monotonic()<until: qapp.processEvents(); time.sleep(.01)
        assert server.accepted.is_set()
        finish_panel(panel,qapp)
        assert all(f.done() for _,_,f in panel.pending)
        with repo.ownership(a,op): pass  # OS ownership released before file cleanup.
        (v.path).rename(tmp_path/'closed-vault.sqlite')
        server.release.set()
