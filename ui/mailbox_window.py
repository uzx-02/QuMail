"""Gmail-first development inbox. No sample data, demo account or automatic send."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import threading
import time
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QPlainTextEdit, QAbstractItemView)
from experiments.m4.model import AccountAccess
from experiments.m5.model import Budget
from experiments.m5.provider import Provider
from mailbox_client.gmail import GmailMailbox
from mailbox_client.service import MailboxService
from mailbox_client.model import Display, Failure, Code
from .identity_settings import IdentitySettings


class MailboxWindow(QWidget):
    def __init__(self, identity, service_factory=None):
        super().__init__()
        self.identity = identity
        self.access = AccountAccess()
        self.lease = None
        self.epoch = 0
        self.cancel_event = None
        self.pending = []
        self.rows = ()
        self.page = None
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='qumail-mailbox')
        self.settings = IdentitySettings(identity)
        self.service_factory = service_factory or self.production_service
        self.setWindowTitle('QuMail — Gmail inbox (development)')
        self.resize(1000, 720)
        # Retain the presentation shell's restrained dark palette, not its fixture workflow.
        self.setStyleSheet('QWidget { background:#0B1220; color:#E5EDF6; } '
            'QPushButton,QComboBox { background:#17263B; padding:7px; } '
            'QTableWidget,QPlainTextEdit { background:#111D2E; selection-background-color:#254B70; }')
        layout = QVBoxLayout(self)
        self.banner = QLabel('Development · production approval pending · sending disabled')
        layout.addWidget(self.banner)
        self.accounts = QComboBox(); layout.addWidget(self.accounts)
        self.accounts.currentIndexChanged.connect(self.select_account)
        bar = QHBoxLayout(); layout.addLayout(bar)
        self.buttons = {}
        for text, action in [('Settings', self.settings.show), ('Refresh headers', lambda:self.start('headers')),
            ('Older', lambda:self.start('older')), ('Open selected', lambda:self.start('open')),
            ('Mark read', lambda:self.start('read')), ('Mark unread', lambda:self.start('unread')),
            ('Cancel', self.cancel), ('Lock', self.identity.lock)]:
            button = QPushButton(text); button.clicked.connect(lambda checked=False, fn=action:fn())
            self.buttons[text] = button; bar.addWidget(button)
        self.status = QLabel('Open Settings to unlock or enroll an explicitly configured Google account.')
        self.status.setTextFormat(Qt.TextFormat.PlainText); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Read state', 'From (transport claim)', 'Subject (transport claim)', 'Date'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        layout.addWidget(self.table)
        layout.addWidget(QLabel('Protected mail: select an imported signer certificate. This does not grant trust.'))
        self.signers = QComboBox(); self.signers.currentIndexChanged.connect(self.selection_changed); layout.addWidget(self.signers)
        self.security = QLabel(); self.security.setTextFormat(Qt.TextFormat.PlainText)
        self.security.setWordWrap(True); layout.addWidget(self.security)
        self.content = QPlainTextEdit(); self.content.setReadOnly(True); layout.addWidget(self.content)
        layout.addWidget(QLabel('Headers/open use PEEK; only Mark read/unread changes server flags. HTML/resources/attachments are not opened.'))
        identity.session.changed.connect(self.session_changed)
        self.timer = QTimer(self); self.timer.timeout.connect(self.poll); self.timer.start(50)
        self.session_changed(identity.session.snapshot)

    def production_service(self):
        helper = Path(__file__).resolve().parents[1]/'tmp/m2/target/debug/qumail-m5-provider.exe'
        return MailboxService(self.identity.require(), self.access, self.identity.google, GmailMailbox(), Provider(helper))

    def cancel(self):
        self.epoch += 1
        if self.cancel_event: self.cancel_event.set()
        self.content.clear(); self.security.clear()
        self.status.setText('Cancelled. A dispatched flag change may have reached Gmail; refresh to confirm.')

    def selection_changed(self):
        self.cancel()
        self.status.setText('Selection changed. Open explicitly; read state is unchanged.')

    def session_changed(self, snapshot):
        self.cancel()
        self.lease = self.access.select(snapshot.active.context if snapshot.active and not snapshot.locked else None)
        self.rows = (); self.page = None
        self.table.setRowCount(0)
        self.accounts.blockSignals(True); self.accounts.clear()
        for row in snapshot.accounts: self.accounts.addItem(row.address, row.context.account)
        if snapshot.active: self.accounts.setCurrentIndex(snapshot.accounts.index(snapshot.active))
        self.accounts.blockSignals(False)
        self.signers.blockSignals(True); self.signers.clear()
        self.signers.addItem('Choose certificate for protected mail', None)
        if self.lease:
            data = self.identity.require()._read(self.lease.context)
            self.signers.addItem(data['address']+' · own root', data['address'])
            for address, contact in data['contacts'].items():
                self.signers.addItem(address+' · '+contact['state'], address)
        self.signers.blockSignals(False)
        self.status.setText('Selected account. Refresh headers explicitly.' if self.lease else 'Locked / no account. Open Settings.')

    def select_account(self, index):
        if index >= 0:
            try: self.identity.select(self.accounts.itemData(index))
            except Exception: self.identity.lock()

    def start(self, action):
        snapshot = self.identity.session.snapshot
        if not self.lease or snapshot.locked:
            self.status.setText('Unlock and select an enrolled Google account in Settings.'); return
        if len(self.pending) >= 2:
            self.status.setText('Previous work is cancelling; wait briefly.'); return
        row = self.table.currentRow()
        key = self.rows[row].key if 0 <= row < len(self.rows) else None
        if action in ('open', 'read', 'unread') and key is None:
            self.status.setText('Select a message.'); return
        if action == 'older' and (not self.page or self.page.before is None):
            self.status.setText('No older UID window available.'); return
        before = (self.page.uidvalidity, self.page.before) if action == 'older' else None
        self.cancel()
        epoch = self.epoch; generation = snapshot.generation; lease = self.lease
        cancel = threading.Event(); self.cancel_event = cancel
        budget = Budget(cancel, time.monotonic()+30)
        signer = self.signers.currentData(); view = snapshot.active
        try: service = self.service_factory()
        except Exception:
            self.status.setText('Mailbox provider or vault unavailable. Check local configuration.'); return
        def work():
            if action in ('headers', 'older'): return service.headers(lease, budget, before)
            if action == 'open': return service.open(lease, key, view.key, signer, budget)
            return service.set_seen(lease, key, action == 'read', budget)
        self.pending.append((epoch, generation, lease, cancel, action, key, self.pool.submit(work)))
        self.status.setText('Working…')

    def poll(self):
        for item in list(self.pending):
            epoch, generation, lease, cancel, action, key, future = item
            if not future.done(): continue
            self.pending.remove(item)
            if (epoch != self.epoch or cancel.is_set() or lease is not self.lease or
                generation != self.identity.session.snapshot.generation): continue
            try:
                result = future.result()
                if action in ('headers', 'older'):
                    self.page = result; self.rows = result.headers
                    self.table.blockSignals(True); self.table.setRowCount(len(self.rows))
                    for index, row in enumerate(self.rows):
                        for column, value in enumerate(('Read' if row.seen else 'Unread', row.sender, row.subject, row.date)):
                            self.table.setItem(index, column, QTableWidgetItem(value))
                    self.table.resizeColumnsToContents(); self.table.blockSignals(False)
                    self.status.setText(f'{len(self.rows)} headers from Gmail. Bodies not fetched. Older scans earlier UID windows.')
                elif isinstance(result, Display):
                    self.security.setText(result.security)
                    self.content.setPlainText(result.subject+'\n\n'+result.body)
                    self.update_seen(result.key, result.seen)
                    self.status.setText('Opened without marking read.')
                else:
                    self.update_seen(key, result)
                    self.status.setText('Server read flag confirmed.')
            except Exception as error:
                self.content.clear(); self.security.clear()
                code = getattr(error, 'code', None)
                self.status.setText(code.value if code else 'Mailbox operation failed; no content released.')
                if isinstance(error, Failure) and error.code in (Code.STALE, Code.MISSING):
                    self.rows = (); self.page = None; self.table.setRowCount(0)

    def update_seen(self, key, seen):
        self.rows = tuple(replace(r, seen=seen) if r.key == key else r for r in self.rows)
        for index, row in enumerate(self.rows):
            self.table.item(index, 0).setText('Read' if row.seen else 'Unread')

    def closeEvent(self, event):
        self.cancel(); self.identity.lock(); self.timer.stop(); self.settings.close()
        self.pool.shutdown(wait=False, cancel_futures=True)
        event.accept()
