"""Real disposable Windows vaults, synthetic OAuth, controlled worker/commit delays."""
import threading
import time
from pathlib import Path
from dataclasses import replace
import pytest
from PyQt6.QtCore import QTimer
from experiments.m3.tests.test_m3 import vault,provider
from experiments.m3.tests.conftest import qapp
from experiments.m3.tests.test_integration import service,add,result
from experiments.m3.vault import Vault
from experiments.m3.types import BoundaryError
from core import settings_operations as ops
from ui.identity_settings import IdentitySettings


def drain(window,qapp,seconds=15):
    end=time.monotonic()+seconds
    while (window.operations.busy or window.needs_read) and time.monotonic()<end:
        qapp.processEvents(); window.poll(); time.sleep(.005)
    assert not window.operations.busy and not window.needs_read


@pytest.fixture
def settings(service,qapp):
    add(service,'alice'); add(service,'bob')
    window=IdentitySettings(service); window.show(); drain(window,qapp)
    yield window
    window.close(); window.dispose(); window.pool.shutdown(wait=True)


def test_slow_native_read_lock_switch_and_close_responsive(settings,qapp,monkeypatch):
    w=settings; service=w.service; entered=threading.Event(); release=threading.Event()
    original=ops.ScopedVault.summaries
    def slow(v): entered.set(); assert release.wait(5); return original(v)
    monkeypatch.setattr(ops.ScopedVault,'summaries',slow)
    w.start('read'); assert entered.wait(2)
    ticks=[]; timer=QTimer(); timer.timeout.connect(lambda:ticks.append(1)); timer.start(10)
    try:
        started=time.monotonic()
        service.select(service.session.snapshot.accounts[0].context.account)
        w.buttons['Lock'].click(); w.close()
        end=time.monotonic()+.12
        while time.monotonic()<end: qapp.processEvents(); time.sleep(.005)
        assert time.monotonic()-started<1 and len(ticks)>=3
        assert service.session.snapshot.locked and not w.contacts.rowCount()
    finally: release.set(); timer.stop()
    drain(w,qapp)
    assert service.vault is None and w.details.text()=='No account selected'


def test_enrollment_cancel_during_real_generate_cannot_commit(service,qapp,monkeypatch):
    entered=threading.Event(); release=threading.Event(); original=service.provider.call
    def delayed(*args,**kwargs):
        value=original(*args,**kwargs); entered.set(); assert release.wait(5); return value
    monkeypatch.setattr(service.provider,'call',delayed)
    monkeypatch.setattr(service.google,'authorize',lambda *args:result('alice'))
    w=IdentitySettings(service); drain(w,qapp)
    try:
        w.address.setText('alice@example.invalid'); w.start_auth(); assert entered.wait(3)
        w.cancel(); release.set(); drain(w,qapp)
        assert service.vault.summaries()==() or len(service.vault.summaries())==0
        assert service.session.snapshot.active is None
    finally: release.set(); w.close(); w.dispose(); w.pool.shutdown(wait=True)


@pytest.mark.parametrize('after_reservation',[False,True])
def test_cancel_commit_boundary_and_owner_receipt(settings,qapp,monkeypatch,after_reservation):
    w=settings; service=w.service; owner=service.active()
    other=next(a for a in service.session.snapshot.accounts if a!=owner)
    entered=threading.Event(); release=threading.Event(); original=ops.Guard.reserve
    def pause(guard):
        if after_reservation: original(guard)
        entered.set(); assert release.wait(5)
        if not after_reservation: original(guard)
    monkeypatch.setattr(ops.Guard,'reserve',pause)
    oldroot=owner.root
    w.start('replace'); assert entered.wait(3)
    started=time.monotonic(); service.select(other.context.account); w.cancel()
    assert time.monotonic()-started<1
    release.set(); drain(w,qapp)
    data=service.vault._read(owner.context)
    assert (data['root']!=oldroot)==after_reservation
    assert bool(data.get('settings_outcomes'))==after_reservation
    assert service.active()==other and owner.address not in w.details.text()
    assert 'settings_outcomes' not in service.vault._read(other.context)


