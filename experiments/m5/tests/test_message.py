"""Disposable actual native crypto, Windows vault and loopback SMTP qualification."""
from dataclasses import replace
from email.utils import format_datetime
from datetime import datetime,timezone
import hashlib
import threading
import time
from pathlib import Path
import pytest
from experiments.m3.tests.test_m3 import provider,vault,enroll,pin
from experiments.m3.types import EmailAddress,BoundaryError
from experiments.m3.vault import Vault
from experiments.m4.model import AccountAccess,State,Failure as OutboxFailure
from experiments.m4.services import SubmitOutbox
from experiments.m4.smtp_transport import LoopbackSMTP
from experiments.m4.smtp_fixture import SMTPServer,SyntheticResolver
from experiments.m5.provider import Provider
from experiments.m5.model import *
from experiments.m5.services import Compose,OpenMessage,decode_draft
from experiments.m5 import mime,legacy

ROOT=Path(__file__).resolve().parents[3]


def budget(lease): return Budget(lease.cancelled,time.monotonic()+30)


@pytest.fixture
def setup(vault):
    accounts=[enroll(vault,name) for name in ('alice','bob','carol','wrong')]
    for ctx,key in accounts[:3]:
        for other,otherkey in accounts[:3]:
            if other!=ctx: pin(vault,ctx,EmailAddress(vault._read(other)['address']),vault.export_public(other,otherkey))
    access=AccountAccess(); lease=access.select(accounts[0][0])
    native=Provider(ROOT/'tmp/m2/target/debug/qumail-m5-provider.exe')
    compose=Compose(vault,access,native)
    draft=Draft(('bob@example.invalid',),('carol@example.invalid',),'Private fixture subject','Disposable body',
        (Attachment('example.txt','text/plain',b'disposable attachment'),),'<prior@example.invalid>',('<prior@example.invalid>',))
    return vault,accounts,access,lease,native,compose,draft


def prepared(setup,draft=None):
    v,accounts,access,lease,native,compose,default=setup
    op=compose.draft(lease,draft or default,budget(lease))
    envelope=compose.prepare(lease,op,accounts[0][1],budget(lease))
    return op,envelope


def crafted(setup,raw,draft=None,op='seal',recipients=None):
    v,accounts,access,lease,native,compose,default=setup
    draft=draft or default
    a,ak=accounts[0]; signer=v.key(v._read(a),a,ak)
    publics=recipients or [v.export_public(ctx,k) for ctx,k in accounts[:3]]
    armor=native.call(op,budget(lease),certificate=bytes(signer['secret']),recipients=publics,data=raw)['data']
    return mime.build_outer('alice@example.invalid',draft,'<fixed@example.invalid>',DATE,armor)


DATE=format_datetime(datetime(2026,10,12,0,0,0,tzinfo=timezone.utc))


def test_multi_recipient_archive_loopback_retry_and_replay(setup,tmp_path):
    v,accounts,access,lease,native,compose,draft=setup
    op,envelope=prepared(setup)
    assert draft.subject.encode() not in envelope.serialized
    with SMTPServer(tmp_path/'tls','final-loss') as server:
        submit=SubmitOutbox(compose.repository,LoopbackSMTP('127.0.0.1',server.port,SyntheticResolver(lease.context),fixture_context=server.client_context))
        assert submit.submit(lease,op).state is State.UNKNOWN
        with pytest.raises(OutboxFailure): submit.retry(lease,op)
        submit.retry(lease,op,acknowledge_duplicate_risk=True); server.mode='success'
        assert submit.submit(lease,op).state is State.ACCEPTED
        assert server.digests==[envelope.digest,envelope.digest]
        assert submit.export_receipt(lease,op,lambda r:(_ for _ in ()).throw(OSError())) is False
        assert submit.inspect(lease,op).state is State.ACCEPTED
    sender=v.export_public(*accounts[0]); opened=OpenMessage(v,access,native)
    for i,(ctx,key) in enumerate(accounts[:3]):
        local=access.select(ctx)
        message=opened.open(local,key,envelope.serialized,sender,budget(local))
        assert message.verified_confidential and message.replay is Replay.FRESH and message.archive==(i==0)
        assert message.body==draft.body and message.attachments==draft.attachments and not message.mismatches
        assert message.subject==draft.subject and message.in_reply_to==draft.in_reply_to
        reopened=OpenMessage(Vault(v.path,v.store,v.provider),access,native)
        assert reopened.open(local,key,envelope.serialized,sender,budget(local)).replay is Replay.DUPLICATE
    print('E2E_OBSERVATION two recipients + sender archive decrypted; TLS payload matched on retry; replay persisted')


