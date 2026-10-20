"""Read-only attribution; retain earlier checkpoint evidence without rewriting it."""
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
BASE='b96abc45d975c208d37c03bed80e87f6b68c04c2'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def audit():
    m1=json.loads((ROOT/'docs/operations/evidence/hosted-success-run.json').read_text())
    assert m1['headSha']=='023c941ec2ef284f6be28b5a9605f1dca9c28787' and m1['conclusion']=='success'
    assert len(m1['jobs'])==2 and all(j['conclusion']=='success' for j in m1['jobs'])
    for name in ['hosted-windows-2022-023c941.txt','hosted-ubuntu-24.04-023c941.txt']:
        assert sum('37 passed' in line for line in (ROOT/'docs/operations/evidence'/name).read_text().splitlines())==3
    preserved=['experiments/m3','experiments/m4','experiments/m5','core/account_session.py',
               'QuMail-1.0-Research-Audit-Specification.md','docs/operations/evidence/m5']
    assert not subprocess.check_output(['git','diff',BASE,'--name-only','--',*preserved],cwd=ROOT).strip()
    old=json.loads((ROOT/'docs/operations/evidence/m5/input-hashes.json').read_text())
    helpers={path:sha(ROOT/path) for path in ['tmp/m2/target/debug/qumail-m5-provider.exe',
        'tmp/m2/target/debug/qumail-m3-provider.exe','tmp/m2/openssl-install/lib/libcrypto.lib']}
    assert list(helpers.values())==[old['m5_helper_sha256'],old['preserved_m3_helper_sha256'],old['native_libcrypto_sha256']]
    evidence=ROOT/'docs/operations/evidence/m6'
    def names(name): return [s[10:] for s in (evidence/name).read_text().splitlines() if s.startswith('EXECUTED: ')]
    normal,reverse=names('normal.txt'),names('reverse.txt')
    assert len(normal)==len(set(normal))==len(reverse)==21 and normal==list(reversed(reverse))
    paths=[ROOT/p for p in ['main.py','transport/development_google.py','ui/mailbox_window.py']]
    for directory in ['mailbox_client','experiments/m6']:
        paths += [p for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    docs=[ROOT/p for p in ['IMPLEMENTATION_STATUS.md','ARCHITECTURE.md',
        'docs/adrs/007-m6-gmail-mailbox-slice.md','docs/operations/m6-validation.md','docs/operations/m6-gmail-inbox.md']]
    def entries(paths): return [dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(paths)]
    return dict(parent=BASE, attribution='Final runtime working-tree snapshot; audit/docs completed afterward; not results on unchanged parent.',
        preserved_m1_tested_commit=m1['headSha'], preserved_m2_proof='1fc4e55f09e173cec7634d0b2dc776097b552063',
        preserved_runtime_paths=preserved,helper_hashes=helpers,
        environment=dict(python=sys.version,platform=platform.platform(),sqlite=sqlite3.sqlite_version,
            tls=ssl.OPENSSL_VERSION,packages={p:importlib.metadata.version(p) for p in ['PyQt6','pytest','google-auth','google-auth-oauthlib']}),
        tests=normal,inputs=entries(paths),documentation=entries(docs),outputs=entries(evidence.glob('*.txt')))


if __name__=='__main__': print(json.dumps(audit(),indent=2))
