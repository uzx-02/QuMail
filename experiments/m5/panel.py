"""Disposable opt-in compose/open UI; no mailbox sync, HTML or default startup."""
from concurrent.futures import ThreadPoolExecutor
import time
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPlainTextEdit,QComboBox,QPushButton,QMessageBox,QFileDialog,QCheckBox
from .model import Draft,Budget,OpenedMessage


class ComposePanel(QWidget):
    def __init__(self,session,access,compose,opener,submit,views):
        super().__init__()
        self.session,self.access,self.compose,self.opener,self.submit,self.views=session,access,compose,opener,submit,views
        self.lease=None; self.operations={}; self.envelopes={}; self.shared=None; self.pending=None
        self.pool=ThreadPoolExecutor(max_workers=1)
        self.setWindowTitle('M5 disposable protected compose — synthetic identities, loopback only')
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('Development only. Bcc unavailable. No external mail. Open uses the persisted ciphertext copy.'))
        self.accounts=QComboBox()
        for view in views: self.accounts.addItem(view.address,view)
        self.accounts.currentIndexChanged.connect(self.select); layout.addWidget(self.accounts)
        self.to=QLineEdit(); self.cc=QLineEdit(); self.subject=QLineEdit(); self.body=QPlainTextEdit()
        for label,widget in [('To (comma-separated)',self.to),('Cc',self.cc),('Protected subject',self.subject),('Body',self.body)]:
            layout.addWidget(QLabel(label)); layout.addWidget(widget)
        self.archive=QCheckBox('Include sender archival encryption recipient'); self.archive.setChecked(True); layout.addWidget(self.archive)
        self.status=QLabel('Locked'); layout.addWidget(self.status)
        self.content=QPlainTextEdit(); self.content.setReadOnly(True); layout.addWidget(self.content)
        row=QHBoxLayout(); layout.addLayout(row)
        for name,action in [('Unlock/select',lambda:self.select(self.accounts.currentIndex())),('Lock',lambda:session.install(locked=True)),
            ('Save draft',lambda:self.start('draft')),('Prepare',lambda:self.start('prepare')),
            ('Inspect',lambda:self.start('inspect')),('Submit loopback',lambda:self.start('submit')),
            ('Open copy',lambda:self.start('open')),('Recover',lambda:self.start('recover')),
            ('Retry',self.retry),('Export receipt',self.export),('Cancel',self.cancel)]:
            button=QPushButton(name); button.clicked.connect(lambda checked=False,fn=action:fn()); row.addWidget(button)
        self.timer=QTimer(self); self.timer.timeout.connect(self.poll); self.timer.start(20)
        session.changed.connect(self.changed); self.select(0)

    def select(self,index):
        view=self.accounts.itemData(index)
        if view: self.session.install(self.views,view)

    def changed(self,snapshot):
        self.lease=self.access.select(snapshot.active.context if snapshot.active and not snapshot.locked else None)
        self.content.clear(); self.subject.clear(); self.body.clear(); self.to.clear(); self.cc.clear()
        self.status.setText('Locked' if snapshot.locked else 'Selected; new draft or inspect saved operation')

    def cancel(self):
        if self.lease: self.lease.cancelled.set()
        self.content.clear(); self.status.setText('Cancelled; select/unlock to continue')

    def start(self,action,**kwargs):
        if not self.lease or self.lease.cancelled.is_set(): self.status.setText('Locked/cancelled'); return
        if self.pending: self.status.setText('Worker busy'); return
        lease=self.lease; generation=self.session.snapshot.generation; view=self.session.snapshot.active
        operation=self.operations.get(lease.context.account.value)
        if action not in ('draft','open','recover') and operation is None: self.status.setText('Save a draft first'); return
        if action=='open' and self.shared is None: self.status.setText('Prepare a message first'); return
        shared=self.shared
        draft=Draft(tuple(v.strip() for v in self.to.text().split(',') if v.strip()),
            tuple(v.strip() for v in self.cc.text().split(',') if v.strip()),self.subject.text(),self.body.toPlainText(),archive=self.archive.isChecked())
        budget=Budget(lease.cancelled,time.monotonic()+30)
        def work():
            if action=='draft': return self.compose.draft(lease,draft,budget)
            if action=='prepare':
                envelope=self.compose.prepare(lease,operation,view.key,budget)
                vault=self.compose.vault
                public=bytes(vault.key(vault._read(lease.context),lease.context,view.key)['public'])
                budget.check()
                return envelope,public
            if action=='open': return self.opener.open(lease,view.key,shared[0],shared[1],budget)
            if action=='recover': return self.submit.recover(lease)
            return getattr(self.submit,action)(lease,operation,**kwargs)
        self.pending=(generation,lease,action,self.pool.submit(work))
        self.status.setText('Working')

    def poll(self):
        if not self.pending or not self.pending[3].done(): return
        generation,lease,action,future=self.pending; self.pending=None
        if generation!=self.session.snapshot.generation or lease is not self.lease or lease.cancelled.is_set(): return
        try:
            value=future.result()
            if action=='draft':
                self.operations[lease.context.account.value]=value; self.status.setText('Draft persisted encrypted')
            elif action=='prepare':
                envelope,public=value; self.envelopes[lease.context.account.value]=envelope
                self.shared=(envelope.serialized,public); self.status.setText('Prepared; exact MIME persisted before SMTP')
            elif isinstance(value,OpenedMessage):
                self.status.setText(f'Signature valid; identity {value.identity_trust}; {value.replay.value}; mismatches {len(value.mismatches)}; archive {value.archive}')
                # Explicit plaintext test view only; no HTML or attachment execution.
                self.content.setPlainText(value.subject+'\n\n'+value.body)
            elif hasattr(value,'state'): self.status.setText(value.state.value+' · '+value.reason)
            else: self.status.setText('Completed; inspect durable state')
        except Exception as error:
            code=getattr(error,'code',None)
            self.status.setText(code.value if code else 'Operation rejected; no diagnostics or private output')
            self.content.clear()

    def retry(self):
        if QMessageBox.question(self,'Explicit retry','The server may already have accepted the message. A retry may duplicate it. Continue?')==QMessageBox.StandardButton.Yes:
            self.start('retry',acknowledge_duplicate_risk=True)

    def export(self):
        path,_=QFileDialog.getSaveFileName(self,'New status-only receipt')
        if path:
            def persist(result):
                with open(path,'x',encoding='utf-8') as f: f.write(result.state.value+'\n'+result.reason+'\n')
            self.start('export_receipt',persist=persist)

    def closeEvent(self,event):
        self.session.install(locked=True); self.timer.stop(); self.pool.shutdown(wait=False,cancel_futures=True); event.accept()
