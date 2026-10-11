"""Disposable child process: parent kills it at real transaction/transport boundaries."""
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import threading
from experiments.m3.types import AccountContext, AccountId, DeviceId, KeyHandle, EmailAddress
from experiments.m3.vault import Vault, PROFILE
from experiments.m3.provider import Provider
from experiments.m3.secure_store import WindowsCredentialStore
from experiments.m4.model import AccountAccess, OperationId, Outcome
from experiments.m4.vault_adapter import VaultOutbox, ProviderFixtureBuilder
from experiments.m4.services import PrepareMessage, SubmitOutbox
from experiments.m4.transports import SimulatedTransport


if __name__ == '__main__':
    request = json.load(sys.stdin)
    def boundary(point):
        if point == request['point']:
            Path(request['marker']).write_text('boundary reached')
            threading.Event().wait(60)
            raise RuntimeError('parent must terminate child')
    class CrashRepository(VaultOutbox):
        count = 0
        @contextmanager
        def transaction(self, *args):
            self.count += 1
            with super().transaction(*args) as account:
                yield account
                boundary(f'{self.count}-before')
            boundary(f'{self.count}-after')
    class ObservedTransport(SimulatedTransport):
        def submit(self, *args):
            boundary('transport-before')
            value = super().submit(*args)
            boundary('transport-after')
            return value
    root = Path(__file__).resolve().parents[3]
    v = Vault(request['path'], WindowsCredentialStore(), Provider(root/'tmp/m2/target/debug/qumail-m3-provider.exe'))
    access = AccountAccess()
    lease = access.select(AccountContext(AccountId(request['account']), DeviceId(request['device']),
                                         request['issuer'], request['subject']))
    repo = CrashRepository(v, access); op = OperationId(request['operation'])
    if request['mode'] == 'prepare':
        PrepareMessage(repo, ProviderFixtureBuilder()).prepare(lease, op, KeyHandle(request['key']),
            (EmailAddress(request['recipient']),), PROFILE)
    elif request['mode'] == 'export':
        def persist(delivery):
            boundary('receipt-before')
            Path(request['marker']+'.receipt').write_text(delivery.state.value)
            boundary('receipt-after')
        SubmitOutbox(repo, ObservedTransport()).export_receipt(lease, op, persist)
    else: SubmitOutbox(repo, ObservedTransport()).submit(lease, op)
