"""Explicit disposable development demonstration; never imports an SMTP adapter."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import time
from experiments.m3.types import EmailAddress, UserId, VerifiedProviderIdentity
from experiments.m3.vault import Vault, PROFILE
from experiments.m3.provider import Provider
from experiments.m3.secure_store import WindowsCredentialStore
from .model import AccountAccess, Outcome, State, Failure
from .vault_adapter import VaultOutbox, ProviderFixtureBuilder
from .services import PrepareMessage, SubmitOutbox
from .transports import SimulatedTransport


def demo():
    root = Path(__file__).resolve().parents[2]
    provider = Provider(root/'tmp/m2/target/debug/qumail-m3-provider.exe')
    store = WindowsCredentialStore()
    with tempfile.TemporaryDirectory(prefix='m4-demo-', dir=root/'tmp') as directory:
        vault = Vault.create(Path(directory)/'disposable.sqlite', store, provider)
        try:
            accounts = []
            for name in ('sender', 'recipient'):
                address = EmailAddress(name+'@example.invalid')
                identity = VerifiedProviderIdentity('https://accounts.google.com', 'synthetic-'+name,
                    (address,), int(time.time())+3600, 'synthetic authorization; not live Google')
                accounts.append(vault.enroll(identity, address, UserId.new(), tokens={
                    'access_token':'synthetic-not-a-credential','expiry':int(time.time())+3600}))
            sender, key = accounts[0]; recipient, recipient_key = accounts[1]
            address = EmailAddress('recipient@example.invalid')
            fingerprint = vault.import_contact(sender, address, vault.export_public(recipient, recipient_key))
            vault.pin_contact(sender, address, fingerprint, 'in-person')  # Controlled ceremony fixture.
            access = AccountAccess(); lease = access.select(sender)
            repository = VaultOutbox(vault, access)
            prepare = PrepareMessage(repository, ProviderFixtureBuilder())
            operation = prepare.draft(lease, b'disposable M4 provider-generated fixture')
            envelope = prepare.prepare(lease, operation, key, (address,), PROFILE)
            assert vault.open_for_test(recipient, recipient_key, vault.export_public(sender, key), envelope.serialized)
            class Interruption(Exception): pass
            class Interrupted(VaultOutbox):
                @contextmanager
                def transaction(self, *args):
                    with super().transaction(*args) as account: yield account
                    raise Interruption()  # Simulation AFTER committed submission intent.
            transport = SimulatedTransport()
            try: SubmitOutbox(Interrupted(vault, access), transport).submit(lease, operation)
            except Interruption: pass
            assert not transport.calls
            reopened = Vault(vault.path, store, provider)
            submit = SubmitOutbox(VaultOutbox(reopened, access), transport)
            assert submit.recover(lease) == (operation,)
            unknown = submit.inspect(lease, operation)
            try: submit.retry(lease, operation)
            except Failure: pass
            else: raise AssertionError('duplicate-risk decision missing')
            submit.retry(lease, operation, acknowledge_duplicate_risk=True)
            accepted = submit.submit(lease, operation)
            assert transport.calls == [envelope] and accepted.state is State.ACCEPTED
            def export_failure(result): raise OSError('controlled optional export failure')
            assert not submit.export_receipt(lease, operation, export_failure)
            assert submit.inspect(lease, operation).state is State.ACCEPTED
            return dict(mode='simulation only; synthetic authorization; real Windows vault/provider',
                prepared=True, interruption='simulated after durable intent; no transport call',
                restart=unknown.state.value, explicit_duplicate_risk_retry=True,
                final=accepted.state.value, meaning='simulated server acceptance, not delivery',
                byte_identical_retry=True, optional_export_failure_preserves_acceptance=True,
                disposable_credentials_cleaned=True)
        finally:
            store.delete(vault.ident)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulate', action='store_true', help='required opt-in; no real mail exists')
    args = parser.parse_args()
    if not args.simulate: parser.error('--simulate is required')
    print(json.dumps(demo(), indent=2))
