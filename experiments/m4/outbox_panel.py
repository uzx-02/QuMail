"""Opt-in fixture panel. No production account enrollment or external destination UI."""
from concurrent.futures import ThreadPoolExecutor
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QComboBox,QLabel,QPushButton,QMessageBox,QFileDialog
from .model import Failure


class OutboxPanel(QWidget):
    def __init__(self, session, access, submit, operations, views):
        super().__init__()
        self.session,self.access,self.submit,self.operations,self.views=session,access,submit,operations,views
        self.lease=None; self.pending=[]; self.pool=ThreadPoolExecutor(max_workers=2)
        self.setWindowTitle('M4 loopback outbox qualification — synthetic credentials only')
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('Disposable SMTP/TLS fixture; no external mail. Accepted means server acceptance only.'))
        self.accounts=QComboBox()
        for view in views: self.accounts.addItem(view.address,view)
        self.accounts.currentIndexChanged.connect(self.select); layout.addWidget(self.accounts)
        self.status=QLabel('Locked'); layout.addWidget(self.status)
        buttons=QHBoxLayout(); layout.addLayout(buttons)
        for name,action in [('Unlock/select',lambda:self.select(self.accounts.currentIndex())),
            ('Lock',lambda:session.install(locked=True)),('Inspect',lambda:self.start('inspect')),
            ('Submit loopback',lambda:self.start('submit')),('Recover',lambda:self.start('recover')),
            ('Retry Unknown/Failed',self.retry),('Export receipt',self.export)]:
            button=QPushButton(name); button.clicked.connect(lambda checked=False,fn=action:fn()); buttons.addWidget(button)
        session.changed.connect(self.changed)
        self.timer=QTimer(self); self.timer.timeout.connect(self.poll); self.timer.start(30)
        self.select(0)

    def select(self,index):
        view=self.accounts.itemData(index)
        if view: self.session.install(self.views,view)

    def changed(self,snapshot):
        self.lease=self.access.select(snapshot.active.context if snapshot.active and not snapshot.locked else None)
        self.status.setText('Locked' if snapshot.locked else 'Account selected; inspect prepared operation')

    def start(self,action,**kwargs):
        if self.lease is None: self.status.setText('Locked'); return
        if sum(not f.done() for _,_,f in self.pending)>=2: self.status.setText('Workers busy'); return
        lease=self.lease; generation=self.session.snapshot.generation
        operation=self.operations[lease.context.account.value]
        def work():
            if action=='recover': return self.submit.recover(lease)
            return getattr(self.submit,action)(lease,operation,**kwargs)
        self.pending.append((generation,lease,self.pool.submit(work)))
        self.status.setText('Working on selected operation')

    def poll(self):
        for item in list(self.pending):
            generation,lease,future=item
            if not future.done(): continue
            self.pending.remove(item)
            if generation!=self.session.snapshot.generation or lease is not self.lease: continue
            try:
                value=future.result()
                if hasattr(value,'state'): self.status.setText(value.state.value+' · '+value.reason)
                else: self.status.setText('Completed; inspect operation for durable status')
            except Failure as error: self.status.setText(error.code.value)
            except Exception: self.status.setText('Operation unavailable; inspect/recover; no diagnostics displayed')

    def retry(self):
        if QMessageBox.question(self,'Explicit retry','The server may already have accepted this message. Retry can duplicate it. Continue?')==QMessageBox.StandardButton.Yes:
            self.start('retry',acknowledge_duplicate_risk=True)

    def export(self):
        path,_=QFileDialog.getSaveFileName(self,'New receipt file; contains status only')
        if not path: return
        def persist(result):
            with open(path,'x',encoding='utf-8') as file: file.write(result.state.value+'\n'+result.reason+'\n')
        self.start('export_receipt',persist=persist)

    def closeEvent(self,event):
        self.session.install(locked=True); self.timer.stop()
        self.pool.shutdown(wait=False,cancel_futures=True); event.accept()
