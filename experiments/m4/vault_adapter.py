# Compatibility bridge forwarding legacy milestone import to production core domain
from core.outbox.vault_adapter import *
import core.outbox.vault_adapter as _mod
for _k, _v in _mod.__dict__.items():
    if not _k.startswith('__'):
        globals()[_k] = _v