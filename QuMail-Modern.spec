# -*- mode: python ; coding: utf-8 -*-
"""
QuMail 1.0 Modern Desktop PyInstaller Specification.
Bundles React 19 (frontend/dist) + Microsoft Edge WebView2 (pywebview) + Python crypto core.
"""

from pathlib import Path
import sys

REPO_ROOT = Path.cwd().resolve()

# Bundled data files
added_files = [
    (str(REPO_ROOT / 'frontend' / 'dist'), 'frontend/dist'),
]

# Add secret credentials if present
if (REPO_ROOT / 'secrets' / 'gmail_client_secret.json').is_file():
    added_files.append((str(REPO_ROOT / 'secrets' / 'gmail_client_secret.json'), 'secrets'))

# Add native provider binaries and manifest if present
if (REPO_ROOT / 'bin' / 'manifest.json').is_file():
    added_files.append((str(REPO_ROOT / 'bin' / 'manifest.json'), 'bin'))
if (REPO_ROOT / 'bin' / 'qumail-m3-provider.exe').is_file():
    added_files.append((str(REPO_ROOT / 'bin' / 'qumail-m3-provider.exe'), 'bin'))
if (REPO_ROOT / 'bin' / 'qumail-m5-provider.exe').is_file():
    added_files.append((str(REPO_ROOT / 'bin' / 'qumail-m5-provider.exe'), 'bin'))

hidden_imports = [
    'webview',
    'webview.platforms.winforms',
    'clr_loader',
    'pythonnet',
    'http.server',
    'socketserver',
    'core',
    'core.hsm',
    'core.hsm.manager',
    'core.hsm.detector',
    'core.hsm.entropy_pool',
    'core.hsm.etsi_qkd',
    'core.logging_config',
    'transport',
    'transport.oauth2_gmail',
    'transport.imap_receiver',
    'transport.smtp_sender',
    'transport.custom_mailbox',
    'cryptography',
    'sqlite3',
    'ctypes',
    'ctypes.wintypes',
    'requests',
    'google_auth_oauthlib',
    'google.oauth2.credentials',
    'google.auth.transport.requests',
]

a = Analysis(
    ['launch_react_desktop.py'],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=added_files,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

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
    target_arch=None,
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
    name='QuMail-Modern',
)

# Post-build: Ensure secrets directory is present directly next to QuMail.exe
import shutil
secrets_src = REPO_ROOT / 'secrets'
if secrets_src.is_dir():
    secrets_dst = REPO_ROOT / 'dist' / 'QuMail-Modern' / 'secrets'
    secrets_dst.mkdir(parents=True, exist_ok=True)
    for f in secrets_src.glob('*'):
        if f.is_file():
            shutil.copy2(f, secrets_dst / f.name)
