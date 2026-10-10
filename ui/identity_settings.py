"""Settings-only development window: no legacy Session, inbox, TQR, portal or SMTP."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,
    QLineEdit,QFileDialog,QMessageBox,QInputDialog,QTableWidget,QTableWidgetItem)
from experiments.m3.types import BoundaryError,Code
from experiments.m3.vault import LIMIT


class IdentitySettings(QWidget):
    def __init__(self,service):
        super().__init__()
        self.service=service
        self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='qumail-dev-identity')
        self.pending=[]
        self.setWindowTitle('QuMail — development identity Settings (sending disabled)')
        self.resize(920,680)
        layout=QVBoxLayout(self)
        banner=QLabel('Development only · provisional cryptography · no sending\n'
            'Google test-client authorization only. Yahoo enrollment unavailable. Independent review deferred.')
        banner.setWordWrap(True); layout.addWidget(banner)
        self.status=QLabel('Locked'); layout.addWidget(self.status)
        self.details=QLabel(); layout.addWidget(self.details)
        self.accounts=QComboBox(); self.accounts.currentIndexChanged.connect(self.select); layout.addWidget(self.accounts)
        self.address=QLineEdit(); self.address.setPlaceholderText('Expected Google test-account email'); layout.addWidget(self.address)
        self.buttons={}
        rows=[('Create vault',lambda:self.service.unlock(True)),('Unlock',lambda:self.service.unlock()),
              ('Lock',self.service.lock),('Connect Google',lambda:self.start_auth()),
              ('Reauthorize selected',lambda:self.start_auth('reauthorize')),
              ('Refresh Google',lambda:self.start_auth('refresh')),('Cancel authorization',self.cancel),
              ('Import public certificate',self.import_public),('Verify fingerprint',self.verify),
              ('Export my public certificate',self.export_public),('Encrypted backup',self.backup),
              ('Transfer device',lambda:self.backup(True)),('Restore backup',self.restore),
              ('Activate unchanged root',self.activate),('Replace root',lambda:self.activate(True)),
              ('Rotate device keys',self.service.rotate),('Revoke root',self.revoke)]
        for index,(name,callback) in enumerate(rows):
            if index%4==0: line=QHBoxLayout(); layout.addLayout(line)
            button=QPushButton(name); self.buttons[name]=button
            button.clicked.connect(lambda checked=False,cb=callback:self.guard(cb)); line.addWidget(button)
        self.contacts=QTableWidget(0,3); self.contacts.setHorizontalHeaderLabels(['Address','Root fingerprint','Trust / lifecycle'])
        self.contacts.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); layout.addWidget(self.contacts)
        self.timer=QTimer(self); self.timer.timeout.connect(self.poll); self.timer.start(100)
        service.session.changed.connect(self.render)
        self.render(service.session.snapshot)

    def guard(self,callback):
        try: callback()
        except BoundaryError as error: self.status.setText(error.code.value)
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
        self.refresh_contacts()

    def refresh_contacts(self):
        self.contacts.setRowCount(0)
        if not self.service.session.snapshot.active: return
        try: rows=self.service.contacts()
        except BoundaryError:
            self.status.setText('Recipient state unavailable; no trust assertion shown.'); return
        self.contacts.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,value in enumerate(row): self.contacts.setItem(i,j,QTableWidgetItem(value))

    def select(self,index):
        if index>=0: self.guard(lambda:self.service.select(self.accounts.itemData(index)))

    def cancel(self):
        self.service.session.invalidate()
        self.status.setText('Authorization cancelled; late results will be discarded.')

    def start_auth(self,mode='enroll',recovery=None):
        if sum(not future.done() for _,future,_,_ in self.pending)>=2:
            raise BoundaryError(Code.LIMIT)
        address=(self.service.active().address if mode in ('refresh','reauthorize') else self.address.text().strip())
        ticket,work=self.service.authorization(address,refresh=mode=='refresh',reauthorize=mode=='reauthorize')
        self.pending.append((ticket,self.pool.submit(work),mode,recovery))
        self.status.setText('Complete authorization in your external browser, or cancel.')

    def poll(self):
        for item in list(self.pending):
            ticket,future,mode,recovery=item
            if not future.done(): continue
            self.pending.remove(item)
            if not self.service.session.current(ticket): continue
            try:
                self.service.accept_authorization(ticket,future.result(),mode,recovery)
            except Exception:
                self.service.session.invalidate()
                self.status.setText('Authorization did not complete in this session. Unlock to inspect committed accounts.')

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
        self.service.import_certificate(address,self.read_bounded(path)); self.refresh_contacts()

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
            self.service.verify_fingerprint(address,fingerprint.strip().upper(),method); self.refresh_contacts()

    def export_public(self):
        path,_=QFileDialog.getSaveFileName(self,'Export public certificate to a NEW file')
        if path: self.service.export_public(path)

    def backup(self,transfer=False):
        if transfer and QMessageBox.question(self,'Confirm device transfer',
            'Persist encrypted recovery, then suspend this local account? Offline copies cannot be erased.')!=QMessageBox.StandardButton.Yes: return
        path,_=QFileDialog.getSaveFileName(self,'Save encrypted recovery to a NEW file')
        if not path: return
        secret=self.service.backup(path,transfer=transfer,confirmed=transfer)
        # Intentional local recovery-secret disclosure after explicit export. No log/cache/clipboard copy.
        QMessageBox.information(self,'Save recovery secret separately',
            ('Transfer saved; source account suspended.\n' if transfer else 'Backup saved; source remains unchanged.\n')+
            'Store this 256-bit recovery secret offline, separately from the package. It is not saved by QuMail.\n\n'+secret.hex())

    def restore(self):
        if self.service.session.snapshot.accounts: raise BoundaryError(Code.CONFLICT)
        path,_=QFileDialog.getOpenFileName(self,'Restore into a CLEAN vault')
        if not path: return
        secret,ok=QInputDialog.getText(self,'Recovery secret','64 hexadecimal characters',QLineEdit.EchoMode.Password)
        if not ok: return
        try: key=bytes.fromhex(secret)
        except ValueError: raise BoundaryError(Code.INVALID) from None
        self.start_auth('restore',(self.read_bounded(path),key))

    def activate(self,replace=False):
        text=('Create a replacement root? Contacts must independently reverify its NEW fingerprint.' if replace else
              'Activate the unchanged restored root? Confirm all prior devices are retired. Offline copies cannot be detected or erased.')
        if QMessageBox.question(self,'Explicit activation',text)==QMessageBox.StandardButton.Yes:
            self.service.activate(replace_root=replace,prior_device_retired=not replace)

    def revoke(self):
        if QMessageBox.question(self,'Revoke root','Block new use of this root? Historical decryption records remain.')==QMessageBox.StandardButton.Yes:
            self.service.revoke()

    def closeEvent(self,event):
        self.cancel(); self.service.lock(); self.timer.stop()
        self.pool.shutdown(wait=False,cancel_futures=True)
        event.accept()
