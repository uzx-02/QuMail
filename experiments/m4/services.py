"""Durable preparation/submission state machine; no Qt, SMTP, HTTP or UI imports."""
import hashlib
import time
from .model import (OperationId, State, Error, Failure, Outcome, DeliveryResult,
                    OutboxRepository, EnvelopeBuilder, Transport, Reconciler, Lease, PreparedEnvelope,
                    MAX_DRAFT, MAX_ENVELOPE, MAX_OPERATIONS, MAX_ATTEMPTS)
from experiments.m3.types import KeyHandle, EmailAddress
from .codec import pack, unpack


def deadline(): return time.monotonic() + 30


def result(operation, row):
    return DeliveryResult(operation, State(row['state']), row['reason'], len(row['attempts']))


class PrepareMessage:
    def __init__(self, repository: OutboxRepository, builder: EnvelopeBuilder):
        self.repository, self.builder = repository, builder

    def draft(self, lease: Lease, plaintext: bytes, *, until: float | None = None) -> OperationId:
        until = deadline() if until is None else until
        if type(plaintext) is not bytes or not plaintext or len(plaintext) > MAX_DRAFT:
            raise Failure(Error.LIMIT)
        operation = OperationId.new()
        with self.repository.transaction(lease, until) as account:
            if len(account.records) >= MAX_OPERATIONS: raise Failure(Error.LIMIT)
            account.records[operation.value] = dict(version=1, account=lease.context.account.value,
                message_id=f'<{operation.value}@qumail.invalid>', state=State.DRAFT.value,
                draft=pack(plaintext), attempts=[], reason='encrypted_draft')
        return operation

    def prepare(self, lease: Lease, operation: OperationId, key: KeyHandle,
                recipients: tuple[EmailAddress, ...], profile: str, *, until: float | None = None) -> PreparedEnvelope:
        until = deadline() if until is None else until
        with self.repository.transaction(lease, until) as account:
            row = account.row(operation)
            if row['state'] != State.DRAFT.value: raise Failure(Error.TRANSITION)
            binding = account.binding(key, recipients, profile)
            try:
                raw = self.builder.build(account, binding, unpack(row['draft']), row['message_id'])
            except Failure: raise
            except Exception: raise Failure(Error.PROVIDER) from None
            if type(raw) is not bytes or not raw or len(raw) > MAX_ENVELOPE: raise Failure(Error.LIMIT)
            if lease.cancelled.is_set() or time.monotonic() >= until: raise Failure(Error.CANCELLED)
            row['prepared'] = dict(bytes=pack(raw), digest=hashlib.sha256(raw).hexdigest(), key=key.value,
                recipients=[a.value for a in binding.recipients], roots=list(binding.roots), profile=profile,
                recipient_keys=[list(k) for k in binding.recipient_keys],
                archive=account.archive_references(binding))
            row.update(state=State.PREPARED.value, reason='durably_prepared')
            del row['draft']  # Never retain a second unwrapped draft or any content key.
            envelope = account.envelope(operation)
        return envelope  # No handle/bytes returned as success until commit completed.


