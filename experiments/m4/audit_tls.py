"""Read-only current attribution; historical manifests validated against their commit."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sqlite3
import ssl
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
BASE='b833e8b38892ba84bc0be3e0ab5cf29607c6d479'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__=='__main__':
    old=json.loads((ROOT/'docs/operations/evidence/m4/input-hashes.json').read_text())
    for item in old['inputs']+old['outputs']:
        blob=subprocess.check_output(['git','show',BASE+':'+item['path']],cwd=ROOT)
        assert hashlib.sha256(blob).hexdigest()==item['sha256'],item['path']
    for item in old['outputs']: assert sha(ROOT/item['path'])==item['sha256'],item['path']
    m3=json.loads((ROOT/'docs/operations/evidence/m3/integration/input-hashes.json').read_text())
    for item in m3['inputs']+m3['outputs']:
        if item['path']=='experiments/m3/vault.py': continue
        assert sha(ROOT/item['path'])==item['sha256'],item['path']
    m2=json.loads((ROOT/'docs/operations/evidence/m2/20261005-input-audit.json').read_text())
    for item in m2['experiment_inputs']: assert sha(ROOT/item['path'])==item['sha256'],item['path']
    assert sha(ROOT/'docs/operations/m2-reviewer-request.md')==old['reviewer_draft_sha256']
    assert sha(ROOT/'tmp/m2/target/debug/qumail-m3-provider.exe')==old['helper_executable_sha256']
    assert sha(ROOT/'tmp/m2/openssl-install/lib/libcrypto.lib')==old['native_libcrypto_sha256']
    evidence=ROOT/'docs/operations/evidence/m4/tls'
    def names(path): return [line[10:] for line in path.read_text().splitlines() if line.startswith('EXECUTED: ')]
    normal,reverse=names(evidence/'normal.txt'),names(evidence/'reverse.txt')
    assert len(normal)==len(set(normal))==len(reverse)==85 and normal==list(reversed(reverse))
    paths=[ROOT/'experiments/m3/vault.py']+[p for p in (ROOT/'experiments/m4').rglob('*')
        if p.is_file() and '__pycache__' not in p.parts]
    print(json.dumps(dict(parent_checkpoint=BASE,
        attribution='Final working-tree source; audit script/docs completed after runtime tests; not results on unchanged parent',
        historical_m4_manifest_matches_parent_commit=True,
        changed_m3_source='experiments/m3/vault.py: deterministic connection closure; affected suite rerun',
        reviewer_draft_sha256=old['reviewer_draft_sha256'],
        helper_executable_sha256=old['helper_executable_sha256'],native_libcrypto_sha256=old['native_libcrypto_sha256'],
        environment=dict(python=sys.version,platform=platform.platform(),sqlite=sqlite3.sqlite_version,
            smtp_tls=ssl.OPENSSL_VERSION,packages={name:importlib.metadata.version(name) for name in
                ['cryptography','google-auth','google-auth-oauthlib','pytest','PyQt6','liboqs-python']}),
        executed_python_tests=normal,
        inputs=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(paths)],
        outputs=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(evidence.glob('*.txt'))]),indent=2))
