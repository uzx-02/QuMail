"""Classification only. No reader invocation or modern-error fallback."""
from dataclasses import dataclass
from enum import Enum
from email.parser import BytesHeaderParser
from email.policy import default
from .model import MAX_WIRE, MAX_HEADERS, Failure, Code


class Kind(str,Enum):
    MODERN='openpgp_requires_modern_verification'
    LEGACY='legacy_unverified_compatibility_gate'
    CONVENTIONAL='conventional_unverified'


@dataclass(frozen=True,repr=False)
class Classified:
    kind: Kind
    original: bytes


def classify(raw):
    if type(raw) is not bytes or len(raw)>MAX_WIRE: raise Failure(Code.LIMIT)
    header=raw.replace(b'\r\n',b'\n').split(b'\n\n',1)[0]
    if len(header)>MAX_HEADERS: raise Failure(Code.LIMIT)
    node=BytesHeaderParser(policy=default).parsebytes(header+b'\n\n')
    if len(node.get_all('Content-Type',[]))!=1: raise Failure(Code.INVALID)
    # Modern-looking structures take precedence over any attacker-added legacy hint.
    if node.get_param('protocol')=='application/pgp-encrypted' or b'-----BEGIN PGP MESSAGE-----' in raw:
        kind=Kind.MODERN
    elif node.get_content_type()=='multipart/encrypted' and node.get_param('protocol')=='application/qumail-pgp':
        kind=Kind.LEGACY
    elif node.get_content_type()=='multipart/encrypted': kind=Kind.MODERN
    else: kind=Kind.CONVENTIONAL
    return Classified(kind,raw)