@pytest.mark.parametrize('direction',['sequoia-to-rpgp','rpgp-to-sequoia'])
def test_independent_exchange_exact_m3_subkey_model(setup,direction):
    v,accounts,access,lease,native,compose,draft=setup
    inner=mime.build_inner('alice@example.invalid',draft,'<fixed@example.invalid>',DATE)
    wire=crafted(setup,inner,op='seal' if direction=='sequoia-to-rpgp' else 'peer_seal')
    outer,armor=mime.parse_outer(wire)
    sender=v.export_public(*accounts[0])
    for ctx,key in accounts[:3]:
        if direction=='sequoia-to-rpgp':
            secret=v.key(v._read(ctx),ctx,key)
            result=native.call('peer_open',budget(lease),certificate=bytes(secret['secret']),sender=sender,data=armor)
            assert result['verified'] and result['data']==inner
        else:
            local=access.select(ctx)
            result=OpenMessage(v,access,native).open(local,key,wire,sender,budget(local))
            assert result.verified_confidential
    print('INDEPENDENT_CRYPTO_OBSERVATION',direction,'three decryptors; shared MIME/armor/policy, not independent mail clients')


@pytest.mark.parametrize('state',['unverified','changed_blocked','expired','revoked','missing'])
def test_every_recipient_blocks_preparation(setup,state):
    v,accounts,access,lease,native,compose,draft=setup
    with v.transaction(lease.context) as data:
        if state=='missing': del data['contacts']['carol@example.invalid']
        else: data['contacts']['carol@example.invalid']['state']=state
    op=compose.draft(lease,draft,budget(lease))
    with pytest.raises((Failure,OutboxFailure,BoundaryError)): compose.prepare(lease,op,accounts[0][1],budget(lease))
    with compose.repository.transaction(lease,time.monotonic()+5) as account:
        assert account.row(op)['state']=='Draft' and 'prepared' not in account.row(op)


@pytest.mark.parametrize('case',['wrong-key','wrong-signer','tamper','truncate','unintended','false-from','unsupported-profile'])
def test_no_verified_output_on_invalid_message(setup,case):
    v,accounts,access,lease,native,compose,draft=setup
    _,envelope=prepared(setup); wire=envelope.serialized
    recipient=accounts[1]; sender=v.export_public(*accounts[0])
    if case=='wrong-key': recipient=accounts[3]
    if case=='wrong-signer': sender=v.export_public(*accounts[3])
    if case=='truncate': wire=wire[:-80]
    if case=='tamper':
        outer,armor=mime.parse_outer(wire)
        # Mutate armored packet data while retaining MIME framing; provider rejects.
        position=armor.index(b'\r\n\r\n')+4
        altered=armor[:position]+(b'A' if armor[position:position+1]!=b'A' else b'B')+armor[position+1:]
        wire=wire.replace(armor.rstrip(b'\r\n'),altered.rstrip(b'\r\n'))
    if case in ('unintended','false-from','unsupported-profile'):
        changed=replace(draft,to=('wrong@example.invalid',),cc=(),archive=False) if case=='unintended' else draft
        inner=mime.build_inner('wrong@example.invalid' if case=='false-from' else 'alice@example.invalid',changed,'<fixed@example.invalid>',DATE)
        if case=='unsupported-profile': inner=inner.replace(PROFILE.encode(),b'UNSUPPORTED')
        wire=crafted(setup,inner,draft=changed)
    local=access.select(recipient[0])
    with pytest.raises((Failure,OutboxFailure,BoundaryError)):
        OpenMessage(v,access,native).open(local,recipient[1],wire,sender,budget(local))
    assert not v._read(recipient[0]).get('m5_seen_v1')


def test_outer_discrepancy_trust_and_conflict_are_distinct(setup):
    v,accounts,access,lease,native,compose,draft=setup
    inner=mime.build_inner('alice@example.invalid',draft,'<fixed@example.invalid>',DATE)
    wire=crafted(setup,inner)
    changed=crafted(setup,mime.build_inner('alice@example.invalid',replace(draft,body='Different authenticated body'),'<fixed@example.invalid>',DATE))
    sender=v.export_public(*accounts[0]); b,bk=accounts[1]; local=access.select(b)
    opener=OpenMessage(v,access,native)
    with v.transaction(b) as data: data['contacts']['alice@example.invalid']['state']='unverified'
    result=opener.open(local,bk,wire.replace(b'Subject: Encrypted message',b'Subject: attacker subject'),sender,budget(local))
    assert result.signature_valid and not result.verified_confidential and result.mismatches==('subject',)
    pin(v,b,EmailAddress('alice@example.invalid'),sender)
    assert opener.open(local,bk,wire,sender,budget(local)).replay is Replay.DUPLICATE
    conflict=opener.open(local,bk,changed,sender,budget(local))
    assert conflict.replay is Replay.CONFLICT and not conflict.verified_confidential
    assert opener.open(local,bk,wire,sender,budget(local)).replay is Replay.DUPLICATE


