"""Account-scoped compose/outbox controls; no presentation controller or fixtures."""
from pathlib import Path
import threading
import time
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QPlainTextEdit, QCheckBox, QListWidget, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QFileDialog, QMessageBox, QInputDialog)
from experiments.m5.model import Draft, Budget
from experiments.m5.provider import Provider
from mailbox_client.model import Display
from mailbox_client.workflows import Workflows, import_attachment
from .mail_accessibility import configure,error_message


class MailActions(QDialog):
    def __init__(self, window, factory=None, gmail_enabled=False):
        super().__init__(window)
        self.window, self.gmail_enabled = window, gmail_enabled
        self.factory = factory or self.service
        self.submission_enabled=gmail_enabled or factory is not None
        self.epoch = 0; self.pending = []; self.cancel_event = None
        self.operation = None; self.attachments = (); self.references = (); self.in_reply_to = ''
        self.rows = ()
        self.setWindowTitle('QuMail — protected compose and outbox (development)')
        self.resize(900, 800)
        layout = QVBoxLayout(self)
        self.notice = QLabel('Protected mail only · Bcc unavailable · 3 recipients · body 8 KiB · 4 attachments / 16 KiB total')
        self.notice.setWordWrap(True); layout.addWidget(self.notice)
        self.to = QLineEdit(); self.cc = QLineEdit(); self.subject = QLineEdit()
        for name, widget in [('To (comma separated)',self.to),('Cc',self.cc),('Subject',self.subject)]:
            label=QLabel('&'+name); label.setBuddy(widget); layout.addWidget(label); layout.addWidget(widget)
        self.body = QPlainTextEdit(); layout.addWidget(self.body)
        self.body.setTabChangesFocus(True)
        self.archive = QCheckBox('Include encrypted sender archive'); self.archive.setChecked(True); layout.addWidget(self.archive)
        self.files = QListWidget(); self.files.setMaximumHeight(80); layout.addWidget(self.files)
        bar = QHBoxLayout(); layout.addLayout(bar)
        self.editor_buttons=[]
        for name, fn in [('New',self.new),('Add attachment',self.add_attachment),('Remove attachment',self.remove_attachment),
                         ('Verify recipients',lambda:self.start('verify')),('Save encrypted draft',lambda:self.start('save'))]:
            b=QPushButton(name); b.clicked.connect(lambda checked=False, action=fn:action()); bar.addWidget(b)
            self.editor_buttons.append(b)
        layout.addWidget(QLabel('Saved outbox: preparation uses the saved draft; save edits first. Accepted means server acceptance, not delivery.'))
        self.table = QTableWidget(0,4)
        self.table.setHorizontalHeaderLabels(['Operation','State','Attempts','Reason'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.table)
        bar = QHBoxLayout(); layout.addLayout(bar)
        self.buttons={}
        for name, action in [('Refresh outbox','list'),('Edit draft','load'),('Prepare saved','prepare'),
            ('Submit once','submit'),('Explicit retry','retry'),('Discard / cancel saved','discard'),('Open archive','archive')]:
            b=QPushButton(name); self.buttons[name]=b
            b.clicked.connect(lambda checked=False,a=action:self.start(a)); bar.addWidget(b)
        self.buttons['Submit once'].setEnabled(gmail_enabled or factory is not None)
        stop=QPushButton('Cancel active work / clear plaintext'); stop.clicked.connect(lambda:self.stop(True)); layout.addWidget(stop)
        self.stop_button=stop
        self.status=QLabel('Gmail submission disabled unless launched with --dev-gmail-submit. No automatic submission.')
        self.status.setTextFormat(Qt.TextFormat.PlainText); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.timer=QTimer(self); self.timer.timeout.connect(self.poll); self.timer.start(50)
        configure(self,[(self.to,'To recipients, comma separated'),(self.cc,'Cc recipients, comma separated; Bcc unavailable'),
            (self.subject,'Protected subject'),(self.body,'Message plain-text body, 8 KiB maximum'),(self.files,'Compose attachments'),
            (self.table,'Durable outbox operations and delivery states'),(self.archive,'Include encrypted sender archive'),
            (self.status,'Compose and outbox operation status')],
            [self.to,self.cc,self.subject,self.body,self.archive,self.files,*self.editor_buttons,self.table,*self.buttons.values(),stop])

    def service(self):
        helper=Path(__file__).resolve().parents[1]/'tmp/m2/target/debug/qumail-m5-provider.exe'
        return Workflows(self.window.identity.require(),self.window.access,Provider(helper),
                         self.window.identity.google,gmail_enabled=self.gmail_enabled)

    def stop(self, clear=False):
        self.epoch+=1
        if self.cancel_event: self.cancel_event.set()
        if clear:
            self.clear_draft()
            self.window.content.clear(); self.window.security.clear()
            self.window.display=None; self.window.attachments.clear()
        self.status.setText('Cancelled. Refresh outbox to inspect the durable result; cancellation cannot recall accepted mail.')

    def clear_draft(self):
        self.operation=None; self.attachments=(); self.references=(); self.in_reply_to=''
        for field in (self.to,self.cc,self.subject,self.body): field.clear()
        self.files.clear(); self.archive.setChecked(True)

    def reset(self):
        self.stop(True); self.rows=(); self.table.setRowCount(0)

    def new(self):
        self.stop(); self.clear_draft()

    def draft(self):
        addresses=lambda text:tuple(v.strip() for v in text.split(',') if v.strip())
        return Draft(addresses(self.to.text()),addresses(self.cc.text()),self.subject.text(),self.body.toPlainText(),
                     self.attachments,self.in_reply_to,self.references,self.archive.isChecked())

    def install(self,draft):
        self.to.setText(', '.join(draft.to)); self.cc.setText(', '.join(draft.cc))
        self.subject.setText(draft.subject); self.body.setPlainText(draft.body)
        self.attachments=draft.attachments; self.references=draft.references; self.in_reply_to=draft.in_reply_to
        self.archive.setChecked(draft.archive); self.show_files()

    def show_files(self):
        self.files.clear()
        for a in self.attachments: self.files.addItem(f'{a.name} · {len(a.data)} bytes · claimed {a.media_type}')

    def add_attachment(self):
        path,_=QFileDialog.getOpenFileName(self,'Add attachment (never executed)')
        if not path: return
        try:
            from dataclasses import replace
            from experiments.m5.mime import validate
            added=self.attachments+(import_attachment(path),)
            # Validate aggregate size even before recipient entry.
            validate(replace(self.draft(),to=('check@example.invalid',),cc=(),attachments=added))
            self.attachments=added; self.show_files()
        except Exception: self.status.setText('Attachment rejected: unsafe filename/path or qualified size/type limit.')

    def remove_attachment(self):
        i=self.files.currentRow()
        if i>=0: self.attachments=self.attachments[:i]+self.attachments[i+1:]; self.show_files()

    def selected(self):
        i=self.table.currentRow()
        return self.rows[i].operation if 0<=i<len(self.rows) else None

    def start(self,action, *, source=None, recipients=(), confirmed=False, destination=None, index=None):
        snapshot=self.window.identity.session.snapshot; lease=self.window.lease
        if not lease or snapshot.locked:
            self.status.setText('Unlock and select an account first.'); return
        if self.pending:
            self.status.setText('Wait for or cancel the active operation.'); return
        operation=self.selected()
        if action in ('load','prepare','submit','retry','discard','archive') and operation is None:
            self.status.setText('Select an outbox operation first.'); return
        acknowledge=False
        if action in ('submit','retry','discard'):
            text={'submit':'Submit this frozen protected message once through the configured Gmail endpoint?',
                  'retry':'Prepare the SAME bytes for a separate retry? Unknown may already have been accepted; another submission can duplicate mail.',
                  'discard':'Discard the selected draft, or cancel a prepared submission? This cannot recall sent mail.'}[action]
            if QMessageBox.question(self,'Explicit action',text)!=QMessageBox.StandardButton.Yes: return
            acknowledge=True
        try:
            service=self.factory(); draft=self.draft() if action in ('save','verify') else None
        except Exception:
            self.status.setText('Vault/provider unavailable.'); return
        if action=='archive': self.window.cancel(clear_actions=False)
        self.stop()
        epoch=self.epoch; parent_epoch=self.window.epoch; generation=snapshot.generation
        cancel=threading.Event(); self.cancel_event=cancel
        budget=Budget(cancel,time.monotonic()+30); editing=self.operation
        key=snapshot.active.key
        def work():
            if action=='save': return service.save(lease,draft,budget,editing)
            if action=='verify': return service.recipients(lease,draft,budget)
            if action=='list': return service.outbox(lease,budget)
            if action=='load': return service.load(lease,operation,budget)
            if action=='prepare': return service.prepare(lease,operation,key,budget)
            if action=='submit': return service.submit(lease,operation,budget)
            if action=='retry': return service.retry(lease,operation,budget,acknowledge)
            if action=='discard': return service.cancel_saved(lease,operation,budget)
            if action=='archive': return service.archive(lease,operation,budget)
            if action=='export': return service.export(lease,source,index,destination,budget)
            return service.derive(lease,source,budget,forward=action=='forward',recipients=recipients,confirmed=confirmed)
        self.pending.append((epoch,parent_epoch,generation,lease,cancel,action,operation,self.window.pool.submit(work)))
        self.status.setText('Working…')
        self.update_controls()

    def poll(self):
        for item in list(self.pending):
            epoch,parent_epoch,generation,lease,cancel,action,operation,future=item
            if not future.done(): continue
            self.pending.remove(item)
            if (epoch!=self.epoch or cancel.is_set() or lease is not self.window.lease or
                generation!=self.window.identity.session.snapshot.generation): continue
            if action in ('archive','reply','forward','export') and parent_epoch!=self.window.epoch: continue
            try:
                value=future.result()
                if action=='list':
                    self.rows=value; self.table.setRowCount(len(value))
                    for i,row in enumerate(value):
                        for j,text in enumerate((row.operation.value,row.state.value,str(row.attempt),row.reason)):
                            self.table.setItem(i,j,QTableWidgetItem(text))
                    self.table.resizeColumnsToContents(); self.status.setText('Durable account outbox refreshed.')
                elif isinstance(value,Draft):
                    self.operation=operation if action=='load' else None
                    self.install(value); self.status.setText('Draft loaded. Review recipients, save, then prepare.'); self.show()
                elif isinstance(value,Display):
                    self.window.show_display(value); self.status.setText('Sender archive verified and opened.')
                elif action=='save':
                    self.operation=value; self.status.setText('Encrypted draft saved. Refresh outbox, select it, then Prepare saved.')
                elif action=='prepare':
                    self.clear_draft(); self.status.setText('Prepared and durably frozen. Refresh outbox; submission is a separate action.')
                elif action=='submit':
                    self.status.setText(f'{value.state.value}: {value.reason}. Refresh outbox. No automatic retry.')
                else: self.status.setText(str(value))
            except Exception as error:
                self.status.setText(error_message(error))
        self.update_controls()

    def update_controls(self):
        ready=self.window.lease is not None and not self.window.identity.session.snapshot.locked
        idle=ready and not self.pending
        self.table.setEnabled(idle)  # A pending archive/submit stays bound to its selected operation.
        for widget in (self.to,self.cc,self.subject,self.body,self.archive,self.files,*self.editor_buttons): widget.setEnabled(idle)
        row=self.table.currentRow()
        state=self.rows[row].state.value if 0<=row<len(self.rows) else None
        for name,button in self.buttons.items():
            allowed={'Refresh outbox':True,'Edit draft':state=='Draft','Prepare saved':state=='Draft',
                'Submit once':self.submission_enabled and state=='Prepared','Explicit retry':state in ('Failed','Unknown'),
                'Discard / cancel saved':state in ('Draft','Prepared'),'Open archive':state is not None and state!='Draft'}[name]
            button.setEnabled(idle and allowed)

    def reject(self):
        self.close()  # Escape follows the same cancellation/plaintext-clearing path as X.

    def derive(self,source,forward=False):
        if source is None: return
        recipients=(); confirmed=False
        if forward or source.protected is None:
            text,ok=QInputDialog.getText(self,'Confirm new recipients',
                'Explicit recipient addresses (comma separated). Original conventional identity is unverified; forwarding is your new signed message.')
            if not ok: return
            recipients=tuple(v.strip() for v in text.split(',') if v.strip())
            confirmed=True
        self.show(); self.start('forward' if forward else 'reply',source=source,recipients=recipients,confirmed=confirmed)

    def closeEvent(self,event):
        self.stop(True)
        event.accept()
