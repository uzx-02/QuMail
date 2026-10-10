"""Coherent development account state. Deliberately separate from legacy Session."""
from dataclasses import dataclass,field
import threading
from PyQt6.QtCore import QObject,pyqtSignal
from experiments.m3.types import AccountContext,KeyHandle


@dataclass(frozen=True,repr=False)
class AccountView:
    context: AccountContext
    key: KeyHandle
    address: str
    root: str
    lifecycle: str


@dataclass(frozen=True)
class Snapshot:
    generation: int=0
    locked: bool=True
    accounts: tuple=()
    active: AccountView|None=None


@dataclass(frozen=True,repr=False)
class Ticket:
    generation: int
    active: AccountView|None
    cancelled: threading.Event=field(default_factory=threading.Event)


class DevelopmentSession(QObject):
    changed=pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.snapshot=Snapshot()
        self.ticket=None
        self._mutex=threading.RLock()

    def invalidate(self):
        with self._mutex:
            if self.ticket: self.ticket.cancelled.set()
            self.ticket=None
            s=self.snapshot
            self.snapshot=Snapshot(s.generation+1,s.locked,s.accounts,s.active)

    def install(self,accounts=(),active=None,locked=False):
        with self._mutex:
            self.invalidate()
            self.snapshot=Snapshot(self.snapshot.generation,locked,tuple(accounts),active)
            self.changed.emit(self.snapshot)  # All fields installed before notification.

    def begin(self):
        with self._mutex:
            self.invalidate()
            self.ticket=Ticket(self.snapshot.generation,self.snapshot.active)
            return self.ticket

    def current(self,ticket):
        return (ticket is self.ticket and not ticket.cancelled.is_set() and
                ticket.generation==self.snapshot.generation and ticket.active==self.snapshot.active)

    def complete(self,ticket,commit):
        with self._mutex:
            if not self.current(ticket): return False
            commit()  # No late result is allowed to persist or install anything.
            if self.ticket is ticket: self.invalidate()
            return True
