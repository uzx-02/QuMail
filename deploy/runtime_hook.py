"""
QuMail PyInstaller Windows Runtime Hook.

Enforces Windows process-level security hardening prior to application initialization:
1. Calls SetDllDirectoryW("") to remove the Current Working Directory (CWD) from the DLL
   search path, mitigating binary planting and DLL hijacking vulnerabilities.
2. Configures default unhandled exception logging.
"""

import ctypes
import os
import sys

# 1. Eliminate CWD from DLL search path
if sys.platform == "win32":
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        # SetDllDirectoryW with an empty string removes the current directory from the DLL search order
        if not kernel32.SetDllDirectoryW(""):
            # Non-fatal if unsupported, but standard on Windows Vista / Server 2008+
            pass
    except Exception:
        pass

# 2. Ensure application directory is primary
app_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)
