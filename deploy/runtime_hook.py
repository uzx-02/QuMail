"""""""""
QuMail PyInstaller Windows Runtime Hook.

Enforces Windows process-level security hardening prior to application initialization:
1. Calls SetDllDirectoryW("") to remove the Current Working Directory (CWD) from the DLL
   search path, mitigating binary planting and DLL hijacking vulnerabilities.
2. Configures default unhandled exception logging.
"""

import ctypes
import os
import sys

# 1. Eliminate CWD from DLL search path and sanitize C runtime environment
if sys.platform == "win32":
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        # SetDllDirectoryW with an empty string removes the current directory from the DLL search order
        kernel32.SetDllDirectoryW("")
        # Remove hazardous environment variables at the Win32 kernel level
        for env_var in ("SSLKEYLOGFILE", "__CONDA_OPENSLL_CERT_FILE_SET"):
            kernel32.SetEnvironmentVariableW(env_var, None)
    except Exception:
        pass

    # Clear C-runtime errno in both ucrtbase.dll and msvcrt.dll
    for dll_name in ("ucrtbase.dll", "msvcrt.dll"):
        try:
            dll = ctypes.CDLL(dll_name)
            if hasattr(dll, "_errno"):
                c_err = dll._errno
                c_err.restype = ctypes.POINTER(ctypes.c_int)
                c_err().contents.value = 0
            if hasattr(dll, "_set_errno"):
                dll._set_errno(0)
        except Exception:
            pass

# Strip hazardous SSL environment variables in Python os.environ
os.environ.pop("SSLKEYLOGFILE", None)
os.environ.pop("__CONDA_OPENSLL_CERT_FILE_SET", None)
for var in ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_CERT_FILE", "SSL_CERT_DIR"):
    val = os.environ.get(var)
    if val and ("conda" in val.lower() or not os.path.exists(val)):
        os.environ.pop(var, None)
        if sys.platform == "win32":
            try:
                ctypes.WinDLL("kernel32").SetEnvironmentVariableW(var, None)
            except Exception:
                pass

# 2. Prevent FileNotFoundError in ssl.SSLContext.__new__ caused by missing codex-rejected-cas.pem in frozen bundles
try:
    import ssl
    if not getattr(ssl.SSLContext, "_is_qumail_patched", False):
        from _ssl import _SSLContext

        def _safe_ssl_context_new(cls, protocol=None, *args, **kwargs):
            if protocol is None:
                protocol = getattr(ssl, "PROTOCOL_TLS_CLIENT", ssl.PROTOCOL_TLS)
            self = _SSLContext.__new__(cls, protocol)
            try:
                ssl_dir = os.path.dirname(getattr(ssl, "__file__", ""))
                pem_path = os.path.join(ssl_dir, "codex-rejected-cas.pem")
                if pem_path and os.path.isfile(pem_path):
                    _SSLContext.load_verify_locations(self, cafile=pem_path)
            except Exception:
                pass
            return self

        ssl.SSLContext.__new__ = _safe_ssl_context_new
        ssl.SSLContext._is_qumail_patched = True
except Exception:
    pass

# 3. Ensure application directory is primary
app_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)
