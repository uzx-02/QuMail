# Compatibility bridge forwarding legacy milestone import to production core domain
from core.crypto_envelope.model import *
import core.crypto_envelope.model as _mod
for _k, _v in _mod.__dict__.items():
    if not _k.startswith('__'):
        globals()[_k] = _v