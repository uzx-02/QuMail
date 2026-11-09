# -*- mode: python ; coding: utf-8 -*-
"""
QuMail Production PyInstaller Specification for Windows x64.

Bundles the QuMail desktop client, PyQt6 GUI runtime, and native Release
cryptographic providers into a self-contained, reproducible distribution directory.
"""

from pathlib import Path
import sys

block_cipher = None
REPO_ROOT = Path.cwd().resolve()

added_files = [
    (str(REPO_ROOT / 'bin' / 'qumail-m3-provider.exe'), 'bin'),
    (str(REPO_ROOT / 'bin' / 'qumail-m5-provider.exe'), 'bin'),
    (str(REPO_ROOT / 'bin' / 'manifest.json'), 'bin'),
]

if (REPO_ROOT / 'version.json').is_file():
    added_files.append((str(REPO_ROOT / 'version.json'), '.'))

hidden_imports = [
    'PyQt6',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PyQt6.sip',
    'cryptography',
    'cryptography.hazmat.primitives',
    'cryptography.hazmat.primitives.ciphers.aead',
    'sqlite3',
    'email',
    'email.mime',
    'email.policy',
    'google.auth',
    'google.oauth2',
    'google_auth_oauthlib',
    'ctypes',
    'ctypes.wintypes',
]

a = Analysis(
    ['main.py'],
    pathex=[str(REPO_ROOT)],
    binaries=added_files,
    datas=[],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['deploy/runtime_hook.py'],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'numpy',
        'pandas',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='QuMail',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='x86_64',
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='QuMail',
)