def test_backup_ack_before_write_survives_lock_and_restores(settings,qapp,tmp_path,monkeypatch,provider):
    w=settings; service=w.service; owner=service.active(); path=tmp_path/'backup.bin'
    w.start('prepare_backup',str(path),False); drain(w,qapp)
    secret=w.recovery.secret; assert not path.exists()
    with pytest.raises(BoundaryError): w.acknowledge_backup('00'*32)
    assert not path.exists()
    entered=threading.Event(); release=threading.Event(); original=ops.persist_new
    def pause(path,data): original(path,data); entered.set(); assert release.wait(5)
    monkeypatch.setattr(ops,'persist_new',pause)
    w.acknowledge_backup(secret.hex()); assert entered.wait(3)
    assert w.recovery is None and w.ceremony is None
    service.lock(); release.set(); drain(w,qapp)
    assert service.vault is None and not w.contacts.rowCount()
    clean=Vault.create(tmp_path/'restored.sqlite',service.store,provider)
    try:
        restored=clean.restore(path.read_bytes(),secret,result('bob').identity,explicit=True)
        assert clean._read(restored)['state']=='archive_only'
        assert clean._read(restored)['root']==owner.root
    finally: service.store.delete(clean.ident)
    service.unlock(); service.select(owner.context.account); drain(w,qapp)
    w.start('outcomes'); drain(w,qapp)
    assert 'write_intent' in w.status.text() and "'package_matches': True" in w.status.text()
    assert service.vault._read(owner.context)['state']=='active'


@pytest.mark.parametrize('failure',['before_write','during_write','before_commit','success'])
def test_transfer_ack_and_failures_never_silently_suspend(settings,qapp,tmp_path,monkeypatch,failure):
    w=settings; service=w.service; owner=service.active(); path=tmp_path/'transfer.bin'
    w.start('prepare_backup',str(path),True); drain(w,qapp); secret=w.recovery.secret
    if failure=='before_write':
        w.cancel(); assert not path.exists() and w.recovery is None
    else:
        original=ops.persist_new
        def write(path,data):
            if failure=='during_write': raise OSError('controlled failure')
            original(path,data)
            if failure=='before_commit': w.operations.request.ticket.cancelled.set()
        monkeypatch.setattr(ops,'persist_new',write)
        w.acknowledge_backup(secret.hex()); drain(w,qapp)
    data=service.vault._read(owner.context)
    assert (data['state']=='suspended_for_transfer')==(failure=='success')
    assert path.exists()==(failure in ('before_commit','success'))
    assert w.recovery is None
    if failure=='success': assert data['settings_outcomes'][-1]['state']=='transfer_written'


def test_close_ceremony_destroys_private_staging_without_package(settings,qapp,tmp_path):
    w=settings; path=tmp_path/'never-written.bin'
    w.start('prepare_backup',str(path),False); drain(w,qapp)
    w.complete_backup(); dialog,label,entry=w.ceremony
    assert len(w.recovery.secret)==32
    w.complete_backup(); assert w.ceremony[0] is dialog
    w.service.lock(); qapp.processEvents()
    assert not path.exists() and w.recovery is None and not label.text() and not entry.text()


def test_single_admission_and_private_result_disposal(settings,qapp,monkeypatch):
    w=settings; entered=threading.Event(); release=threading.Event(); original=ops.ScopedVault.summaries
    def pause(v): entered.set(); assert release.wait(5); return original(v)
    monkeypatch.setattr(ops.ScopedVault,'summaries',pause)
    w.start('read'); assert entered.wait(2)
    with pytest.raises(BoundaryError): w.start('replace')
    assert not w.buttons['Rotate device keys'].isEnabled()
    future=w.operations.future; w.dispose(); release.set(); w.pool.shutdown(wait=True)
    assert w.operations.future is None
    r=future.result(); assert r.vault is None and r.recovery is None and not r.request.args
    assert not any(t.name.startswith('qumail-settings') and t.is_alive() for t in threading.enumerate())


def test_async_import_rotate_read_and_revoke_preserve_historical_key(settings,qapp,tmp_path):
    w=settings; s=w.service; owner=s.active(); other=next(a for a in s.session.snapshot.accounts if a!=owner)
    public=tmp_path/'contact.asc'; public.write_bytes(s.vault.export_public(other.context,other.key))
    w.start('import',other.address,str(public)); drain(w,qapp)
    assert w.contacts.item(0,2).text()=='unverified'
    w.start('verify',other.address,other.root,'in-person'); drain(w,qapp)
    assert w.contacts.item(0,2).text()=='independently_verified'
    output=tmp_path/'own.asc'; w.start('export',str(output)); drain(w,qapp)
    assert output.read_bytes()==s.vault.export_public(owner.context,owner.key)
    w.start('rotate'); drain(w,qapp)
    current=s.active(); assert current.root==owner.root and current.key!=owner.key
    assert s.vault._read(owner.context)['keys'][owner.key.value]['secret']
    w.start('revoke'); drain(w,qapp)
    assert s.active().lifecycle=='revoked'
    assert s.vault._read(owner.context)['keys'][current.key.value]['secret']


