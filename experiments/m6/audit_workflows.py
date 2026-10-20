"""Read-only attribution for the M6 workflow continuation, not a test substitute."""
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
BASE='2c0eed635bb66740f8365ee89b81e04470a7f515'
EVIDENCE=ROOT/'docs/operations/evidence/m6-workflows'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def audit():
    preserved=['experiments/m3','experiments/m5','core/account_session.py','core/identity_service.py',
        'transport/development_google.py','packaging','QuMail-1.0-Research-Audit-Specification.md',
        'docs/operations/evidence/m6','docs/operations/evidence/m5']
    assert not subprocess.check_output(['git','diff',BASE,'--name-only','--',*preserved],cwd=ROOT).strip()
    prior=json.loads((ROOT/'docs/operations/evidence/m6/input-hashes.json').read_text())
    helpers={path:sha(ROOT/path) for path in prior['helper_hashes']}
    assert helpers==prior['helper_hashes']
    def names(name):
        return [line[10:] for line in (EVIDENCE/name).read_text().splitlines() if line.startswith('EXECUTED: ')]
    normal,reverse=names('normal.txt'),names('reverse.txt')
    assert len(normal)==len(set(normal))==len(reverse)==52 and normal==list(reversed(reverse))
    assert len(names('m4.txt'))==85 and len(names('m5.txt'))==55 and len(names('m3.txt'))==54
    source_roots=['experiments/m3','experiments/m4','experiments/m5','experiments/m6',
        'mailbox_client','ui/mailbox_window.py','ui/mail_actions.py','ui/identity_settings.py',
        'core/account_session.py','core/identity_service.py','transport/development_google.py','main.py','packaging']
    tracked=subprocess.check_output(['git','ls-files','--',*source_roots],cwd=ROOT,text=True).splitlines()
    added=['mailbox_client/smtp.py','mailbox_client/workflows.py','ui/mail_actions.py',
           'experiments/m6/test_workflows.py','experiments/m6/audit_workflows.py']
    paths=sorted(set(tracked+added))
    docs=['IMPLEMENTATION_STATUS.md','ARCHITECTURE.md','README.md','docs/adrs/007-m6-gmail-mailbox-slice.md',
        'docs/adrs/008-m6-mail-workflows.md','docs/operations/m6-validation.md','docs/operations/m6-gmail-inbox.md']
    def entries(paths): return [dict(path=p,sha256=sha(ROOT/p)) for p in paths]
    return dict(parent=BASE,attribution='Executed on the final runtime working-tree bytes recorded below; not on unchanged parent HEAD. Audit and documentation written after tests.',
        preserved_paths=preserved,helper_hashes=helpers,
        preserved_m1='023c941ec2ef284f6be28b5a9605f1dca9c28787',
        preserved_m2='1fc4e55f09e173cec7634d0b2dc776097b552063',
        environment=dict(python=sys.version,platform=platform.platform(),tls=ssl.OPENSSL_VERSION,sqlite=sqlite3.sqlite_version,
            packages={p:importlib.metadata.version(p) for p in ['PyQt6','pytest','google-auth','google-auth-oauthlib']}),
        tests=normal,inputs=entries(paths),documentation=entries(docs),
        outputs=entries([p.relative_to(ROOT).as_posix() for p in sorted(EVIDENCE.glob('*.txt'))]),
        initial_results='initial-48.txt predates final refinements; initial-order-assumption.txt is a retained 1-fail/50-pass development run, not final evidence.')


if __name__=='__main__': print(json.dumps(audit(),indent=2))
