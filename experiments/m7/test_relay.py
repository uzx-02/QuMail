"""Real M5 ciphertext/vault and loopback mTLS; synthetic identities only."""
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
import hashlib
import http.client
import json
import socket
import sqlite3
import threading
import time
import uuid

import pytest
from experiments.m6.test_workflows import prepared, setup, vault, provider, qapp, budget
from experiments.m4.model import Failure as AccountFailure
from experiments.m5.mime import parse_outer
from experiments.m5.model import Failure as MessageFailure
from services.relay.store import Store, Peer, Limits, Failure, Code
from services.relay.client import Client, Recipient
from services.relay.http import Server
from .tls_fixture import contexts


def uid(): return uuid.uuid4().hex


@pytest.fixture
def encrypted(prepared):
    state,work,draft,op = prepared
    v,a,ak,b,bk,access,lease,native = state
    envelope = work.prepare(lease,op,ak,budget())
    return state,work,draft,envelope


@pytest.fixture
def relay(encrypted,tmp_path):
    state,work,draft,envelope = encrypted
    v,a,ak,b,bk,access,lease,native = state
    pa,pb = Peer(a.account.value,a.device.value),Peer(b.account.value,b.device.value)
    store = Store.create(tmp_path/'relay.sqlite')
    return encrypted,store,pa,pb


def test_real_mtls_upload_recipient_decrypt_ack_archive_and_snapshot(relay,tmp_path):
    (state,work,draft,envelope),store,pa,pb = relay
    v,a,ak,b,bk,access,lease,native = state
    ctx,clients,registry,_ = contexts(tmp_path/'tls',[pa,pb])
    with Server(store,ctx,registry) as server:
        sender = Client(access,lease,clients[0],server.server_port,repository=work.repository)
        recipient = Recipient(pb.principal,'bob@example.invalid',envelope.binding.roots[0])
        key = uid()
        uploaded = sender.upload(lease,budget(),envelope,recipient,key)
        assert sender.upload(lease,budget(),envelope,recipient,key)==uploaded
        with pytest.raises(Failure): sender.acquire(lease,budget(),uploaded['id'],uid())
        local = access.select(b)
        receiver = Client(access,local,clients[1],server.server_port)
        acquired = receiver.acquire(local,budget(),uploaded['id'],uid())
        wire = receiver.download(local,budget(),uploaded['id'],acquired['lease'])
        assert wire==envelope.serialized
        opened = work.opener.open(local,bk,wire,v.export_public(a,ak),budget())
        assert opened.signature_valid and opened.verified_confidential
        assert opened.body==draft.body and opened.attachments==draft.attachments
        assert opened.identity_trust=='independently_verified'
        # Snapshot contains encrypted MIME + opaque routing/lease state, no endpoint secrets.
        with closing(sqlite3.connect(store.path)) as db:
            snapshot = '\n'.join(db.iterdump()).encode()
        for secret in (draft.body.encode(),draft.attachments[0].data,b'PRIVATE KEY',b'synthetic-mail-token',b'synthetic-refresh'):
            assert secret not in snapshot and secret not in store.path.read_bytes()
        assert receiver.acknowledge(local,budget(),uploaded['id'],acquired['lease'])=={'state':'consumed'}
        assert receiver.acknowledge(local,budget(),uploaded['id'],acquired['lease'])=={'state':'consumed'}
        with pytest.raises(Failure): receiver.download(local,budget(),uploaded['id'],acquired['lease'])
        with closing(sqlite3.connect(store.path)) as db:
            assert db.execute('SELECT payload FROM objects').fetchone()[0] is None
        original = access.select(a)
        assert work.archive(original,envelope.operation,budget()).body==draft.body
    print('Real endpoint crypto, mTLS upload/download, verified recipient/attachment, archive, redacted backend snapshot, ACK deletion: pass')


def acquire_process(args):
    path,principal,device,object_id,key = args
    try: return Store(path).lease(Peer(principal,device),object_id,key)
    except Failure as error: return error.code.value


