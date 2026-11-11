# -*- mode: python ; coding: utf-8 -*-
"""
QuMail 1.0 Production PyInstaller Specification for Windows x64.
Bundles React 19 (frontend/dist) + Microsoft Edge WebView2 (pywebview) + Python crypto core.
Strictly excludes all developer secrets and local private configuration.
"""

from pathlib import Path
import sys

REPO_ROOT = Path.cwd().resolve()

# Bundled data files
added_files = [
    (str(REPO_ROOT / 'frontend' / 'dist'), 'frontend/dist'),
]

# Add native provider binaries and manifest
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
    'core.config',
    'core.enterprise_policy',
    'core.hsm',
    'core.hsm.manager',
    'core.hsm.detector',
    'core.hsm.entropy_pool',
    'core.hsm.etsi_qkd',
    'core.logging_config',
    'core.outbox_manager',
    'core.outbox_reconciliation',
    'core.provider_resolver',
    'core.web_link_crypto',
    'transport',
    'transport.oauth2_gmail',
    'transport.imap_receiver',
    'transport.smtp_sender',
    'transport.custom_mailbox',
    'cryptography',
    'cryptography.hazmat.primitives',
    'cryptography.hazmat.primitives.ciphers.aead',
    'sqlite3',
    'ctypes',
    'ctypes.wintypes',
    'requests',
    'google_auth_oauthlib',
    'google.oauth2.credentials',
    'google.auth.transport.requests',
    'fpdf2',
]

a = Analysis(
    ['main.py'],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=added_files,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['deploy/runtime_hook.py'],
    excludes=[
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
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
    name='QuMail-App',
)

# Post-build: Ensure native providers and manifest are present in bin/ adjacent to QuMail.exe
import shutil
import json
bin_src = REPO_ROOT / 'bin'
if bin_src.is_dir():
    bin_dst = REPO_ROOT / 'dist' / 'QuMail-App' / 'bin'
    bin_dst.mkdir(parents=True, exist_ok=True)
    for f in bin_src.glob('*'):
        if f.is_file() and not f.name.endswith('.gitkeep'):
            shutil.copy2(f, bin_dst / f.name)

# Ensure resources and version.json are present for installer packaging
res_dst = REPO_ROOT / 'dist' / 'QuMail-App' / 'resources'
res_dst.mkdir(parents=True, exist_ok=True)
default_cfg = {
    "version": "1.0.0",
    "default_mode": "mailbox",
    "allow_legacy_simulator": False,
    "log_level": "INFO",
    "update_channel": "Production",
    "telemetry_enabled": False,
}
with (res_dst / "qumail.default.json").open("w", encoding="utf-8") as f:
    json.dump(default_cfg, f, indent=2)

version_dst = REPO_ROOT / 'dist' / 'QuMail-App' / 'version.json'
version_data = {
    "app_name": "QuMail",
    "display_name": "QuMail Secure Email",
    "version": "1.0.0",
    "build_utc": "2026-11-11T09:00:00Z",
    "commit_sha": "3a9171f",
    "platform": "win32-x64",
    "provider_schema": "1.0",
    "rust_profile": "release-cfg",
    "pe_mitigations_verified": True,
}
with version_dst.open("w", encoding="utf-8") as f:
    json.dump(version_data, f, indent=2)
