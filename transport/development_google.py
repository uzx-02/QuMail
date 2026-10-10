"""Development-only Google desktop OAuth. Never reads a legacy token cache."""
from dataclasses import dataclass
from datetime import timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import secrets
import threading
import time
from urllib.parse import urlsplit, parse_qs
import webbrowser
import requests
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.oauth2 import id_token
from google.auth.transport.requests import Request
from experiments.m3.identity import google_identity
from experiments.m3.types import BoundaryError, Code, EmailAddress, VerifiedProviderIdentity

AUTH='https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_CLIENT_AUTH_URIS=(AUTH,'https://accounts.google.com/o/oauth2/auth')
TOKEN='https://oauth2.googleapis.com/token'
USERINFO='https://openidconnect.googleapis.com/v1/userinfo'
SCOPES=('openid','https://www.googleapis.com/auth/userinfo.email')


@dataclass(frozen=True,repr=False)
class Authorization:
    identity: VerifiedProviderIdentity
    tokens: dict


def client_configuration(path):
    # Only an explicitly selected Desktop client file; no discovery/cache scanning.
    try:
        with open(path,'rb') as file: raw=file.read(32769)
        if len(raw)>32768: raise ValueError()
        config=json.loads(raw)['installed']
        if (not config['client_id'].endswith('.apps.googleusercontent.com') or
            config['auth_uri'] not in GOOGLE_CLIENT_AUTH_URIS or config['token_uri']!=TOKEN): raise ValueError()
        selected={k:config[k] for k in ('client_id','client_secret','auth_uri','token_uri')}
        selected['auth_uri']=AUTH  # Always use the documented v2 endpoint with S256 PKCE.
        return {'installed':selected}
    except (OSError,ValueError,KeyError,TypeError):
        raise BoundaryError(Code.IDENTITY) from None


class BoundedRequest(Request):
    def __call__(self,*args,**kwargs):
        kwargs['timeout']=15
        return super().__call__(*args,**kwargs)


def callback_code(path,host,expected_host,state):
    try:
        url=urlsplit(path)
        if len(path)>4096 or host!=expected_host or url.path!='/' or url.scheme or url.netloc or url.fragment:
            raise ValueError()
        query=parse_qs(url.query,keep_blank_values=True,strict_parsing=True,max_num_fields=12)
        if len(query.get('state',[]))!=1 or not secrets.compare_digest(query['state'][0],state):
            raise ValueError()
        if 'error' in query: raise BoundaryError(Code.IDENTITY)
        if len(query.get('code',[]))!=1 or not query['code'][0]: raise ValueError()
        return query['code'][0]
    except (ValueError,KeyError,TypeError): raise BoundaryError(Code.IDENTITY) from None


class Loopback:
    def __init__(self,state):
        self.state=state
        self.code=None
        self.denied=False
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass  # Callback URL/code never logged.
            def do_GET(self):
                try:
                    if len(self.headers.get_all('Host',[]))!=1: raise BoundaryError(Code.IDENTITY)
                    code=callback_code(self.path,self.headers.get('Host'),owner.host,state)
                    owner.code=code
                    status=200
                except BoundaryError:
                    # Error callbacks with correct state terminate cleanly; random
                    # loopback probes do not enroll anything or install credentials.
                    try:
                        q=parse_qs(urlsplit(self.path).query,max_num_fields=12)
                        owner.denied=q.get('state')==[state] and 'error' in q and self.path.startswith('/?')
                    except ValueError: pass
                    status=400
                self.send_response(status)
                self.send_header('Content-Type','text/plain; charset=utf-8')
                self.send_header('Cache-Control','no-store')
                self.end_headers()
                self.wfile.write(b'Return to QuMail. No credentials are displayed here.')
        class Server(HTTPServer):
            def get_request(self):
                connection,address=super().get_request(); connection.settimeout(2)
                return connection,address
            def handle_error(self,*args): pass
        self.server=Server(('127.0.0.1',0),Handler)
        self.server.timeout=.2
        self.host=f'127.0.0.1:{self.server.server_port}'
        self.redirect='http://'+self.host+'/'

    def wait(self,cancel,timeout=180):
        deadline=time.monotonic()+timeout
        while not cancel.is_set() and time.monotonic()<deadline and not self.denied:
            self.server.handle_request()
            if self.code: return self.code
        raise BoundaryError(Code.IDENTITY)

    def close(self): self.server.server_close()


