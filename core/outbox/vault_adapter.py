"""M3 adapter: versioned outbox inside the existing authenticated account aggregate.

No schema migration or adjacent key. Short SQLite transactions and OS-released
operation ownership keep network waits outside account-wide writer transactions.
"""
from contextlib import contextmanager
import hashlib
import time
from core.vault.types import BoundaryError, Code, EmailAddress, KeyHandle
from core.vault.vault import PROFILE
from .model import (Binding, CredentialHandle, Error, Failure, PreparedEnvelope,
                    OperationId, MAX_ENVELOPE)
from .codec import pack, unpack
from .ownership import worker_lock


class AccountTransaction:
    def __init__(self, vault, context, data):
        self._vault, self.context, self._data = vault, context, data
        self.records = data.setdefault('m4_outbox_v1', {})
        self.sender = EmailAddress(data['address'])

    def binding(self, key, recipients, profile):
        if profile != PROFILE or not 1 <= len(recipients) <= 32 or len(set(recipients)) != len(recipients):
            raise Failure(Error.POLICY)
        try:
            self._vault.check(self._data, self.context, active=True)
            self._vault.key(self._data, self.context, key, active=True)
            roots, keys = [], []
            for address in recipients:
                if type(address) is not EmailAddress: raise Failure(Error.INVALID)
                self._vault.recipient(self._data, address)
                roots.append(self._data['contacts'][address.value]['fingerprint'])
                contact = self._data['contacts'][address.value]
                keys.append((contact['signing'], contact['encryption']))
            return Binding(key, tuple(recipients), tuple(roots), profile, tuple(keys))
        except BoundaryError:
            raise Failure(Error.POLICY) from None

    def check_prepared(self, envelope):
        current = self.binding(envelope.binding.key, envelope.binding.recipients, envelope.binding.profile)
        if current != envelope.binding: raise Failure(Error.POLICY)

    def credential(self):
        self._vault.check(self._data, self.context, active=True)
        token = self._data.get('oauth')
        if (not token or not token.get('access_token') or
            not isinstance(token.get('expiry'), (int, float)) or token['expiry'] <= time.time()):
            raise Failure(Error.CREDENTIAL)
        # The development transport receives only a scoped handle. No real token
        # is passed to a simulation, nor are identity scopes treated as mail scopes.
        return CredentialHandle(self.context)

    def seal_fixture(self, binding, plaintext):
        if len(binding.recipients) != 1: raise Failure(Error.POLICY)
        key = self._vault.key(self._data, self.context, binding.key, active=True)
        recipient = self._vault.recipient(self._data, binding.recipients[0])
        result = self._vault.provider.call('seal', certificate=bytes(key['secret']),
                                         recipient=recipient, data=plaintext)
        return bytes(result['data'])

    def archive_references(self, binding):
        key = self._vault.key(self._data, self.context, binding.key)
        # Public certificate snapshots and signing key handle; NOT a claim that
        # the sender can decrypt a recipient-only proof payload.
        return {'sender_key': binding.key.value, 'sender_public': pack(bytes(key['public'])),
                'recipient_public': [pack(self._vault.recipient(self._data, a)) for a in binding.recipients]}

    def envelope(self, operation):
        row = self.row(operation)
        value = row['prepared']
        raw = unpack(value['bytes'])
        if not raw or len(raw) > MAX_ENVELOPE or hashlib.sha256(raw).hexdigest() != value['digest']:
            raise Failure(Error.STORAGE)
        binding = Binding(KeyHandle(value['key']), tuple(EmailAddress(a) for a in value['recipients']),
                          tuple(value['roots']), value['profile'], tuple(tuple(k) for k in value['recipient_keys']))
        return PreparedEnvelope(operation, self.context, row['message_id'], binding, raw, value['digest'],
                                EmailAddress(value['sender']))

    def row(self, operation):
        if type(operation) is not OperationId or operation.value not in self.records:
            raise Failure(Error.ACCOUNT)
        row = self.records[operation.value]
        if row['account'] != self.context.account.value or row['version'] != 1:
            raise Failure(Error.ACCOUNT)
        return row


class VaultOutbox:
    def __init__(self, vault, access):
        self.vault, self.access = vault, access

    def ownership(self, context, operation):
        return worker_lock(self.vault.path, context.account, operation)

    @contextmanager
    def completion(self, context):
        # Persist an observed side effect for its original account even after UI
        # selection/lock changes. No credential resolution or UI publication here.
        try:
            with self.vault.transaction(context) as data:
                yield AccountTransaction(self.vault, context, data)
        except BoundaryError: raise Failure(Error.STORAGE) from None

    @contextmanager
    def transaction(self, lease, deadline):
        self.access.check(lease, deadline)
        try:
            with self.vault.transaction(lease.context) as data:
                self.access.check(lease, deadline)  # Recheck after acquiring SQLite lock.
                yield AccountTransaction(self.vault, lease.context, data)
        except Failure: raise
        except BoundaryError as error:
            code = Error.ACCOUNT if error.code == Code.OWNERSHIP else Error.STORAGE
            raise Failure(code) from None
        except (ValueError, KeyError, TypeError):
            raise Failure(Error.STORAGE) from None


class ProviderFixtureBuilder:
    """Unmodified M3 Sequoia helper. Raw OpenPGP proof, NOT a complete MIME mail.

    M5 will bind Message-ID/protected headers through the approved MIME builder.
    This adapter intentionally supports one recipient; no multi-recipient format
    or fallback is invented here. Other conforming builders implement the protocol.
    """
    def build(self, account, binding, plaintext, message_id):
        return account.seal_fixture(binding, plaintext)
