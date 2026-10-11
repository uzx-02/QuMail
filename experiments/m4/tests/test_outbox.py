"""Real provider/SQLite/Windows store; authorization and transports are fixtures."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import base64
import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import pytest
from experiments.m3.tests.test_m3 import provider, vault, enroll, pin, synthetic_identity, ROOT
from experiments.m3.types import EmailAddress, BoundaryError, Code
from experiments.m3.vault import Vault, PROFILE
from experiments.m4.model import *
from experiments.m4.services import PrepareMessage, SubmitOutbox, deadline
from experiments.m4.vault_adapter import VaultOutbox, ProviderFixtureBuilder
from experiments.m4.transports import SimulatedTransport


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def reject(*args, **kwargs): raise AssertionError('M4 must not contact a network')
    monkeypatch.setattr(socket.socket, 'connect', reject)
    monkeypatch.setattr(socket.socket, 'connect_ex', reject)
    monkeypatch.setattr(socket, 'create_connection', reject)


@pytest.fixture
def setup(vault):
    a, ak = enroll(vault); b, bk = enroll(vault, 'bob')
    address = EmailAddress('bob@example.invalid')
    pin(vault, a, address, vault.export_public(b, bk))
    vault.store_oauth(a, synthetic_identity(), dict(access_token='synthetic-test-only', expiry=int(time.time())+3600))
    access = AccountAccess(); lease = access.select(a)
    repo = VaultOutbox(vault, access)
    return vault, a, ak, b, bk, address, access, lease, repo


def prepared(setup, builder=None):
    v, a, ak, b, bk, address, access, lease, repo = setup
    service = PrepareMessage(repo, builder or ProviderFixtureBuilder())
    op = service.draft(lease, b'M4 disposable private draft')
    envelope = service.prepare(lease, op, ak, (address,), PROFILE)
    return op, envelope


def test_provider_generated_persisted_envelope_and_restart(setup):
    v, a, ak, b, bk, address, access, lease, repo = setup
    op, envelope = prepared(setup)
    assert v.open_for_test(b, bk, v.export_public(a, ak), envelope.serialized) == b'M4 disposable private draft'
    assert envelope.message_id == f'<{op.value}@qumail.invalid>'
    with pytest.raises(FrozenInstanceError): envelope.serialized = b'changed'
    restarted = VaultOutbox(Vault(v.path, v.store, v.provider), access)
    transport = SimulatedTransport()
    submit = SubmitOutbox(restarted, transport)
    assert submit.envelope(lease, op) == envelope
    assert submit.submit(lease, op).state is State.ACCEPTED
    assert transport.calls == [envelope]
    row = v._read(a)['m4_outbox_v1'][op.value]
    assert 'draft' not in row and 'content_key' not in row
    assert row['prepared']['archive']['sender_key'] == ak.value
    assert len(row['prepared']['archive']['recipient_public']) == 1
    assert row['attempts'][0]['digest'] == envelope.digest


def test_draft_encrypted_and_no_submit_before_preparation(setup):
    v, a, ak, b, bk, address, access, lease, repo = setup
    plain = b'unique private draft must not appear on disk'
    op = PrepareMessage(repo, ProviderFixtureBuilder()).draft(lease, plain)
    transport = SimulatedTransport(); submit = SubmitOutbox(repo, transport)
    with pytest.raises(Failure): submit.submit(lease, op)
    assert not transport.calls
    raw = v.path.read_bytes()
    assert plain not in raw and base64.b64encode(plain) not in raw and address.value.encode() not in raw
    assert b'synthetic-test-only' not in raw
    assert submit.inspect(lease, op).state is State.DRAFT


@pytest.mark.parametrize('kind', ['unknown', 'unverified', 'changed', 'revoked', 'expired', 'bad-profile', 'wrong-key', 'locked'])
def test_prerequisites_fail_closed_zero_transport(setup, kind):
    v, a, ak, b, bk, address, access, lease, repo = setup
    prepare = PrepareMessage(repo, ProviderFixtureBuilder())
    op = prepare.draft(lease, b'disposable draft')
    profile = PROFILE
    if kind == 'unknown': address = EmailAddress('unknown@example.invalid')
    elif kind == 'bad-profile': profile = 'weak-or-unknown'
    elif kind == 'wrong-key': ak = bk
    elif kind == 'locked': access.select(None)
    else:
        with v.transaction(a) as data:
            if kind == 'expired': data['keys'][ak.value]['expires'] = 1
            else: data['contacts'][address.value]['state'] = {'unverified':'unverified','changed':'changed_blocked','revoked':'revoked'}[kind]
    transport = SimulatedTransport()
    with pytest.raises(Failure): prepare.prepare(lease, op, ak, (address,), profile)
    with pytest.raises(Failure): SubmitOutbox(repo, transport).submit(lease, op)
    assert not transport.calls
    assert v._read(a)['m4_outbox_v1'][op.value]['state'] == 'Draft'


def test_provider_and_output_failure_retains_encrypted_draft(setup):
    class Broken:
        def build(self, *args): raise RuntimeError('sensitive backend diagnostics')
    class Oversize:
        def build(self, *args): return b'x' * (MAX_ENVELOPE + 1)
    *_, lease, repo = setup
    for builder in [Broken(), Oversize()]:
        prepare = PrepareMessage(repo, builder)
        op = prepare.draft(lease, b'draft')
        with pytest.raises(Failure) as error: prepare.prepare(lease, op, setup[2], (setup[5],), PROFILE)
        assert 'sensitive' not in str(error.value)
        assert SubmitOutbox(repo, SimulatedTransport()).inspect(lease, op).state is State.DRAFT


@contextmanager
def deny_commit(vault, target=1):
    original = vault.connection
    count = 0
    @contextmanager
    def connection():
        nonlocal count
        count += 1
        with original() as db:
            if count == target:
                db.set_authorizer(lambda action, arg, *rest: sqlite3.SQLITE_DENY
                    if action == sqlite3.SQLITE_TRANSACTION and arg == 'COMMIT' else sqlite3.SQLITE_OK)
            yield db
    vault.connection = connection
    try: yield
    finally: vault.connection = original


def test_preparation_commit_denied_no_ready_record(setup):
    v, a, ak, b, bk, address, access, lease, repo = setup
    service = PrepareMessage(repo, ProviderFixtureBuilder()); op = service.draft(lease, b'draft')
    with deny_commit(v):
        with pytest.raises(Failure): service.prepare(lease, op, ak, (address,), PROFILE)
    transport = SimulatedTransport()
    with pytest.raises(Failure): SubmitOutbox(repo, transport).submit(lease, op)
    assert not transport.calls
    assert v._read(a)['m4_outbox_v1'][op.value]['state'] == 'Draft'


def test_real_sqlite_full_draft_has_no_operation(setup):
    v, a, ak, b, bk, address, access, lease, repo = setup
    original = v.connection
    @contextmanager
    def full():
        with original() as db:
            pages = db.execute('PRAGMA page_count').fetchone()[0]
            db.execute(f'PRAGMA max_page_count={pages}')
            yield db
    v.connection = full
    try:
        with pytest.raises(Failure): PrepareMessage(repo, ProviderFixtureBuilder()).draft(lease, os.urandom(MAX_DRAFT))
    finally: v.connection = original
    assert not v._read(a).get('m4_outbox_v1')


@pytest.mark.parametrize('phase', ['credential', 'intent_commit', 'result_commit'])
def test_submission_failure_boundaries(setup, phase):
    v, a, ak, b, bk, address, access, lease, repo = setup
    op, envelope = prepared(setup)
    transport = SimulatedTransport(); submit = SubmitOutbox(repo, transport)
    if phase == 'credential':
        with v.transaction(a) as data: del data['oauth']
        with pytest.raises(Failure) as error: submit.submit(lease, op)
        assert error.value.code is Error.CREDENTIAL
    else:
        with deny_commit(v, 1 if phase == 'intent_commit' else 2):
            if phase == 'intent_commit':
                with pytest.raises(Failure): submit.submit(lease, op)
            else: assert submit.submit(lease, op).state is State.UNKNOWN
    assert len(transport.calls) == (1 if phase == 'result_commit' else 0)
    if phase == 'result_commit':
        assert submit.inspect(lease, op).state is State.SUBMITTING
        assert submit.recover(lease) == (op,)
        assert submit.inspect(lease, op).state is State.UNKNOWN
    else: assert submit.inspect(lease, op).state is State.PREPARED
    assert submit.envelope(lease, op) == envelope


@pytest.mark.parametrize('outcome', list(Outcome))
def test_delivery_semantics_explicit_retry_and_receipt_failure(setup, outcome):
    *_, lease, repo = setup
    op, envelope = prepared(setup)
    transport = SimulatedTransport(outcome); submit = SubmitOutbox(repo, transport)
    got = submit.submit(lease, op)
    assert got.state is {Outcome.ACCEPTED:State.ACCEPTED, Outcome.REJECTED:State.FAILED, Outcome.UNKNOWN:State.UNKNOWN}[outcome]
    def fail(receipt): raise OSError('disk full exporting optional receipt')
    assert submit.export_receipt(lease, op, fail) is False
    assert submit.inspect(lease, op) == got
    with pytest.raises(Failure): submit.submit(lease, op)
    if outcome is Outcome.ACCEPTED:
        with pytest.raises(Failure): submit.retry(lease, op, acknowledge_duplicate_risk=True)
    else:
        if outcome is Outcome.UNKNOWN:
            with pytest.raises(Failure) as error: submit.retry(lease, op)
            assert error.value.code is Error.DUPLICATE
        submit.retry(lease, op, acknowledge_duplicate_risk=True)
        transport.outcome = Outcome.ACCEPTED
        assert submit.submit(lease, op).state is State.ACCEPTED
        assert transport.calls == [envelope, envelope]


def test_transport_exception_invalid_result_and_retry_limit(setup):
    class Bad(SimulatedTransport):
        def submit(self, envelope, *args):
            self.calls.append(envelope)
            if len(self.calls) == 1: raise TimeoutError('after simulated DATA acceptance')
            return 'not a typed result'
    *_, lease, repo = setup
    op, envelope = prepared(setup); transport = Bad(); submit = SubmitOutbox(repo, transport)
    for n in range(MAX_ATTEMPTS):
        assert submit.submit(lease, op).state is State.UNKNOWN
        if n < MAX_ATTEMPTS-1: submit.retry(lease, op, acknowledge_duplicate_risk=True)
    with pytest.raises(Failure) as error: submit.retry(lease, op, acknowledge_duplicate_risk=True)
    assert error.value.code is Error.LIMIT and transport.calls == [envelope]*MAX_ATTEMPTS


def test_concurrent_submission_and_active_recovery_no_duplicate(setup):
    class Blocking(SimulatedTransport):
        def submit(self, *args):
            value = super().submit(*args); entered.set(); assert release.wait(4); return value
    *_, lease, repo = setup
    op, _ = prepared(setup); entered = threading.Event(); release = threading.Event()
    transport = Blocking(); submit = SubmitOutbox(repo, transport)
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(submit.submit, lease, op); assert entered.wait(4)
        second = pool.submit(submit.submit, lease, op)
        recovery = pool.submit(submit.recover, lease)
        release.set()
        assert first.result().state is State.ACCEPTED
        with pytest.raises(Failure): second.result()
        assert recovery.result() == ()
    assert len(transport.calls) == 1


def test_account_switch_cancel_deadline_and_cross_account(setup):
    v, a, ak, b, bk, address, access, lease, repo = setup
    op, _ = prepared(setup); transport = SimulatedTransport(); submit = SubmitOutbox(repo, transport)
    with pytest.raises(Failure): submit.submit(lease, op, until=time.monotonic()-1)
    other = access.select(b)
    for token in (lease, other):
        with pytest.raises(Failure): submit.submit(token, op)
    current = access.select(a); current.cancelled.set()
    with pytest.raises(Failure): submit.submit(current, op)
    assert not transport.calls


def test_switch_during_transport_preserves_original_account_uncertainty(setup):
    v, a, ak, b, bk, address, access, lease, repo = setup
    class Switch(SimulatedTransport):
        def submit(self, *args):
            super().submit(*args); access.select(b); return Outcome.UNKNOWN
    op, _ = prepared(setup); transport = Switch()
    assert SubmitOutbox(repo, transport).submit(lease, op).state is State.UNKNOWN
    assert v._read(a)['m4_outbox_v1'][op.value]['state'] == 'Unknown'
    assert not v._read(b).get('m4_outbox_v1')
    assert len(transport.calls) == 1


def test_changed_contact_after_prepare_blocks_submission_and_retry(setup):
    v, a, ak, b, bk, address, access, lease, repo = setup
    op, envelope = prepared(setup)
    replacement = v.provider.call('generate', address=address.value)
    v.import_contact(a, address, bytes(replacement['public']))
    transport = SimulatedTransport(); submit = SubmitOutbox(repo, transport)
    with pytest.raises(Failure): submit.submit(lease, op)
    assert not transport.calls and submit.envelope(lease, op) == envelope


def test_same_root_rotated_recipient_subkeys_block_old_envelope(setup):
    v, a, ak, b, bk, address, access, lease, repo = setup
    op, envelope = prepared(setup)
    rotated = v.rotate(b, bk)
    v.import_contact(a, address, v.export_public(b, rotated))
    transport = SimulatedTransport(); submit = SubmitOutbox(repo, transport)
    with pytest.raises(Failure) as error: submit.submit(lease, op)
    assert error.value.code is Error.POLICY
    assert not transport.calls and submit.envelope(lease, op) == envelope


def test_no_real_transport_no_multi_recipient_format_and_bounds(setup):
    *_, lease, repo = setup
    transport = SimulatedTransport(); transport.simulation_only = False
    with pytest.raises(Failure): SubmitOutbox(repo, transport)
    service = PrepareMessage(repo, ProviderFixtureBuilder())
    with pytest.raises(Failure): service.draft(lease, b'x'*(MAX_DRAFT+1))
    for _ in range(MAX_OPERATIONS): service.draft(lease, b'small')
    with pytest.raises(Failure): service.draft(lease, b'over bound')


def test_every_recipient_verified_single_recipient_fixture_limit(setup):
    v, a, ak, b, bk, address, access, lease, repo = setup
    service = PrepareMessage(repo, ProviderFixtureBuilder())
    op = service.draft(lease, b'fixture')
    third, tk = enroll(v, 'third'); other = EmailAddress('third@example.invalid')
    with pytest.raises(Failure): service.prepare(lease, op, ak, (address, other), PROFILE)
    pin(v, a, other, v.export_public(third, tk))
    with pytest.raises(Failure) as error: service.prepare(lease, op, ak, (address, other), PROFILE)
    assert error.value.code is Error.POLICY
    assert SubmitOutbox(repo, SimulatedTransport()).inspect(lease, op).state is State.DRAFT


def test_cancellation_during_preparation_and_after_intent(setup):
    v, a, ak, b, bk, address, access, lease, repo = setup
    class CancelBuilder(ProviderFixtureBuilder):
        def build(self, *args):
            value = super().build(*args); lease.cancelled.set(); return value
    prepare = PrepareMessage(repo, CancelBuilder()); op = prepare.draft(lease, b'draft')
    with pytest.raises(Failure): prepare.prepare(lease, op, ak, (address,), PROFILE)
    assert v._read(a)['m4_outbox_v1'][op.value]['state'] == 'Draft'
    lease = access.select(a)
    PrepareMessage(repo, ProviderFixtureBuilder()).prepare(lease, op, ak, (address,), PROFILE)
    class CancelAfterCommit(VaultOutbox):
        @contextmanager
        def transaction(self, *args):
            with super().transaction(*args) as account: yield account
            lease.cancelled.set()
    transport = SimulatedTransport()
    assert SubmitOutbox(CancelAfterCommit(v, access), transport).submit(lease, op).state is State.UNKNOWN
    assert not transport.calls
    lease = access.select(a)
    assert SubmitOutbox(repo, transport).recover(lease) == (op,)


def test_reconciliation_never_resubmits(setup):
    *_, lease, repo = setup
    op, envelope = prepared(setup); transport = SimulatedTransport(Outcome.UNKNOWN)
    submit = SubmitOutbox(repo, transport); submit.submit(lease, op)
    class Observer:
        simulation_only = True
        value = Outcome.REJECTED
        def lookup(self, incoming, attempt):
            assert incoming == envelope and attempt == 1
            return self.value
    observer = Observer()
    assert submit.reconcile(lease, op, observer).state is State.UNKNOWN
    observer.value = Outcome.ACCEPTED
    assert submit.reconcile(lease, op, observer).state is State.ACCEPTED
    assert len(transport.calls) == 1


def test_opt_in_harness_and_disposable_cleanup():
    command = [sys.executable, '-m', 'experiments.m4.harness']
    absent = subprocess.run(command, capture_output=True, text=True, timeout=20)
    assert absent.returncode == 2 and '--simulate is required' in absent.stderr
    before = set((ROOT/'tmp').glob('m4-demo-*'))
    run = subprocess.run(command+['--simulate'], capture_output=True, text=True, timeout=20)
    assert run.returncode == 0, 'disposable harness failed; inspect private local output'
    report = json.loads(run.stdout)
    assert report['restart'] == 'Unknown' and report['final'] == 'Accepted'
    assert report['byte_identical_retry'] and report['disposable_credentials_cleaned']
    assert set((ROOT/'tmp').glob('m4-demo-*')) == before


@pytest.mark.parametrize('mode,point,expected', [
    ('prepare','1-before','Draft'), ('prepare','1-after','Prepared'),
    ('submit','1-before','Prepared'), ('submit','1-after','Unknown'),
    ('submit','transport-before','Unknown'), ('submit','transport-after','Unknown'),
    ('submit','2-before','Unknown'), ('submit','2-after','Accepted'),
    ('export','receipt-before','Accepted'), ('export','receipt-after','Accepted'),
])
def test_abrupt_child_termination_restart_exact_bytes(setup, tmp_path, mode, point, expected):
    v, a, ak, b, bk, address, access, lease, repo = setup
    service = PrepareMessage(repo, ProviderFixtureBuilder())
    op = service.draft(lease, b'child disposable draft')
    envelope = None
    if mode in ('submit','export'): envelope = service.prepare(lease, op, ak, (address,), PROFILE)
    if mode == 'export': SubmitOutbox(repo, SimulatedTransport()).submit(lease, op)
    marker = tmp_path/'boundary.txt'
    request = dict(path=str(v.path), account=a.account.value, device=a.device.value, issuer=a.issuer,
        subject=a.subject, key=ak.value, recipient=address.value, operation=op.value,
        mode=mode, point=point, marker=str(marker))
    child = subprocess.Popen([sys.executable, '-m', 'experiments.m4.tests.crash_worker'],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        child.stdin.write(json.dumps(request).encode()); child.stdin.close()
        until = time.monotonic()+20
        while not marker.exists() and child.poll() is None and time.monotonic()<until: time.sleep(.02)
        assert marker.exists(), 'child did not reach requested boundary'
        child.kill(); child.wait(timeout=5)
    finally:
        if child.poll() is None: child.kill(); child.wait(timeout=5)
    reopened = VaultOutbox(Vault(v.path, v.store, v.provider), access)
    transport = SimulatedTransport(); submit = SubmitOutbox(reopened, transport)
    submit.recover(lease)
    assert submit.inspect(lease, op).state.value == expected
    assert not transport.calls  # Restart never resubmits.
    if envelope is not None: assert submit.envelope(lease, op) == envelope
    if expected == 'Unknown':
        with pytest.raises(Failure): submit.submit(lease, op)
        with pytest.raises(Failure): submit.retry(lease, op)
        submit.retry(lease, op, acknowledge_duplicate_risk=True)
        assert submit.submit(lease, op).state is State.ACCEPTED
        assert transport.calls == [envelope]
