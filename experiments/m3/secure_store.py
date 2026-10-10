"""Direct Windows Credential Manager API; no selectable/insecure fallback."""
import ctypes as c
from ctypes import wintypes as w
import os
from .types import BoundaryError, Code, OpaqueId


class Credential(c.Structure):
    _fields_ = [('Flags',w.DWORD),('Type',w.DWORD),('TargetName',w.LPWSTR),
        ('Comment',w.LPWSTR),('LastWritten',w.FILETIME),('CredentialBlobSize',w.DWORD),
        ('CredentialBlob',c.POINTER(c.c_ubyte)),('Persist',w.DWORD),
        ('AttributeCount',w.DWORD),('Attributes',c.c_void_p),('TargetAlias',w.LPWSTR),('UserName',w.LPWSTR)]


class WindowsCredentialStore:
    def __init__(self):
        if os.name != 'nt':
            raise BoundaryError(Code.STORE)
        self.api=c.WinDLL('Advapi32.dll',use_last_error=True)
        self.api.CredWriteW.argtypes=[c.POINTER(Credential),w.DWORD]
        self.api.CredReadW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,c.POINTER(c.POINTER(Credential))]
        self.api.CredDeleteW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD]
        for name in ['CredWriteW','CredReadW','CredDeleteW']:
            getattr(self.api,name).restype=w.BOOL
        self.api.CredFree.argtypes=[c.c_void_p]
        self.api.CredFree.restype=None

    def target(self, ident):
        return 'QuMail-M3-Development/'+OpaqueId(ident).value

    def put(self, ident: str, secret: bytes):
        if len(secret)!=32:
            raise BoundaryError(Code.INVALID)
        buf=(c.c_ubyte*32).from_buffer_copy(secret)
        record=Credential(Type=1,TargetName=self.target(ident),CredentialBlobSize=32,
            CredentialBlob=buf,Persist=2,UserName='QuMail M3 local vault')
        try:
            if not self.api.CredWriteW(c.byref(record),0):
                raise BoundaryError(Code.STORE)
        finally:
            c.memset(buf,0,32)

    def get(self, ident: str) -> bytes:
        out=c.POINTER(Credential)()
        if not self.api.CredReadW(self.target(ident),1,0,c.byref(out)):
            raise BoundaryError(Code.STORE)
        try:
            if out.contents.CredentialBlobSize!=32:
                raise BoundaryError(Code.STORE)
            return c.string_at(out.contents.CredentialBlob,32)
        finally:
            c.memset(out.contents.CredentialBlob,0,out.contents.CredentialBlobSize)
            self.api.CredFree(out)

    def delete(self, ident: str):
        if not self.api.CredDeleteW(self.target(ident),1,0) and c.get_last_error()!=1168:
            raise BoundaryError(Code.STORE)
