"""Read-only hash attribution for the asynchronous Windows Settings checkpoint."""
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
BASE='f39bc5429658ec3009b9ce10c3f1cd39c21db3ef'
EVIDENCE=ROOT/'docs/operations/evidence/m6-settings'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def audit():
    preserved=['experiments/m2','experiments/m4','experiments/m5','experiments/m3/provider.py',
        'experiments/m3/secure_store.py','experiments/m3/Cargo.lock','core/account_session.py',
        'transport','mailbox_client','packaging','.github','QuMail-1.0-Research-Audit-Specification.md',
        'docs/operations/evidence/m1','docs/operations/evidence/m2','docs/operations/evidence/m3',
        'docs/operations/evidence/m4','docs/operations/evidence/m5','docs/operations/evidence/m6',
        'docs/operations/evidence/m6-workflows','docs/operations/evidence/m6-windows']
    assert not subprocess.check_output(['git','diff',BASE,'--name-only','--',*preserved],cwd=ROOT).strip()
    prior=json.loads((ROOT/'docs/operations/evidence/m6-windows/input-hashes.json').read_text(encoding='utf-8'))
    helpers={p:sha(ROOT/p) for p in prior['helper_hashes']}
    assert helpers==prior['helper_hashes']
    def names(name):
        return [line[10:] for line in (EVIDENCE/name).read_text(encoding='utf-8').splitlines() if line.startswith('EXECUTED: ')]
    suites={name:names(name) for name in ['normal.txt','focused-reverse.txt','m3.txt']}
    for name,count in [('normal.txt',82),('focused-reverse.txt',17),('m3.txt',54)]:
        assert len(suites[name])==len(set(suites[name]))==count
        assert 'zero skips' in (EVIDENCE/name).read_text(encoding='utf-8')
    focused=[n for n in suites['normal.txt'] if n.startswith('experiments/m6/test_settings.py::')]
    assert focused==list(reversed(suites['focused-reverse.txt']))
    roots=['experiments/m3','experiments/m4','experiments/m5','experiments/m6','mailbox_client',
        'ui/identity_settings.py','ui/mailbox_window.py','ui/mail_actions.py','ui/mail_accessibility.py',
        'core/identity_service.py','core/account_session.py','core/settings_operations.py',
        'transport/development_google.py','transport/bounded_google.py','transport/bounded_worker.py',
        'transport/network_worker.py','main.py','packaging']
    paths=set(subprocess.check_output(['git','ls-files','--',*roots],cwd=ROOT,text=True).splitlines())
    paths.update(['core/settings_operations.py','experiments/m6/test_settings.py','experiments/m6/audit_settings.py'])
    docs=['IMPLEMENTATION_STATUS.md','ARCHITECTURE.md','docs/adrs/008-m6-mail-workflows.md',
        'docs/operations/m6-validation.md','docs/operations/m6-settings-validation.md',
        'docs/operations/m3-development-settings.md','docs/operations/m3-recovery.md','docs/operations/m6-gmail-inbox.md']
    def entries(paths): return [dict(path=p,sha256=sha(ROOT/p)) for p in paths]
    return dict(parent=BASE,attribution='Final M6 82, focused reverse 17 and M3 54 executed against these runtime/test bytes. Docs/audit written afterward; not unchanged parent HEAD.',
        preserved_paths=preserved,helper_hashes=helpers,
        preserved_m1=prior['preserved_m1'],preserved_m2=prior['preserved_m2'],
        environment=dict(python=sys.version,platform=platform.platform(),tls=ssl.OPENSSL_VERSION,sqlite=sqlite3.sqlite_version,
            packages={p:importlib.metadata.version(p) for p in ['PyQt6','pytest','google-auth','google-auth-oauthlib']}),
        tests=suites,inputs=entries(sorted(paths)),documentation=entries(docs),
        outputs=entries([p.relative_to(ROOT).as_posix() for p in sorted(EVIDENCE.glob('*.txt'))]))


if __name__=='__main__': print(json.dumps(audit(),indent=2))
