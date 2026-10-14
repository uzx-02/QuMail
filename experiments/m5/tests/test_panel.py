import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import subprocess
import sys
import threading
import time
import pytest
from PyQt6.QtCore import QTimer
from core.account_session import DevelopmentSession,AccountView
from experiments.m3.tests.conftest import qapp
from experiments.m5.tests.test_message import setup,provider,vault
from experiments.m5.panel import ComposePanel
from experiments.m5.services import OpenMessage
from experiments.m4.services import SubmitOutbox
from experiments.m4.transports import SimulatedTransport


@pytest.mark.parametrize('scenario,initial',[('success','Accepted'),('auth-reject','Failed'),('final-loss','Unknown')])
def test_disposable_compose_open_workflow(scenario,initial):
    run=subprocess.run([sys.executable,'-m','experiments.m5.demo','--loopback','--smoke','--scenario',scenario],capture_output=True,text=True,timeout=60)
    assert run.returncode==0,'disposable demo failed; no private diagnostics published'
    result=json.loads(run.stdout)
    assert result['initial']==initial and result['final']=='Accepted'
    assert result['sender_archive'] and result['recipient_copies']==2 and result['persisted_bytes_match']
    print('COMPOSE_WORKFLOW',scenario,'draft -> persisted MIME -> TLS -> recipient/CC/archive open')


@pytest.mark.parametrize('change',['switch','lock','cancel'])
def test_slow_crypto_off_gui_and_stale_result_rejected(setup,qapp,monkeypatch,change):
    v,accounts,access,lease,native,compose,draft=setup
    views=tuple(sorted((AccountView(*row) for row in v.summaries()),key=lambda row:row.context!=accounts[0][0]))
    panel=ComposePanel(DevelopmentSession(),access,compose,OpenMessage(v,access,native),SubmitOutbox(compose.repository,SimulatedTransport()),views)
    panel.to.setText('bob@example.invalid'); panel.subject.setText('fixture'); panel.body.setPlainText('private fixture')
    entered=threading.Event(); release=threading.Event(); original=native.call
    def delayed(op,*args,**kw):
        if op=='seal': entered.set(); assert release.wait(4)
        return original(op,*args,**kw)
    monkeypatch.setattr(native,'call',delayed)
    ticks=[]; timer=QTimer(); timer.timeout.connect(lambda:ticks.append(1)); timer.start(10)
    def drain():
        until=time.monotonic()+8
        while panel.pending and time.monotonic()<until: qapp.processEvents(); panel.poll(); time.sleep(.01)
        assert not panel.pending
    try:
        panel.start('draft'); drain(); panel.start('prepare')
        until=time.monotonic()+3
        while not entered.is_set() and time.monotonic()<until: qapp.processEvents(); time.sleep(.01)
        assert entered.is_set() and ticks
        if change=='switch': panel.select(1)
        elif change=='lock': panel.session.install(locked=True)
        else: panel.cancel()
        status=panel.status.text(); release.set(); drain()
        assert panel.status.text()==status and panel.shared is None and not panel.content.toPlainText()
        data=v._read(accounts[0][0]); rows=data['m4_outbox_v1'].values()
        assert all(row['state']=='Draft' and 'prepared' not in row for row in rows)
    finally:
        release.set(); timer.stop(); panel.close(); qapp.processEvents(); panel.pool.shutdown(wait=True,cancel_futures=True)
