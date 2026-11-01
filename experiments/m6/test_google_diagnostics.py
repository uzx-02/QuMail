"""Sanitized stage reporting uses only fixed codes, never OAuth payloads."""
import threading
from types import SimpleNamespace
import pytest
from experiments.m3.types import BoundaryError,Code
from transport import development_google as google
from transport.bounded_google import BoundedGoogleAuthorization
from ui.mail_accessibility import error_message

CONFIG={'installed':{'client_id':'test.apps.googleusercontent.com','client_secret':'fixture',
                    'auth_uri':google.AUTH,'token_uri':google.TOKEN}}


@pytest.mark.parametrize('stage,code',[
    ('callback',Code.GOOGLE_CALLBACK),('token',Code.GOOGLE_TOKEN),('claims',Code.GOOGLE_CLAIMS),
    ('address',Code.GOOGLE_ADDRESS),('scope',Code.GOOGLE_SCOPES)])
def test_authorization_stage_redacts_provider_errors(monkeypatch,stage,code):
    sentinel='PRIVATE_PROVIDER_PAYLOAD_MUST_NOT_ESCAPE'
    def reject(): raise ValueError(sentinel)
    class Listener:
        redirect='http://127.0.0.1:1234/'
        def __init__(self,state): pass
        def wait(self,cancel): return reject() if stage=='callback' else 'fixture-code'
        def close(self): pass
    class Flow:
        code_verifier='fixture-verifier'
        oauth2session=SimpleNamespace(close=lambda:None)
        def authorization_url(self,**kwargs): return 'https://accounts.google.com/',self.state
        def fetch_token(self,**kwargs):
            if stage=='token': reject()
            return dict(id_token='fixture',access_token='fixture',expires_at=2000000000,scope=[])
    def factory(config,scopes,state,**kwargs):
        flow=Flow(); flow.state=state; return flow
    def identity(*args,**kwargs):
        if stage=='claims': reject()
        return SimpleNamespace(addresses=(google.EmailAddress('bob@gmail.com' if stage=='address' else 'alice@gmail.com'),))
    monkeypatch.setattr(google,'Loopback',Listener)
    monkeypatch.setattr(google.InstalledAppFlow,'from_client_config',factory)
    monkeypatch.setattr(google,'google_identity',identity)
    with pytest.raises(BoundaryError) as error:
        google.GoogleAuthorization(CONFIG).authorize(threading.Event(),'alice@gmail.com',opener=lambda _:True)
    assert error.value.code is code
    assert sentinel not in str(error.value) and sentinel not in error_message(error.value)


def test_bounded_google_preserves_only_fixed_stage_code(monkeypatch):
    from transport import bounded_google
    def reject(*args): raise BoundaryError(Code.GOOGLE_CLAIMS)
    monkeypatch.setattr(bounded_google,'call',reject)
    with pytest.raises(BoundaryError) as error:
        BoundedGoogleAuthorization(CONFIG).authorize(threading.Event(),'alice@gmail.com')
    assert error.value.code is Code.GOOGLE_CLAIMS


@pytest.mark.parametrize('reason,code',[
    ('Token used too early, PRIVATE',Code.GOOGLE_CLOCK),
    ('Token expired, PRIVATE',Code.GOOGLE_CLOCK),
    ('Token has wrong audience PRIVATE',Code.GOOGLE_AUDIENCE),
    ('Signature could not be verified PRIVATE',Code.GOOGLE_SIGNATURE)])
def test_verifier_reason_redacted_without_relaxing_checks(monkeypatch,reason,code):
    from experiments.m3 import identity
    from google.auth.exceptions import InvalidValue
    def reject(*args,**kwargs):
        assert kwargs=={'audience':'client'}  # No clock-skew relaxation.
        raise InvalidValue(reason)
    monkeypatch.setattr(identity.id_token,'verify_oauth2_token',reject)
    with pytest.raises(BoundaryError) as error:
        identity.google_identity('PRIVATE','client','n'*32,'s'*32,'s'*32)
    assert error.value.code is code and 'PRIVATE' not in str(error.value)


def test_fresh_token_wait_reverifies_and_never_relaxes_time(monkeypatch):
    from experiments.m3 import identity
    from google.auth.exceptions import InvalidValue
    now=[0.]; calls=[]
    class Cancel:
        def is_set(self): return False
        def wait(self,seconds): now[0]+=seconds; return False
    def verify(token,request,**kwargs):
        assert kwargs=={'audience':'client'}
        calls.append(now[0])
        if now[0]<2: raise InvalidValue('Token used too early, PRIVATE')
        return {'verified':'fixture'}
    monkeypatch.setattr(identity.time,'monotonic',lambda:now[0])
    monkeypatch.setattr(identity.id_token,'verify_oauth2_token',verify)
    assert identity.verify_google_token('PRIVATE','client',object(),cancel=Cancel(),wait_seconds=20)=={'verified':'fixture'}
    assert calls==[0,1,2]


@pytest.mark.parametrize('reason',['Token expired, PRIVATE','Signature could not be verified PRIVATE'])
def test_wait_never_retries_expiry_or_signature_failure(monkeypatch,reason):
    from experiments.m3 import identity
    from google.auth.exceptions import InvalidValue
    calls=[]
    def verify(*args,**kwargs): calls.append(1); raise InvalidValue(reason)
    monkeypatch.setattr(identity.id_token,'verify_oauth2_token',verify)
    with pytest.raises(InvalidValue): identity.verify_google_token('PRIVATE','client',object(),wait_seconds=20)
    assert len(calls)==1


def test_fresh_token_wait_is_bounded_and_cancellable(monkeypatch):
    from experiments.m3 import identity
    from google.auth.exceptions import InvalidValue
    now=[0.]
    class Cancel:
        stopped=False
        def is_set(self): return self.stopped
        def wait(self,seconds): now[0]+=seconds; return self.stopped
    def verify(*args,**kwargs): raise InvalidValue('Token used too early, PRIVATE')
    monkeypatch.setattr(identity.time,'monotonic',lambda:now[0])
    monkeypatch.setattr(identity.id_token,'verify_oauth2_token',verify)
    cancel=Cancel()
    with pytest.raises(InvalidValue): identity.verify_google_token('PRIVATE','client',object(),cancel=cancel,wait_seconds=999)
    assert now[0]==20
    cancel.stopped=True
    with pytest.raises(BoundaryError): identity.verify_google_token('PRIVATE','client',object(),cancel=cancel,wait_seconds=20)