@pytest.mark.parametrize('change',['duplicate-profile','hp-clear','duplicate-hp','bad-hp-outer','critical','bad-date','duplicate-from','bad-base64','nested-hp','unknown-parameter','missing-filename'])
def test_authenticated_malformed_inner_rejected(setup,change):
    v,accounts,access,lease,native,compose,draft=setup
    raw=mime.build_inner('alice@example.invalid',draft,'<fixed@example.invalid>',DATE)
    if change=='duplicate-profile': raw=b'X-QuMail-Profile: '+PROFILE.encode()+b'\r\n'+raw
    elif change=='hp-clear': raw=raw.replace(b'hp="cipher"',b'hp="clear"')
    elif change=='duplicate-hp': raw=raw.replace(b'hp="cipher"',b'hp="cipher"; hp="cipher"')
    elif change=='bad-hp-outer': raw=raw.replace(b'HP-Outer: Subject: Encrypted message',b'HP-Outer: Subject: changed')
    elif change=='critical': raw=b'X-QuMail-Critical: unsupported\r\n'+raw
    elif change=='bad-date': raw=raw.replace(DATE.encode(),b'not-a-date')
    elif change=='duplicate-from': raw=b'From: wrong@example.invalid\r\n'+raw
    elif change=='bad-base64': raw=raw.replace(b'RGlzcG9z',b'!!!!@@@@')
    elif change=='nested-hp': raw=raw.replace(b'Content-Type: text/plain;',b'HP-Outer: From: wrong@example.invalid\r\nContent-Type: text/plain;',1)
    elif change=='unknown-parameter': raw=raw.replace(b'hp="cipher"',b'hp="cipher"; critical="unknown"')
    elif change=='missing-filename': raw=raw.replace(b'; filename="example.txt"',b'')
    wire=crafted(setup,raw)
    local=access.select(accounts[1][0])
    with pytest.raises(Failure): OpenMessage(v,access,native).open(local,accounts[1][1],wire,v.export_public(*accounts[0]),budget(local))


def test_legacy_read_only_classification_never_fallback():
    from mime.encapsulator import encapsulate
    raw=encapsulate('a@example.invalid','b@example.invalid','legacy',b'unchanged-ciphertext',{'tqr_level':3}).as_bytes()
    result=legacy.classify(raw)
    assert result.kind is legacy.Kind.LEGACY and result.original==raw
    poisoned=raw.replace(b'application/qumail-pgp',b'application/pgp-encrypted')
    assert legacy.classify(poisoned).kind is legacy.Kind.MODERN
    with pytest.raises(Failure): mime.parse_outer(poisoned)


def test_explicit_no_archive_and_added_outer_headers(setup):
    v,accounts,access,lease,native,compose,draft=setup
    _,envelope=prepared(setup,replace(draft,archive=False,cc=()))
    sender=v.export_public(*accounts[0])
    with pytest.raises(Failure): OpenMessage(v,access,native).open(lease,accounts[0][1],envelope.serialized,sender,budget(lease))
    local=access.select(accounts[1][0])
    wire=b'Cc: attacker@example.invalid\r\n'+envelope.serialized
    message=OpenMessage(v,access,native).open(local,accounts[1][1],wire,sender,budget(local))
    assert message.mismatches==('cc',) and not message.archive


def test_provider_incomplete_verification_never_releases_content(setup,monkeypatch):
    v,accounts,access,lease,native,compose,draft=setup
    _,envelope=prepared(setup); sender=v.export_public(*accounts[0]); local=access.select(accounts[1][0])
    monkeypatch.setattr(native,'call',lambda *a,**k:dict(verified=False,signer='not-authority',data=b'unverified synthetic output'))
    with pytest.raises(Failure): OpenMessage(v,access,native).open(local,accounts[1][1],envelope.serialized,sender,budget(local))
    assert not v._read(accounts[1][0]).get('m5_seen_v1')
