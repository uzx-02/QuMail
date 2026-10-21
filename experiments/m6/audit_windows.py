"""Read-only attribution of Windows M6 continuation; not execution evidence itself."""
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
BASE='6f4d5fcb62ae0fbae7be68739e0242a4468d750d'
EVIDENCE=ROOT/'docs/operations/evidence/m6-windows'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def audit():
    preserved=['experiments/m3','experiments/m4','experiments/m5','core/account_session.py',
        'transport/development_google.py','packaging','QuMail-1.0-Research-Audit-Specification.md',
        'docs/operations/evidence/m1','docs/operations/evidence/m2','docs/operations/evidence/m3',
        'docs/operations/evidence/m4','docs/operations/evidence/m5','docs/operations/evidence/m6',
        'docs/operations/evidence/m6-workflows']
    assert not subprocess.check_output(['git','diff',BASE,'--name-only','--',*preserved],cwd=ROOT).strip()
    prior=json.loads((ROOT/'docs/operations/evidence/m6-workflows/input-hashes.json').read_text())
    helpers={p:sha(ROOT/p) for p in prior['helper_hashes']}
    assert helpers==prior['helper_hashes']
    def names(name):
        return [line[10:] for line in (EVIDENCE/name).read_text().splitlines() if line.startswith('EXECUTED: ')]
    suites={name:names(name) for name in ['normal.txt','focused.txt','m3.txt']}
    for name,count in [('normal.txt',65),('focused.txt',13),('m3.txt',54)]:
        assert len(suites[name])==len(set(suites[name]))==count
        assert 'zero skips' in (EVIDENCE/name).read_text()
    assert set(suites['focused.txt'])<=set(suites['normal.txt'])
    roots=['experiments/m3','experiments/m4','experiments/m5','experiments/m6','mailbox_client',
        'ui/mailbox_window.py','ui/mail_actions.py','ui/identity_settings.py','ui/mail_accessibility.py',
        'core/account_session.py','core/identity_service.py','transport/development_google.py',
        'transport/bounded_google.py','transport/bounded_worker.py','transport/network_worker.py','main.py','packaging']
    paths=set(subprocess.check_output(['git','ls-files','--',*roots],cwd=ROOT,text=True).splitlines())
    paths.update(['experiments/m6/audit_windows.py','experiments/m6/test_windows.py','experiments/m6/blocking_worker.py',
        'mailbox_client/connection.py','transport/bounded_google.py','transport/bounded_worker.py',
        'transport/network_worker.py','ui/mail_accessibility.py'])
    docs=['IMPLEMENTATION_STATUS.md','ARCHITECTURE.md','docs/adrs/008-m6-mail-workflows.md',
        'docs/operations/m6-validation.md','docs/operations/m6-windows-validation.md',
        'docs/operations/m6-gmail-inbox.md','docs/operations/m6-google-acceptance.md']
    def entries(paths): return [dict(path=p,sha256=sha(ROOT/p)) for p in paths]
    return dict(parent=BASE,attribution='Final M6 65-test run and focused 13-test run executed against these runtime/source bytes, not unchanged parent HEAD. M3 54-test run preceded only the final outbox table busy-control refinement and two new M6 tests. Docs/audit written afterward.',
        preserved_paths=preserved,helper_hashes=helpers,
        preserved_m1='023c941ec2ef284f6be28b5a9605f1dca9c28787',preserved_m2='1fc4e55f09e173cec7634d0b2dc776097b552063',
        environment=dict(python=sys.version,platform=platform.platform(),tls=ssl.OPENSSL_VERSION,sqlite=sqlite3.sqlite_version,
            packages={p:importlib.metadata.version(p) for p in ['PyQt6','pytest','google-auth','google-auth-oauthlib']}),
        tests=suites,inputs=entries(sorted(paths)),documentation=entries(docs),
        outputs=entries([p.relative_to(ROOT).as_posix() for p in sorted(EVIDENCE.glob('*.txt'))]))


if __name__=='__main__': print(json.dumps(audit(),indent=2))