class SubmitOutbox:
    def __init__(self, repository: OutboxRepository, transport: Transport):
        if transport.simulation_only is not True: raise Failure(Error.TRANSPORT)
        self.repository, self.transport = repository, transport

    def inspect(self, lease: Lease, operation: OperationId) -> DeliveryResult:
        with self.repository.transaction(lease, deadline()) as account:
            return result(operation, account.row(operation))

    def envelope(self, lease: Lease, operation: OperationId) -> PreparedEnvelope:
        with self.repository.transaction(lease, deadline()) as account:
            return account.envelope(operation)

    def submit(self, lease: Lease, operation: OperationId, *, until: float | None = None) -> DeliveryResult:
        until = deadline() if until is None else until
        # Phase one is independently committed BEFORE credentials reach any
        # transport. Concurrent callers cannot both claim the Prepared record.
        with self.repository.transaction(lease, until) as account:
            row = account.row(operation)
            if row['state'] != State.PREPARED.value: raise Failure(Error.TRANSITION)
            if len(row['attempts']) >= MAX_ATTEMPTS: raise Failure(Error.LIMIT)
            envelope = account.envelope(operation)
            account.check_prepared(envelope)
            account.credential()
            row['attempts'].append(dict(number=len(row['attempts']) + 1, state=State.SUBMITTING.value,
                                        reason='submission_intent_committed', digest=envelope.digest))
            row.update(state=State.SUBMITTING.value, reason='submission_intent_committed')
            attempt = len(row['attempts'])
        # Phase two holds SQLite's writer lock through bounded transport/result
        # commit. Recovery waits/fails busy rather than stealing an active worker.
        # If recovery wins the gap before this lock, the state check blocks sending.
        try:
            with self.repository.transaction(lease, until) as account:
                row = account.row(operation)
                if row['state'] != State.SUBMITTING.value or len(row['attempts']) != attempt:
                    raise Failure(Error.TRANSITION)
                envelope = account.envelope(operation)
                try:
                    account.check_prepared(envelope)
                    credential = account.credential()
                    if lease.cancelled.is_set() or time.monotonic() >= until:
                        raise Failure(Error.CANCELLED)
                except Failure as error:
                    state, reason = State.FAILED, error.code.value
                else:
                    try:
                        outcome = self.transport.submit(envelope, credential, lease.cancelled, until)
                    except Exception:
                        outcome = Outcome.UNKNOWN  # Never infer 'not sent' from an exception.
                    if type(outcome) is not Outcome: outcome = Outcome.UNKNOWN
                    state, reason = {
                        Outcome.ACCEPTED: (State.ACCEPTED, 'server_accepted_not_delivered'),
                        Outcome.REJECTED: (State.FAILED, 'definitive_rejection'),
                        Outcome.UNKNOWN: (State.UNKNOWN, 'acceptance_unknown_duplicate_risk'),
                    }[outcome]
                row.update(state=state.value, reason=reason)
                row['attempts'][-1].update(state=state.value, reason=reason)
                delivered = result(operation, row)
            return delivered
        except Failure:
            # Durable Submitting survives any credential/lock/result-commit failure.
            # Recovery must conservatively classify it Unknown, even if this caller
            # happens to know a transport was not invoked. Never return Accepted.
            return DeliveryResult(operation, State.UNKNOWN, 'recover_durable_submission_intent', attempt)

    def recover(self, lease: Lease) -> tuple[OperationId, ...]:
        recovered = []
        with self.repository.transaction(lease, deadline()) as account:
            for ident, row in account.records.items():
                if row['state'] == State.SUBMITTING.value:
                    row.update(state=State.UNKNOWN.value, reason='interrupted_acceptance_unknown')
                    row['attempts'][-1].update(state=State.UNKNOWN.value, reason=row['reason'])
                    recovered.append(OperationId(ident))
        return tuple(recovered)  # Never calls transport or automatically retries.

    def retry(self, lease: Lease, operation: OperationId, *, acknowledge_duplicate_risk: bool = False) -> None:
        with self.repository.transaction(lease, deadline()) as account:
            row = account.row(operation)
            if row['state'] not in (State.FAILED.value, State.UNKNOWN.value): raise Failure(Error.TRANSITION)
            if row['state'] == State.UNKNOWN.value and acknowledge_duplicate_risk is not True:
                raise Failure(Error.DUPLICATE)
            if len(row['attempts']) >= MAX_ATTEMPTS: raise Failure(Error.LIMIT)
            account.check_prepared(account.envelope(operation))
            row.update(state=State.PREPARED.value, reason='explicit_retry_same_envelope')
        # Explicit single attempts only: no automatic retry loop, jitter or storms.

    def reconcile(self, lease: Lease, operation: OperationId, observer: Reconciler) -> DeliveryResult:
        if observer.simulation_only is not True: raise Failure(Error.TRANSPORT)
        with self.repository.transaction(lease, deadline()) as account:
            row = account.row(operation)
            if row['state'] != State.UNKNOWN.value: raise Failure(Error.TRANSITION)
            try: observed = observer.lookup(account.envelope(operation), len(row['attempts']))
            except Exception: observed = Outcome.UNKNOWN
            # An absent record/rejection now cannot disprove a past acceptance.
            if observed is Outcome.ACCEPTED:
                row.update(state=State.ACCEPTED.value, reason='simulated_reconciliation_server_accepted')
                row['attempts'][-1].update(state=row['state'], reason=row['reason'])
            delivery = result(operation, row)
        return delivery

    def export_receipt(self, lease, operation, persist):
        delivery = self.inspect(lease, operation)
        try: persist(delivery)
        except Exception: return False
        return True  # Export failure never edits a delivery state or an attempt.