def test_128_requests_across_eight_processes_have_one_initial_lease(relay):
    (_,_,_,envelope),store,pa,pb = relay
    obj = store.upload(pa,uid(),pb.principal,envelope.serialized)
    requests = [(str(store.path),pb.principal,uid(),obj['id'],uid()) for _ in range(128)]
    with ProcessPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(acquire_process,requests))
    winners = [i for i,r in enumerate(results) if isinstance(r,dict)]
    assert len(winners)==1
    assert results.count(Code.DENIED.value)==127
    winner = requests[winners[0]]
    assert acquire_process(winner)==results[winners[0]]
    print('128 competing requests; 8 Windows processes/independent Store instances: exactly one initial lease, 127 denied')


def test_relay_ciphertext_tampering_rejected_locally_without_ack(relay):
    (state,work,draft,envelope),store,pa,pb=relay
    v,a,ak,b,bk,access,lease,native=state
    obj=store.upload(pa,uid(),pb.principal,envelope.serialized)
    acquired=store.lease(pb,obj['id'],uid())
    _,armor=parse_outer(envelope.serialized)
    lines=armor.splitlines(keepends=True)
    # Alter an encrypted data line, retaining valid armor/MIME syntax.
    candidates=[i for i,line in enumerate(lines) if len(line.rstrip())>40 and not line.startswith(b'-')]
    i=candidates[len(candidates)//2]
    lines[i]=(b'A' if lines[i][:1]!=b'A' else b'B')+lines[i][1:]
    changed=envelope.serialized.replace(armor,b''.join(lines))
    assert changed!=envelope.serialized
    parse_outer(changed)
    with closing(sqlite3.connect(store.path)) as db:
        db.execute('UPDATE objects SET payload=? WHERE id=?',(changed,obj['id'])); db.commit()
    local=access.select(b)
    with pytest.raises(MessageFailure):
        work.opener.open(local,bk,store.download(pb,obj['id'],acquired['lease']),v.export_public(a,ak),budget())
    with closing(sqlite3.connect(store.path)) as db:
        assert db.execute('SELECT state FROM objects').fetchone()[0]=='leased'
    print('Valid MIME carrying modified real ciphertext: recipient provider rejects; no plaintext result or ACK')


def test_expiry_device_retry_idempotency_and_retention(relay):
    (_,_,_,envelope),store,pa,pb = relay
    now = [1000.]
    store.clock = lambda:now[0]
    key = uid(); obj=store.upload(pa,key,pb.principal,envelope.serialized,ttl=400)
    lid=uid(); leased=store.lease(pb,obj['id'],lid)
    assert leased['until']==1300
    assert store.lease(pb,obj['id'],lid)==leased
    for peer,k in [(Peer(pb.principal,uid()),lid),(pb,uid()),(pa,lid)]:
        with pytest.raises(Failure): store.lease(peer,obj['id'],k)
    with pytest.raises(Failure): store.download(Peer(pb.principal,uid()),obj['id'],leased['lease'])
    now[0]=1299
    assert store.download(pb,obj['id'],leased['lease'])==envelope.serialized
    now[0]=1300
    with pytest.raises(Failure): store.download(pb,obj['id'],leased['lease'])
    store.sweep()
    assert store.upload(pa,key,pb.principal,envelope.serialized,ttl=400)['state']=='expired'
    with closing(sqlite3.connect(store.path)) as db:
        assert db.execute('SELECT payload FROM objects').fetchone()[0] is None
    with pytest.raises(Failure) as error: store.upload(pa,key,pb.principal,envelope.serialized,ttl=401)
    assert error.value.code is Code.CONFLICT
    short=store.upload(pa,uid(),pb.principal,envelope.serialized,ttl=2)
    assert store.lease(pb,short['id'],uid())['until']==1302
    now[0]=1302
    with pytest.raises(Failure): store.lease(pb,short['id'],uid())


def test_expiry_checked_after_waiting_for_database_lock(relay):
    (_,_,_,envelope),store,pa,pb = relay
    now=[10.]; store.clock=lambda:now[0]
    obj=store.upload(pa,uid(),pb.principal,envelope.serialized,ttl=1)
    with closing(sqlite3.connect(store.path)) as blocker:
        blocker.execute('BEGIN IMMEDIATE')
        started=threading.Event()
        def waiting():
            started.set()
            return store.lease(pb,obj['id'],uid())
        with ThreadPoolExecutor(1) as pool:
            pending=pool.submit(waiting); assert started.wait(1)
            now[0]=11.; blocker.commit()
            with pytest.raises(Failure): pending.result()


def test_expiry_inside_lease_transaction_rolls_back_claim(relay):
    (_,_,_,envelope),store,pa,pb=relay
    store.clock=lambda:100.
    obj=store.upload(pa,uid(),pb.principal,envelope.serialized,ttl=1)
    moments=iter((100.,101.))
    store.clock=lambda:next(moments)
    with pytest.raises(Failure): store.lease(pb,obj['id'],uid())
    with closing(sqlite3.connect(store.path)) as db:
        assert db.execute('SELECT state,lease_id FROM objects').fetchone()==('ready',None)


def test_global_bytes_and_tombstone_quotas(relay):
    (_,_,_,envelope),store,pa,pb=relay
    store.limits=Limits(total_bytes=len(envelope.serialized)-1)
    with pytest.raises(Failure) as error: store.upload(pa,uid(),pb.principal,envelope.serialized)
    assert error.value.code is Code.LIMIT
    store.limits=Limits(total_records=1)
    obj=store.upload(pa,uid(),pb.principal,envelope.serialized)
    leased=store.lease(pb,obj['id'],uid()); store.acknowledge(pb,obj['id'],leased['lease'])
    with pytest.raises(Failure): store.upload(pa,uid(),pb.principal,envelope.serialized)


def test_simultaneous_ack_download_and_restart(relay):
    (_,_,_,envelope),store,pa,pb=relay
    obj=store.upload(pa,uid(),pb.principal,envelope.serialized)
    acquired=store.lease(pb,obj['id'],uid())
    reloaded=Store(store.path)
    assert reloaded.download(pb,obj['id'],acquired['lease'])==envelope.serialized
    def get():
        try: return reloaded.download(pb,obj['id'],acquired['lease'])
        except Failure as error: return error.code
    with ThreadPoolExecutor(8) as pool:
        futures=[pool.submit(get) for _ in range(16)]
        acks=[pool.submit(store.acknowledge,pb,obj['id'],acquired['lease']) for _ in range(8)]
        assert all(f.result() in (envelope.serialized,Code.DENIED) for f in futures)
        assert all(f.result()=={'state':'consumed'} for f in acks)
    with pytest.raises(Failure): get_result=reloaded.download(pb,obj['id'],acquired['lease'])


def test_quotas_malformed_profile_and_backend_outage_fail_closed(relay,tmp_path):
    (_,_,_,envelope),store,pa,pb=relay
    store.limits=Limits(principal_objects=1)
    store.upload(pa,uid(),pb.principal,envelope.serialized)
    with pytest.raises(Failure) as error: store.upload(pa,uid(),pb.principal,envelope.serialized)
    assert error.value.code is Code.LIMIT
    for bad in (b'plaintext',envelope.serialized.replace(b'Encrypted message',b'Private subject'),envelope.serialized[:-40]):
        with pytest.raises(Failure): store.upload(pa,uid(),pb.principal,bad)
    for ttl in (0,86401,True,'3600'):
        with pytest.raises(Failure): store.upload(pa,uid(),pb.principal,envelope.serialized,ttl)
    # No fallback when a once-ready durable store disappears.
    store.path.rename(tmp_path/'offline.sqlite')
    with pytest.raises(Failure) as error: store.sweep()
    assert error.value.code is Code.BACKEND and not store.path.exists()
    with pytest.raises(Failure): Store(tmp_path/'absent.sqlite')


def test_tls_auth_registry_and_authorization_header_rejection(relay,tmp_path):
    (_,_,_,envelope),store,pa,pb=relay
    ctx,clients,registry,anonymous=contexts(tmp_path/'tls',[pa,pb,Peer(uid(),uid())])
    registry={key:value for key,value in registry.items() if value in (pa,pb)}
    with Server(store,ctx,registry) as server:
        conn=http.client.HTTPSConnection('127.0.0.1',server.server_port,context=anonymous,timeout=2)
        with pytest.raises((OSError,http.client.HTTPException)):
            conn.request('POST','/v1/objects','{}',{'Content-Type':'application/json'}); conn.getresponse()
        conn.close()
        for context,headers,status in [(clients[2],{},403),(clients[0],{'Authorization':'Bearer synthetic-not-google'},400)]:
            conn=http.client.HTTPSConnection('127.0.0.1',server.server_port,context=context,timeout=2)
            conn.request('POST','/v1/objects','{}',{'Content-Type':'application/json',**headers})
            response=conn.getresponse(); assert response.status==status; response.read(); conn.close()


def test_http_limits_duplicates_outage_and_slow_client(relay,tmp_path):
    (_,_,_,envelope),store,pa,pb=relay
    ctx,clients,registry,_=contexts(tmp_path/'tls',[pa,pb])
    with Server(store,ctx,registry) as server:
        def raw(request):
            with socket.create_connection(('127.0.0.1',server.server_port),timeout=7) as sock:
                with clients[0].wrap_socket(sock,server_hostname='127.0.0.1') as tls:
                    tls.sendall(request)
                    return tls.recv(4096)
        prefix=b'POST /v1/objects HTTP/1.0\r\nContent-Type: application/json\r\n'
        assert b' 429 ' in raw(prefix+b'Content-Length: 9999999\r\n\r\n')
        assert b' 400 ' in raw(prefix+b'Content-Length: 2\r\nContent-Length: 2\r\n\r\n{}')
        body=b'{"key":"one","key":"two"}'
        assert b' 400 ' in raw(prefix+b'Content-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body)
        assert raw(prefix+b'X-Large: '+b'a'*9000+b'\r\n\r\n')==b''
        started=time.monotonic()
        assert raw(b'POST /v1/objects HTTP/1.0\r\nX-Incomplete: ')==b''
        assert 4 <= time.monotonic()-started < 7  # Only this controlled phase, not all OS calls.
        # Stop the background sweeper before removing its database. Windows
        # correctly prohibits renaming a file while that connection is open.
        server.stop.set(); server.sweeper.join()
        store.path.rename(tmp_path/'offline.sqlite')
        # Authenticated valid lease request exercises unavailable DB and returns 503.
        body=json.dumps({'key':uid()}).encode()
        request=(f'POST /v1/objects/{uid()}/leases HTTP/1.0\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n').encode()+body
        assert b' 503 ' in raw(request)


def test_switch_cancel_and_late_result_no_cross_account_publication(relay,tmp_path):
    (state,work,draft,envelope),store,pa,pb=relay
    v,a,ak,b,bk,access,lease,native=state
    ctx,clients,registry,_=contexts(tmp_path/'tls',[pa,pb])
    committed=threading.Event(); release=threading.Event()
    upload=store.upload
    def delayed(*args,**kwargs):
        result=upload(*args,**kwargs); committed.set(); release.wait(2); return result
    store.upload=delayed
    with Server(store,ctx,registry) as server:
        client=Client(access,lease,clients[0],server.server_port,repository=work.repository)
        recipient=Recipient(pb.principal,'bob@example.invalid',envelope.binding.roots[0]); key=uid()
        with ThreadPoolExecutor(1) as pool:
            pending=pool.submit(client.upload,lease,budget(),envelope,recipient,key)
            assert committed.wait(2)
            other=access.select(b); release.set()
            with pytest.raises(AccountFailure): pending.result()
        with pytest.raises(Failure): client.upload(other,budget(),envelope,recipient,key)
        # Side effect is retained, never called rolled back; same owner/key discovers it.
        assert upload(pa,key,pb.principal,envelope.serialized)['state']=='ready'
        with closing(sqlite3.connect(store.path)) as db: assert db.execute('SELECT count(*) FROM objects').fetchone()[0]==1


def test_upload_rechecks_current_vault_trust_and_frozen_bytes(relay,tmp_path):
    (state,work,draft,envelope),store,pa,pb=relay
    v,a,ak,b,bk,access,lease,native=state
    ctx,clients,registry,_=contexts(tmp_path/'tls',[pa,pb])
    with Server(store,ctx,registry) as server:
        client=Client(access,lease,clients[0],server.server_port,repository=work.repository)
        recipient=Recipient(pb.principal,'bob@example.invalid',envelope.binding.roots[0])
        with pytest.raises(Failure):
            client.upload(lease,budget(),replace(envelope,serialized=envelope.serialized+b'bad'),recipient,uid())
        with v.transaction(a) as data: data['contacts']['bob@example.invalid']['state']='changed_blocked'
        with pytest.raises(AccountFailure): client.upload(lease,budget(),envelope,recipient,uid())
        with closing(sqlite3.connect(store.path)) as db:
            assert db.execute('SELECT count(*) FROM objects').fetchone()[0]==0
