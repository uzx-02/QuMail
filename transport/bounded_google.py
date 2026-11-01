"""Application OAuth boundary; original provider verification runs in a private worker."""
from dataclasses import asdict
import time
from .development_google import GoogleAuthorization,Authorization
from .bounded_worker import call
from experiments.m3.types import BoundaryError,Code,VerifiedProviderIdentity,EmailAddress


class BoundedGoogleAuthorization(GoogleAuthorization):
    def invoke(self,op,cancel,seconds,*,deadline=None,**fields):
        try:
            until=time.monotonic()+seconds
            if deadline is not None: until=min(until,deadline)
            result=call(dict(op=op,config=self.config,scopes=self.scopes,**fields),cancel,until)
            i=result['identity']
            identity=VerifiedProviderIdentity(i['issuer'],i['subject'],tuple(EmailAddress(a['value']) for a in i['addresses']),i['expires'],i['evidence'])
            return Authorization(identity,result['tokens'])
        except BoundaryError: raise
        except Exception: raise BoundaryError(Code.IDENTITY) from None

    def authorize(self,cancel,expected_address,expected_subject=None):
        return self.invoke('authorize',cancel,210,address=expected_address,subject=expected_subject)

    def refresh(self,cancel,context,address,tokens,*,deadline=None):
        return self.invoke('refresh',cancel,30,deadline=deadline,context=asdict(context),address=address,tokens=tokens)
