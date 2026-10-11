"""Internal encrypted-record encoding; not an email wire format."""
import base64


def pack(value): return base64.b64encode(value).decode('ascii')
def unpack(value): return base64.b64decode(value, validate=True)
