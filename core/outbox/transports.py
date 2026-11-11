"""Deterministic injected transport observations, never an SMTP implementation."""
import time
from .model import Outcome


class SimulatedTransport:
    simulation_only = True

    def __init__(self, outcome=Outcome.ACCEPTED):
        self.outcome = outcome
        self.calls = []

    def submit(self, envelope, credential, cancel, deadline):
        if credential.context != envelope.account: raise ValueError('scoped_handle_mismatch')
        if cancel.is_set() or time.monotonic() >= deadline: return Outcome.REJECTED
        self.calls.append(envelope)
        return self.outcome
