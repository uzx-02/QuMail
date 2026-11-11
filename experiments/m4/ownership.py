# Compatibility bridge forwarding legacy milestone import to production core domain
from core.outbox.ownership import *
import core.outbox.ownership as _mod
for _k, _v in _mod.__dict__.items():
    if not _k.startswith('__'):
        globals()[_k] = _v