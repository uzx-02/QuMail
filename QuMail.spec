# -*- mode: python ; coding: utf-8 -*-
"""
QuMail 1.0 Production PyInstaller Specification for Windows x64.
Bundles React 19 (frontend/dist) + Microsoft Edge WebView2 (pywebview) + Python crypto core.
Strictly excludes all developer secrets and local private configuration.
"""

from pathlib import Path
import os
import sys
import json
import shutil
from PyInstaller.utils.hooks import collect_all

REPO_ROOT = Path.cwd().resolve()

# Bundled data files
added_files = [
    (str(REPO_ROOT / 'frontend' / 'dist'), 'frontend/dist'),
]

# A distributable Desktop OAuth client is a public-client resource, not a
# per-user setting.  The release engineer supplies its local, ignored JSON
# path at build time; the file is embedded under a stable name without ever
# being copied into the repository.  Refuse to produce a shareable build
# without it, preventing the old first-run "import client_secret.json" trap.
release_oauth_config = os.environ.get('QUMAIL_RELEASE_OAUTH_CONFIG', '').strip()
if not release_oauth_config:
    raise SystemExit(
        'QUMAIL_RELEASE_OAUTH_CONFIG must point to the approved Desktop OAuth '
        'client JSON for a distributable QuMail build.'
    )
release_oauth_path = Path(release_oauth_config).expanduser().resolve()
if not release_oauth_path.is_file():
    raise SystemExit(f'Release OAuth configuration not found: {release_oauth_path}')

# The directory endpoint is public configuration.  It is emitted by the build
# rather than relying on a developer shell environment on recipient machines.
release_directory_url = os.environ.get('QUMAIL_RELEASE_DIRECTORY_URL', '').strip()
if not release_directory_url.startswith('https://'):
    raise SystemExit('QUMAIL_RELEASE_DIRECTORY_URL must be an HTTPS directory endpoint.')

# Create non-secret release metadata before Analysis so PyInstaller includes it
# in the actual one-directory bundle, regardless of --distpath.
release_resources_dir = REPO_ROOT / 'build' / 'release_resources'
release_resources_dir.mkdir(parents=True, exist_ok=True)
release_oauth_bundle_path = release_resources_dir / 'google_oauth_client.json'
shutil.copy2(release_oauth_path, release_oauth_bundle_path)
release_metadata_path = release_resources_dir / 'qumail.release.json'
release_metadata_path.write_text(
    json.dumps({'directory_url': release_directory_url}, indent=2), encoding='utf-8'
)
default_metadata_path = release_resources_dir / 'qumail.default.json'
default_metadata_path.write_text(
    json.dumps({
        'version': '1.0.0',
        'default_mode': 'mailbox',
        'allow_legacy_simulator': False,
        'log_level': 'INFO',
        'update_channel': 'Test',
        'telemetry_enabled': False,
    }, indent=2), encoding='utf-8'
)
added_files.extend([
    (str(release_oauth_bundle_path), 'resources'),
    (str(release_metadata_path), 'resources'),
    (str(default_metadata_path), 'resources'),
])

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
