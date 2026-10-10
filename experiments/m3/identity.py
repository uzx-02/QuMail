"""Provider evidence boundary; no browser or real authorization invoked here."""
import secrets
import time
from google.oauth2 import id_token
from google.auth.transport.requests import Request
from .types import BoundaryError,Code,EmailAddress,VerifiedProviderIdentity


def google_identity(token: str, client_id: str, expected_nonce: str,
                    expected_state: str, received_state: str, expected_subject=None):
    if not client_id or len(expected_nonce)<32 or len(expected_state)<32 or not secrets.compare_digest(expected_state,received_state):
        raise BoundaryError(Code.IDENTITY)
    try:
        claims=id_token.verify_oauth2_token(token,Request(),audience=client_id)
        return validated_google_claims(claims,client_id,expected_nonce,expected_subject)
    except Exception:
        raise BoundaryError(Code.IDENTITY) from None


def validated_google_claims(claims, client_id, nonce, expected_subject=None):
    """Internal post-signature validation; direct fixture calls are synthetic evidence."""
    try:
        address=EmailAddress(claims['email'])
        domain=address.value.rsplit('@',1)[1]
        # Google explicitly warns email_verified alone is not authoritative for
        # third-party email. Unproven alias domains fail closed in this prototype.
        if domain!='gmail.com' and claims.get('hd')!=domain:
            raise ValueError()
        if (claims['iss'] not in ('accounts.google.com','https://accounts.google.com') or
            claims['aud']!=client_id or claims.get('azp',client_id)!=client_id or
            not secrets.compare_digest(claims['nonce'],nonce) or
            claims['email_verified'] is not True or int(claims['exp'])<=int(time.time()) or
            not isinstance(claims['sub'],str) or not claims['sub'] or
            (expected_subject is not None and claims['sub']!=expected_subject)):
            raise ValueError()
        return VerifiedProviderIdentity('https://accounts.google.com',claims['sub'],
            (address,),int(claims['exp']),'google-auth verified ID token')
    except (KeyError,ValueError,TypeError):
        raise BoundaryError(Code.IDENTITY) from None


def yahoo_identity(*args, **kwargs):
    # No unverified JWT decode or synthetic fixture may enable Yahoo enrollment.
    raise BoundaryError(Code.IDENTITY)