def test_async_restore_cancel_then_restore_activate_and_replace(service,qapp,tmp_path,monkeypatch,provider):
    from core.identity_service import IdentityService
    original=add(service,'alice'); archive=tmp_path/'restore.bin'; secret=service.backup(archive)
    target=IdentityService(tmp_path/'target.sqlite',provider,service.store,service.google)
    monkeypatch.setattr(target.google,'authorize',lambda *args:result('alice'))
    w=IdentitySettings(target)
    try:
        w.start('create'); drain(w,qapp); ident=target.vault.ident
        real=provider.call; entered=threading.Event(); release=threading.Event()
        def pause(*args,**kwargs):
            value=real(*args,**kwargs); entered.set(); assert release.wait(5); return value
        monkeypatch.setattr(provider,'call',pause)
        w.address.setText('alice@example.invalid'); w.start_auth('restore',(str(archive),secret))
        assert entered.wait(3); w.cancel(); release.set(); drain(w,qapp)
        assert not target.vault.summaries()
        monkeypatch.setattr(provider,'call',real)
        w.start_auth('restore',(str(archive),secret)); drain(w,qapp)
        assert target.active().lifecycle=='archive_only' and target.active().root==original.root
        w.start('activate'); drain(w,qapp)
        assert target.active().root==original.root and target.active().lifecycle=='active'
        w.start('replace'); drain(w,qapp)
        assert target.active().root!=original.root
        target.lock(); w.start('unlock'); drain(w,qapp)
        assert not target.session.snapshot.locked
    finally:
        w.close(); w.dispose(); w.pool.shutdown(wait=True)
        if 'ident' in locals(): service.store.delete(ident)


def test_secret_display_failure_keeps_unwritten_stage(settings,qapp,tmp_path,monkeypatch):
    from ui import identity_settings
    w=settings; path=tmp_path/'not-yet.bin'
    w.start('prepare_backup',str(path),False); drain(w,qapp)
    secret=w.recovery.secret
    monkeypatch.setattr(identity_settings,'QDialog',lambda *args:(_ for _ in ()).throw(RuntimeError('synthetic display failure')))
    w.guard(w.complete_backup)
    assert not path.exists() and w.recovery.secret==secret
    w.acknowledge_backup(secret.hex()); drain(w,qapp)
    assert path.exists() and w.recovery is None and w.service.active().lifecycle=='active'


def test_sqlite_contention_cancel_responsive_and_connection_released(settings,qapp):
    w=settings; s=w.service; owner=s.active()
    with s.vault.connection() as blocker:
        blocker.execute('BEGIN IMMEDIATE')
        w.start('rotate')
        end=time.monotonic()+.1
        while time.monotonic()<end: qapp.processEvents(); time.sleep(.005)
        started=time.monotonic(); w.cancel(); s.lock(); qapp.processEvents()
        assert time.monotonic()-started<1
        blocker.execute('ROLLBACK')
    drain(w,qapp); s.unlock()
    assert s.vault._read(owner.context)['active_key']==owner.key.value
    with s.vault.connection() as db:
        db.execute('BEGIN IMMEDIATE'); db.execute('ROLLBACK')


def test_new_enrollment_receipt_belongs_to_new_account_only(settings,qapp,monkeypatch):
    w=settings; s=w.service; old=s.active()
    monkeypatch.setattr(s.google,'authorize',lambda *args:result('carol'))
    w.address.setText('carol@example.invalid'); w.start_auth(); drain(w,qapp)
    new=s.active()
    assert new.address=='carol@example.invalid' and new.context!=old.context
    assert s.vault._read(new.context)['settings_outcomes'][-1]['operation']=='enroll'
    assert 'settings_outcomes' not in s.vault._read(old.context)


def test_real_sqlite_commit_denial_keeps_transfer_active_and_secret_usable(settings,qapp,tmp_path,monkeypatch,provider):
    import sqlite3
    w=settings; s=w.service; owner=s.active(); path=tmp_path/'denied.bin'
    w.start('prepare_backup',str(path),True); drain(w,qapp); secret=w.recovery.secret
    original=ops.ScopedVault.commit
    def deny(v,db):
        if v.receipt=='transfer_written':
            db.set_authorizer(lambda action,arg,*rest:sqlite3.SQLITE_DENY
                if action==sqlite3.SQLITE_TRANSACTION and arg=='COMMIT' else sqlite3.SQLITE_OK)
        original(v,db)
    monkeypatch.setattr(ops.ScopedVault,'commit',deny)
    w.acknowledge_backup(secret.hex()); drain(w,qapp)
    assert path.exists() and s.vault._read(owner.context)['state']=='active'
    assert 'do not assume rollback' in w.status.text()
    target=Vault.create(tmp_path/'denied-restore.sqlite',s.store,provider)
    try:
        restored=target.restore(path.read_bytes(),secret,result('bob').identity,explicit=True)
        assert target._read(restored)['root']==owner.root
    finally: s.store.delete(target.ident)
