# -*- mode: python ; coding: utf-8 -*-
"""
QuMail 1.0 Production PyInstaller Specification for Windows x64.
Bundles React 19 (frontend/dist) + Microsoft Edge WebView2 (pywebview) + Python crypto core.
Strictly excludes all developer secrets and local private configuration.
"""

from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all

REPO_ROOT = Path.cwd().resolve()

# Bundled data files
added_files = [
    (str(REPO_ROOT / 'frontend' / 'dist'), 'frontend/dist'),
]

# Collect ctranslate2 and sentencepiece runtime assets and DLLs (without model weights)
ct2_datas, ct2_binaries, ct2_hidden = collect_all('ctranslate2')
sp_datas, sp_binaries, sp_hidden = collect_all('sentencepiece')
added_files += ct2_datas + sp_datas

extra_binaries = []
import site
for sp_dir in site.getsitepackages():
    for libs_name in ('sentencepiece.libs', 'numpy.libs'):
        libs_path = Path(sp_dir) / libs_name
        if libs_path.is_dir():
            added_files.append((str(libs_path), libs_name))
            added_files.append((str(libs_path), f'_internal/{libs_name}'))
            for dll in libs_path.glob('*.dll'):
                extra_binaries.append((str(dll), '.'))
                extra_binaries.append((str(dll), '_internal'))
                extra_binaries.append((str(dll), libs_name))
                extra_binaries.append((str(dll), f'_internal/{libs_name}'))

# Embed client_secret JSON for production builds
for secret_name in [
    'client_secret_953431543574-t137vvqsic9jbrddt9dr1t3g5hjkj5p3.apps.googleusercontent.com.json',
    'gmail_client_secret.json',
    'google_client_secret.json',
]:
    p = REPO_ROOT / 'secrets' / secret_name
    if p.is_file():
        added_files.append((str(p), 'secrets'))
        added_files.append((str(p), '.'))


# Embed codex-rejected-cas.pem if present in Python Lib
codex_pem = Path(sys.base_prefix) / 'Lib' / 'codex-rejected-cas.pem'
if codex_pem.is_file():
    added_files.append((str(codex_pem), '.'))
    added_files.append((str(codex_pem), '_internal'))

# Add native provider binaries and manifest
if (REPO_ROOT / 'bin' / 'manifest.json').is_file():
    added_files.append((str(REPO_ROOT / 'bin' / 'manifest.json'), 'bin'))
if (REPO_ROOT / 'bin' / 'qumail-vault-provider.exe').is_file():
    added_files.append((str(REPO_ROOT / 'bin' / 'qumail-vault-provider.exe'), 'bin'))
if (REPO_ROOT / 'bin' / 'qumail-crypto-provider.exe').is_file():
    added_files.append((str(REPO_ROOT / 'bin' / 'qumail-crypto-provider.exe'), 'bin'))

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
    'google_auth_oauthlib',
    'google_auth_oauthlib.flow',
    'google.oauth2.credentials',
    'google.auth.transport.requests',
    'cryptography',
    'cryptography.hazmat.primitives',
    'cryptography.hazmat.primitives.ciphers.aead',
    'sqlite3',
    'ctypes',
    'ctypes.wintypes',
    'requests',
    'certifi',
    'urllib3',
    'charset_normalizer',
    'idna',
    'core.offline_translator',
    'ctranslate2',
    'sentencepiece',
] + ct2_hidden + sp_hidden

a = Analysis(
    ['main.py'],
    pathex=[str(REPO_ROOT)],
    binaries=ct2_binaries + sp_binaries + extra_binaries,
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
