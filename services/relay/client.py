"""Explicit optional endpoint bridge; never installed in ordinary email services."""
from dataclasses import dataclass
import base64
import http.client
import json
import ssl
import time

from experiments.m5.mime import parse_outer
from .http import MAX_BODY
from .store import Code, Failure, Peer


@dataclass(frozen=True)
class Recipient:
    principal: str
    address: str
    root: str


class Client:
    def __init__(self, access, lease, context, port, *, repository=None):
        if context.verify_mode!=ssl.CERT_REQUIRED or not context.check_hostname:
            raise Failure(Code.INVALID)
        self.access, self.owner, self.context, self.port = access,lease,context,port
        self.repository = repository
        self.peer = Peer(lease.context.account.value,lease.context.device.value)

    def request(self, lease, budget, path, payload):
        if lease is not self.owner: raise Failure(Code.DENIED)
        budget.check(); self.access.check(lease,budget.deadline)
        connection = http.client.HTTPSConnection('127.0.0.1',self.port,
            timeout=max(.001,min(5,budget.deadline-time.monotonic())),context=self.context)
        try:
            connection.request('POST',path,json.dumps(payload,separators=(',',':')).encode(),
                               {'Content-Type':'application/json'})
            response = connection.getresponse()
            raw = response.read(MAX_BODY+1)
            if len(raw)>MAX_BODY: raise Failure(Code.LIMIT)
            result = json.loads(raw)
            if response.status!=200:
                try: code = Code(result['error'])
                except (ValueError,KeyError,TypeError): code = Code.BACKEND
                raise Failure(code)
            # A side effect may already have committed. Retrying must use the SAME
            # owner/idempotency key; never install stale results in another account.
            budget.check(); self.access.check(lease,budget.deadline)
            return result
        except (OSError,http.client.HTTPException,ValueError):
            raise Failure(Code.BACKEND) from None
        finally: connection.close()

    def upload(self, lease, budget, envelope, recipient, key, ttl=3600):
        if envelope.account!=lease.context: raise Failure(Code.DENIED)
        if self.repository is None: raise Failure(Code.DENIED)
        # Reuse current M4/M5 vault policy, not merely the frozen recipient root.
        # The short account transaction ends BEFORE network work begins.
        with self.repository.transaction(lease,budget.deadline) as account:
            if account.envelope(envelope.operation)!=envelope: raise Failure(Code.DENIED)
            account.check_prepared(envelope)
        matches = list(zip((a.value for a in envelope.binding.recipients),envelope.binding.roots))
        if (recipient.address,recipient.root) not in matches: raise Failure(Code.DENIED)
        parse_outer(envelope.serialized)
        return self.request(lease,budget,'/v1/objects',dict(key=key,recipient=recipient.principal,
            ciphertext=base64.b64encode(envelope.serialized).decode(),ttl=ttl))

    def acquire(self, lease, budget, object_id, key):
        return self.request(lease,budget,f'/v1/objects/{object_id}/leases',dict(key=key))

    def download(self, lease, budget, object_id, lease_id):
        result = self.request(lease,budget,f'/v1/objects/{object_id}/download',dict(lease=lease_id))
        try: wire = base64.b64decode(result['ciphertext'],validate=True)
        except (KeyError,ValueError,TypeError): raise Failure(Code.INVALID) from None
        parse_outer(wire)
        return wire  # Ciphertext only; existing OpenMessage verifies before plaintext release.

    def acknowledge(self, lease, budget, object_id, lease_id):
        return self.request(lease,budget,f'/v1/objects/{object_id}/ack',dict(lease=lease_id))