class GoogleAuthorization:
    def __init__(self,config):
        self.config=config
        c=config['installed']
        if c['auth_uri']!=AUTH or c['token_uri']!=TOKEN: raise BoundaryError(Code.IDENTITY)
        self.client_id=c['client_id']

    def authorize(self,cancel,expected_address,expected_subject=None,opener=webbrowser.open):
        state=secrets.token_urlsafe(32); nonce=secrets.token_urlsafe(32)
        listener=Loopback(state)
        flow=None
        try:
            if cancel.is_set(): raise BoundaryError(Code.IDENTITY)
            flow=InstalledAppFlow.from_client_config(self.config,SCOPES,state=state,autogenerate_code_verifier=True)
            flow.redirect_uri=listener.redirect
            url,returned_state=flow.authorization_url(nonce=nonce,prompt='select_account consent',access_type='offline')
            if returned_state!=state or not flow.code_verifier: raise BoundaryError(Code.IDENTITY)
            if not opener(url): raise BoundaryError(Code.IDENTITY)
            code=listener.wait(cancel)
            if cancel.is_set(): raise BoundaryError(Code.IDENTITY)
            # State/path/host verified on loopback; HTTPS token exchange and PKCE
            # are handled by maintained requests-oauthlib/google-auth-oauthlib.
            token=flow.fetch_token(code=code,timeout=15,allow_redirects=False)
            verified=google_identity(token['id_token'],self.client_id,nonce,state,state,
                                     expected_subject,request=BoundedRequest())
            if EmailAddress(expected_address) not in verified.addresses or cancel.is_set():
                raise BoundaryError(Code.IDENTITY)
            scopes=token.get('scope',SCOPES)
            if isinstance(scopes,str): scopes=scopes.split()
            if not set(SCOPES)<=set(scopes): raise BoundaryError(Code.IDENTITY)
            tokens=dict(access_token=token['access_token'],refresh_token=token.get('refresh_token'),
                        expiry=int(token['expires_at']),scopes=list(scopes))
            return Authorization(verified,tokens)
        except Exception:
            raise BoundaryError(Code.IDENTITY) from None
        finally:
            listener.close()
            if flow: flow.oauth2session.close()

    def refresh(self,cancel,context,address,tokens):
        try:
            if cancel.is_set() or context.issuer!='https://accounts.google.com' or not tokens.get('refresh_token'): raise ValueError()
            c=self.config['installed']
            credentials=Credentials(tokens['access_token'],refresh_token=tokens['refresh_token'],
                token_uri=TOKEN,client_id=self.client_id,client_secret=c['client_secret'],scopes=SCOPES)
            credentials.refresh(BoundedRequest())
            # Refresh responses need not supply an ID token/nonce. Authenticate the
            # fresh access token at Google's fixed TLS userinfo endpoint instead.
            with requests.Session() as session:
                response=session.get(USERINFO,headers={'Authorization':'Bearer '+credentials.token},
                                     timeout=15,allow_redirects=False)
                if response.status_code!=200: raise ValueError()
                claims=response.json()
            if (claims.get('sub')!=context.subject or claims.get('email_verified') is not True or
                EmailAddress(claims['email'])!=EmailAddress(address) or cancel.is_set()): raise ValueError()
            if credentials.id_token:
                info=id_token.verify_oauth2_token(credentials.id_token,BoundedRequest(),audience=self.client_id)
                if info.get('sub')!=context.subject: raise ValueError()
            expiration=credentials.expiry
            if expiration.tzinfo is None: expiration=expiration.replace(tzinfo=timezone.utc)
            expiry=int(expiration.timestamp())
            identity=VerifiedProviderIdentity(context.issuer,context.subject,(EmailAddress(address),),expiry,
                'Google TLS userinfo with refreshed token')
            return Authorization(identity,dict(access_token=credentials.token,refresh_token=credentials.refresh_token,
                                               expiry=expiry,scopes=list(SCOPES)))
        except Exception: raise BoundaryError(Code.IDENTITY) from None
