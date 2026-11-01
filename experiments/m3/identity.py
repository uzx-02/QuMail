"""Provider evidence boundary; no browser or real authorization invoked here."""
import secrets
import time
from google.oauth2 import id_token
from google.auth.transport.requests import Request
from google.auth.exceptions import InvalidValue, TransportError
from .types import BoundaryError,Code,EmailAddress,VerifiedProviderIdentity


def verify_google_token(token,client_id,request,*,cancel=None,wait_seconds=0):
    """Retry only a not-yet-valid token; never accept clock skew or expired JWTs.

    Each attempt uses the maintained signature/audience/time verifier unchanged.
    Parent process deadline still bounds certificate fetches and cancellation.
    """
    deadline=time.monotonic()+min(max(wait_seconds,0),20)
    while True:
        if cancel is not None and cancel.is_set(): raise BoundaryError(Code.IDENTITY)
        try:
            return id_token.verify_oauth2_token(token,request,audience=client_id)
        except InvalidValue as error:
            if not str(error).startswith('Token used too early,') or time.monotonic()>=deadline:
                raise
            delay=min(1,deadline-time.monotonic())
            if cancel is not None:
                if cancel.wait(delay): raise BoundaryError(Code.IDENTITY)
            else: time.sleep(delay)


def google_identity(token: str, client_id: str, expected_nonce: str,
                    expected_state: str, received_state: str, expected_subject=None,request=None,
                    *,cancel=None,wait_seconds=0):
    if not client_id or len(expected_nonce)<32 or len(expected_state)<32 or not secrets.compare_digest(expected_state,received_state):
        raise BoundaryError(Code.IDENTITY)
    try:
        claims=verify_google_token(token,client_id,request or Request(),cancel=cancel,wait_seconds=wait_seconds)
        return validated_google_claims(claims,client_id,expected_nonce,expected_subject)
    except BoundaryError: raise
    except TransportError:
        raise BoundaryError(Code.GOOGLE_KEYS) from None
    except InvalidValue as error:
        # Classify maintained-library failures into fixed application codes.
        # Never forward its message, claims, token, timestamps or URLs.
        message=str(error)
        if message.startswith(('Token used too early,','Token expired,')):
            raise BoundaryError(Code.GOOGLE_CLOCK) from None
        if message.startswith('Token has wrong audience'):
            raise BoundaryError(Code.GOOGLE_AUDIENCE) from None
        raise BoundaryError(Code.GOOGLE_SIGNATURE) from None
    except Exception:
        raise BoundaryError(Code.GOOGLE_SIGNATURE) from None


def validated_google_claims(claims, client_id, nonce, expected_subject=None):
    """Internal post-signature validation; direct fixture calls are synthetic evidence."""
    try:
        address=EmailAddress(claims['email'])
        domain=address.value.rsplit('@',1)[1]
        # Google explicitly warns email_verified alone is not authoritative for
        # third-party email. Unproven alias domains fail closed in this prototype.
        if domain!='gmail.com' and claims.get('hd')!=domain:
            raise ValueError()
        if claims['aud']!=client_id or claims.get('azp',client_id)!=client_id:
            raise BoundaryError(Code.GOOGLE_AUDIENCE)
        if not secrets.compare_digest(claims['nonce'],nonce):
            raise BoundaryError(Code.GOOGLE_NONCE)
        if (claims['iss'] not in ('accounts.google.com','https://accounts.google.com') or
            claims['email_verified'] is not True or int(claims['exp'])<=int(time.time()) or
            not isinstance(claims['sub'],str) or not claims['sub'] or
            (expected_subject is not None and claims['sub']!=expected_subject)):
            raise ValueError()
        return VerifiedProviderIdentity('https://accounts.google.com',claims['sub'],
            (address,),int(claims['exp']),'google-auth verified ID token')
    except (KeyError,ValueError,TypeError):
        raise BoundaryError(Code.GOOGLE_AUTHORITY) from None


def yahoo_identity(*args, **kwargs):
    # No unverified JWT decode or synthetic fixture may enable Yahoo enrollment.
    raise BoundaryError(Code.IDENTITY)
