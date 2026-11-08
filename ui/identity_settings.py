"""Settings-only development window: no legacy Session, inbox, TQR, portal or SMTP."""
import secrets
from core.settings_operations import Operations,current
from pathlib import Path
from PyQt6.QtCore import QTimer,Qt,pyqtSignal
from PyQt6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,
    QLineEdit,QFileDialog,QMessageBox,QInputDialog,QTableWidget,QTableWidgetItem,QDialog)
from experiments.m3.types import BoundaryError,Code
from experiments.m3.vault import LIMIT
from .mail_accessibility import configure,error_message


class IdentitySettings(QWidget):
    contacts_ready=pyqtSignal(object,object,object)
    def __init__(self,service):
        super().__init__()
        self.service=service
        self.operations=Operations(service)
        self.pool=self.operations.pool
        self.needs_read=False
        self.recovery=None; self.recovery_request=None; self.ceremony=None
        self.publishing=False
        self.disposed=False
        self.setWindowTitle('QuMail — Account Settings')
        self.resize(920,680)
        layout=QVBoxLayout(self)
        banner=QLabel('Google accounts only · Pre-release · Independent security review pending.')
        banner.setWordWrap(True); layout.addWidget(banner)
        self.status=QLabel('Locked'); layout.addWidget(self.status)
        self.details=QLabel(); layout.addWidget(self.details)
        self.status.setTextFormat(Qt.TextFormat.PlainText); self.status.setWordWrap(True)
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        self.accounts=QComboBox(); self.accounts.currentIndexChanged.connect(self.select); layout.addWidget(self.accounts)
        self.address=QLineEdit(); self.address.setPlaceholderText('Expected Google test-account email'); layout.addWidget(self.address)
        self.buttons={}
        rows=[('Create vault',lambda:self.start('create')),('Unlock',lambda:self.start('unlock')),
              ('Lock',self.service.lock),('Connect Google',lambda:self.start_auth()),
              ('Reauthorize selected',lambda:self.start_auth('reauthorize')),
              ('Refresh Google',lambda:self.start_auth('refresh')),('Cancel authorization / operation',self.cancel),
              ('Import public certificate',self.import_public),('Verify fingerprint',self.verify),
              ('Export my public certificate',self.export_public),('Encrypted backup',self.backup),
              ('Transfer device',lambda:self.backup(True)),('Restore backup',self.restore),
              ('Activate unchanged root',self.activate),('Replace root',lambda:self.activate(True)),
              ('Rotate device keys',lambda:self.start('rotate')),('Revoke root',self.revoke),
              ('Complete backup',self.complete_backup),('Inspect outcomes',lambda:self.start('outcomes'))]
        for index,(name,callback) in enumerate(rows):
            if index%4==0: line=QHBoxLayout(); layout.addLayout(line)
            button=QPushButton(name); self.buttons[name]=button
            button.clicked.connect(lambda checked=False,cb=callback:self.guard(cb)); line.addWidget(button)
        self.contacts=QTableWidget(0,3); self.contacts.setHorizontalHeaderLabels(['Address','Root fingerprint','Trust / lifecycle'])
        self.contacts.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); layout.addWidget(self.contacts)
        configure(self,[(self.accounts,'Settings account'),(self.address,'Expected Google test-account email'),
            (self.contacts,'Contact fingerprints and trust lifecycle'),(self.status,'Identity operation status'),
            (self.details,'Selected account root and lifecycle')],[self.accounts,self.address,*self.buttons.values(),self.contacts])
        self.timer=QTimer(self); self.timer.timeout.connect(self.poll); self.timer.start(100)
        service.session.changed.connect(self.render)
        self.render(service.session.snapshot)

    def guard(self,callback):
        try: callback()
        except BoundaryError as error: self.status.setText(error_message(error))
        except Exception: self.status.setText('Operation failed; no credentials or provider diagnostics displayed.')

    def render(self,snapshot):
        self.accounts.blockSignals(True); self.accounts.clear()
        for view in snapshot.accounts: self.accounts.addItem(view.address,view.context.account)
        if snapshot.active:
            self.accounts.setCurrentIndex(next(i for i,v in enumerate(snapshot.accounts) if v==snapshot.active))
        self.accounts.blockSignals(False)
        self.status.setText('Locked' if snapshot.locked else 'Unlocked · sending disabled')
        view=snapshot.active
        self.details.setText(f'{view.address} · {view.lifecycle}\nRoot: {view.root}' if view else 'No account selected')
        for name,button in self.buttons.items():
            if name in ('Create vault','Unlock'): enabled=snapshot.locked
            elif name=='Lock': enabled=not snapshot.locked
            elif name in ('Connect Google','Restore backup'): enabled=not snapshot.locked and self.service.google is not None
            elif name=='Cancel authorization': enabled=True
            else: enabled=view is not None and not snapshot.locked
            if name in ('Refresh Google','Reauthorize selected'): enabled=enabled and self.service.google is not None
            button.setEnabled(enabled)
        if not self.publishing:
            self.drop_recovery()
            self.contacts.setRowCount(0)
            self.needs_read=not snapshot.locked
        self.update_busy()

    def update_busy(self):
        busy=self.operations.busy
        snap=self.service.session.snapshot
        ready=not snap.locked
        for name,button in self.buttons.items():
            if name=='Lock': allowed=ready
            elif name=='Cancel authorization / operation': allowed=busy or self.recovery is not None
            elif name=='Complete backup': allowed=ready and self.recovery is not None and not busy
            elif name in ('Create vault','Unlock'): allowed=snap.locked and not busy
            elif name in ('Connect Google','Restore backup'):
                allowed=ready and self.service.google is not None and not busy and self.recovery is None
            else: allowed=ready and snap.active is not None and not busy and self.recovery is None
            if name in ('Refresh Google','Reauthorize selected'): allowed=allowed and self.service.google is not None
            button.setEnabled(allowed)
        self.address.setEnabled(ready and not busy and self.recovery is None)

    def refresh_contacts(self):
        self.needs_read=not self.service.session.snapshot.locked
        self.contacts.setRowCount(0)

    def select(self,index):
        if index>=0: self.guard(lambda:self.service.select(self.accounts.itemData(index)))

    def drop_recovery(self):
        self.recovery=None; self.recovery_request=None
        if self.ceremony:
            dialog,label,entry=self.ceremony
            self.ceremony=None; label.clear(); entry.clear(); dialog.close(); dialog.deleteLater()

    def cancel(self):
        self.operations.cancel(); self.drop_recovery(); self.needs_read=False
        self.status.setText('Cancellation requested. Authorized commits may finish; unlock/select the original account and Inspect outcomes. No recall or rollback claim.')
        self.update_busy()

    def start(self,operation,*args):
        self.operations.start(operation,*args)
        self.needs_read=False
        self.status.setText('Working in background. Cancel/Lock remain available; committed effects are not undone.')
        self.update_busy()

    def start_auth(self,mode='enroll',recovery=None):
        address=self.service.active().address if mode in ('refresh','reauthorize') else self.address.text().strip()
        self.start(mode,address,*(recovery or ()))
        self.status.setText('Complete authorization in your external browser, or cancel. Persistence follows in the background.')

    def poll(self):
        result=self.operations.take()
        if result is not None:
            authorized=current(self.service.session,result.request)
            if authorized:
                if result.state in ('ready','committed'):
                    op=result.request.operation
                    if (op not in ('read','prepare_backup','outcomes') or
                        op in ('read','outcomes') and result.accounts!=self.service.session.snapshot.accounts):
                        self.publishing=True
                        try:
                            self.service.vault=result.vault
                            self.service.session.install(result.accounts,result.selected)
                        finally: self.publishing=False
                    self.contacts.setRowCount(len(result.contacts))
                    for i,row in enumerate(result.contacts):
                        for j,value in enumerate(row): self.contacts.setItem(i,j,QTableWidgetItem(value))
                    snap=self.service.session.snapshot
                    self.contacts_ready.emit(snap.generation,snap.active,result.contacts)
                    if result.recovery is not None:
                        self.recovery=result.recovery; self.recovery_request=result.request
                        self.status.setText('Backup prepared in memory only. Complete backup: save and acknowledge the recovery secret BEFORE any file is written.')
                    elif op=='outcomes':
                        self.status.setText('Owner-scoped outcomes (last 16 commits): '+str(result.outcomes or 'none'))
                    else: self.status.setText('Committed.' if result.state=='committed' else 'Current account data loaded.')
                elif result.state=='inspect_outcome':
                    self.status.setText('An irreversible step was authorized. Inspect outcomes for this account; do not assume rollback. Unlock again if enrollment/creation changed the vault.')
                elif result.state=='cancelled': self.status.setText('Cancelled before irreversible work.')
                else: self.status.setText(error_message(BoundaryError(result.error)))
            # Stale completion never changes selection, widgets, vault or secret custody.
            result.recovery=None; result.vault=None
        if self.needs_read and not self.operations.busy and not self.recovery and not self.disposed:
            self.needs_read=False
            if not self.service.session.snapshot.locked: self.guard(lambda:self.start('read'))
        self.update_busy()

    def complete_backup(self):
        if self.ceremony: return
        if self.recovery is None: return
        if not self.service.session.current(self.recovery_request.ticket):
            self.drop_recovery(); return
        dialog=QDialog(self); dialog.setWindowTitle('Recovery secret custody — no file written yet')
        layout=QVBoxLayout(dialog)
        label=QLabel('Save this secret offline, separately from the package. QuMail will not retain it.\n'+self.recovery.secret.hex())
        label.setTextFormat(Qt.TextFormat.PlainText); label.setWordWrap(True); layout.addWidget(label)
        entry=QLineEdit(); entry.setEchoMode(QLineEdit.EchoMode.Password)
        entry.setAccessibleName('Re-enter the saved recovery secret to acknowledge custody'); layout.addWidget(entry)
        button=QPushButton('I saved the secret separately; write package'); button.setAutoDefault(False)
        button.clicked.connect(lambda:self.guard(lambda:self.acknowledge_backup(entry.text())))
        layout.addWidget(button)
        self.ceremony=(dialog,label,entry)
        dialog.finished.connect(lambda _:self.cancel() if self.ceremony and self.ceremony[0] is dialog else None)
        dialog.show()

    def acknowledge_backup(self,text):
        stage=self.recovery; req=self.recovery_request
        if stage is None or not self.service.session.current(req.ticket): raise BoundaryError(Code.OWNERSHIP)
        if not secrets.compare_digest(text.strip().lower(),stage.secret.hex()): raise BoundaryError(Code.INVALID)
        args=(stage.package,stage.destination,stage.transfer,stage.revision)
        self.drop_recovery()
        self.start('write_backup',*args)

    @staticmethod
    def read_bounded(path):
        with open(path,'rb') as file: data=file.read(LIMIT+129)
        if len(data)>LIMIT+128: raise BoundaryError(Code.LIMIT)
        return data

    def import_public(self):
        address,ok=QInputDialog.getText(self,'Contact','Expected contact email')
        if not ok: return
        path,_=QFileDialog.getOpenFileName(self,'Select public OpenPGP certificate')
        if not path: return
        self.start('import',address,path)

    def verify(self):
        row=self.contacts.currentRow()
        if row<0: return
        address=self.contacts.item(row,0).text()
        fingerprint,ok=QInputDialog.getText(self,'Independent verification',
            'Enter the FULL root fingerprint verified through an independent channel (not this import).')
        if not ok: return
        method,ok=QInputDialog.getItem(self,'Verification method','Independent channel',
                                     ['in-person','independent-voice','independent-qr'],editable=False)
        if ok:
            self.start('verify',address,fingerprint.strip().upper(),method)

    def export_public(self):
        path,_=QFileDialog.getSaveFileName(self,'Export public certificate to a NEW file')
        if path: self.start('export',path)

    def backup(self,transfer=False):
        if transfer and QMessageBox.question(self,'Confirm device transfer',
            'Persist encrypted recovery, then suspend this local account? Offline copies cannot be erased.')!=QMessageBox.StandardButton.Yes: return
        path,_=QFileDialog.getSaveFileName(self,'Save encrypted recovery to a NEW file')
        if not path: return
        self.start('prepare_backup',path,transfer)

    def restore(self):
        if self.service.session.snapshot.accounts: raise BoundaryError(Code.CONFLICT)
        path,_=QFileDialog.getOpenFileName(self,'Restore into a CLEAN vault')
        if not path: return
        secret,ok=QInputDialog.getText(self,'Recovery secret','64 hexadecimal characters',QLineEdit.EchoMode.Password)
        if not ok: return
        try: key=bytes.fromhex(secret)
        except ValueError: raise BoundaryError(Code.INVALID) from None
        self.start_auth('restore',(path,key))

    def activate(self,replace=False):
        text=('Create a replacement root? Contacts must independently reverify its NEW fingerprint.' if replace else
              'Activate the unchanged restored root? Confirm all prior devices are retired. Offline copies cannot be detected or erased.')
        if QMessageBox.question(self,'Explicit activation',text)==QMessageBox.StandardButton.Yes:
            self.start('replace' if replace else 'activate')

    def revoke(self):
        if QMessageBox.question(self,'Revoke root','Block new use of this root? Historical decryption records remain.')==QMessageBox.StandardButton.Yes:
            self.start('revoke')

    def closeEvent(self,event):
        self.cancel(); self.service.lock()
        # Closing Settings hides it. Its timer must drain cancelled results and
        # its executor must remain usable when the mailbox reopens Settings.
        event.accept()

    def dispose(self):
        if self.disposed: return
        self.disposed=True
        self.cancel(); self.timer.stop()
        self.operations.close()
