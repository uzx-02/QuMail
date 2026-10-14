from dataclasses import replace
import pytest
from experiments.m5.model import *
from experiments.m5 import mime
from experiments.m5.services import OpenMessage
from experiments.m5.tests.test_message import setup,provider,vault,prepared,budget,DATE


def fixture(): return Draft(('b@example.invalid',),(),'subject','body')


@pytest.mark.parametrize('change',['body','attachments','attachment-size','recipients','bcc','name','header-injection','references'])
def test_outbound_limits_before_crypto(change):
    d=fixture()
    if change=='body': d=replace(d,body='x'*(MAX_BODY+1))
    elif change=='attachments': d=replace(d,attachments=tuple(Attachment(str(i)+'.bin','application/octet-stream',b'') for i in range(5)))
    elif change=='attachment-size': d=replace(d,attachments=(Attachment('a.bin','application/octet-stream',b'x'*(MAX_ATTACHMENT_BYTES+1)),))
    elif change=='recipients': d=replace(d,to=tuple(str(i)+'@example.invalid' for i in range(4)))
    elif change=='bcc': d=replace(d,bcc=('hidden@example.invalid',))
    elif change=='name': d=replace(d,attachments=(Attachment('../secret','text/plain',b'x'),))
    elif change=='header-injection': d=replace(d,subject='safe\r\nBcc: evil@example.invalid')
    else: d=replace(d,references=tuple('<'+str(i)+'@example.invalid>' for i in range(9)))
    with pytest.raises(Failure): mime.build_inner('a@example.invalid',d,'<fixed@example.invalid>',DATE)


def test_exact_qualified_plaintext_limits():
    d=replace(fixture(),body='a'*MAX_BODY,attachments=tuple(Attachment(str(i)+'.bin','application/octet-stream',b'b'*(MAX_ATTACHMENT_BYTES//4)) for i in range(4)))
    raw=mime.build_inner('a@example.invalid',d,'<fixed@example.invalid>',DATE)
    assert len(raw)<MAX_INNER
    assert mime.parse_inner(raw)[1]==d


@pytest.mark.parametrize('change',['wire','headers','depth','parts','duplicate-content-type','duplicate-boundary','duplicate-control','trailing-armor'])
def test_bounded_malformed_structures(change):
    inner=mime.build_inner('a@example.invalid',fixture(),'<fixed@example.invalid>',DATE)
    if change=='wire': raw=b'x'*(MAX_WIRE+1)
    elif change=='headers': raw=b'X-Pad: '+b'\r\n '.join([b'x'*900]*10)+b'\r\n\r\nbody\r\n'
    elif change=='depth':
        raw=inner
        for i in range(3): raw=b'Content-Type: multipart/mixed; boundary=b'+str(i).encode()+b'\r\n\r\n--b'+str(i).encode()+b'\r\n'+raw+b'\r\n--b'+str(i).encode()+b'--\r\n'
    elif change=='parts': raw=b'Content-Type: multipart/mixed; boundary=b\r\n\r\n'+(b'--b\r\n'+inner+b'\r\n')*7+b'--b--\r\n'
    else:
        armor=b'-----BEGIN PGP MESSAGE-----\r\n\r\nZmFrZQ==\r\n-----END PGP MESSAGE-----\r\n'
        raw=mime.build_outer('a@example.invalid',fixture(),'<fixed@example.invalid>',DATE,armor)
        if change=='duplicate-content-type': raw=b'Content-Type: multipart/encrypted\r\n'+raw
        elif change=='duplicate-boundary': raw=raw.replace(b'protocol="application/pgp-encrypted";',b'protocol="application/pgp-encrypted"; boundary=evil;')
        elif change=='duplicate-control': raw=raw.replace(b'Version: 1',b'Version: 1\r\nVersion: 1')
        else: raw=raw.replace(b'-----END PGP MESSAGE-----',b'-----END PGP MESSAGE-----\r\n-----BEGIN PGP MESSAGE-----')
    with pytest.raises(Failure): mime.parse_outer(raw)


def test_cancellation_never_publishes_or_prepares(setup):
    v,accounts,access,lease,native,compose,draft=setup
    op=compose.draft(lease,draft,budget(lease)); lease.cancelled.set()
    with pytest.raises(Failure): compose.prepare(lease,op,accounts[0][1],budget(lease))
    lease=access.select(accounts[0][0])
    envelope=compose.prepare(lease,op,accounts[0][1],budget(lease))
    local=access.select(accounts[1][0]); local.cancelled.set()
    with pytest.raises(Failure): OpenMessage(v,access,native).open(local,accounts[1][1],envelope.serialized,v.export_public(*accounts[0]),budget(local))


def test_replay_capacity_and_storage_failure_no_verified_return(setup):
    v,accounts,access,lease,native,compose,draft=setup
    _,envelope=prepared(setup); sender=v.export_public(*accounts[0]); b,bk=accounts[1]; local=access.select(b)
    with v.transaction(b) as data: data['m5_seen_v1']={str(i):{'digest':'a'*64} for i in range(MAX_HISTORY)}
    with pytest.raises(Failure) as failure: OpenMessage(v,access,native).open(local,bk,envelope.serialized,sender,budget(local))
    assert failure.value.code is Code.LIMIT
    with v.transaction(b) as data: data['m5_seen_v1']={}
    from experiments.m4.tests.test_outbox import deny_commit
    # Open first reads the key on connection 1; replay persistence uses connection 2.
    with deny_commit(v,2):
        with pytest.raises(Failure): OpenMessage(v,access,native).open(local,bk,envelope.serialized,sender,budget(local))
    assert not v._read(b).get('m5_seen_v1')
