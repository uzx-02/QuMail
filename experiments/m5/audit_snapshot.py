"""Read-only attribution of the tested M5 snapshot and preserved earlier evidence."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sqlite3
import ssl
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = 'b00693cbaba92037b3dec8c9e35d866650a5018f'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def names(path):
    return [line[10:] for line in path.read_text().splitlines() if line.startswith('EXECUTED: ')]


def audit():
    old = json.loads((ROOT/'docs/operations/evidence/m4/tls/input-hashes.json').read_text())
    for item in old['inputs'] + old['outputs']:
        assert sha(ROOT/item['path']) == item['sha256'], item['path']
    # Also validate historical M2/M3 inputs and historical M4 inputs at their commit.
    subprocess.run([sys.executable, '-m', 'experiments.m4.audit_tls'], cwd=ROOT,
                   stdout=subprocess.DEVNULL, check=True)
    for path in ['QuMail-1.0-Research-Audit-Specification.md', 'core/account_session.py']:
        blob = subprocess.check_output(['git', 'show', BASE+':'+path], cwd=ROOT)
        assert hashlib.sha256(blob).hexdigest() == sha(ROOT/path), path
    for name in ['Cargo.toml', 'Cargo.lock']:
        prior = (ROOT/'experiments/m3/provider'/name).read_bytes()
        assert (ROOT/'experiments/m5/provider'/name).read_bytes() == prior.replace(
            b'qumail-m3-provider', b'qumail-m5-provider'), name
    evidence = ROOT/'docs/operations/evidence/m5'
    normal, reverse = names(evidence/'normal.txt'), names(evidence/'reverse.txt')
    assert len(normal) == len(set(normal)) == len(reverse) == 55
    assert normal == list(reversed(reverse))
    paths = [p for p in (ROOT/'experiments/m5').rglob('*')
             if p.is_file() and '__pycache__' not in p.parts]
    paths += [ROOT/p for p in ['experiments/m3/provider/src/provider.rs',
                              'experiments/m2/inputs.json', 'core/account_session.py',
                              'QuMail-1.0-Research-Audit-Specification.md']]
    docs = [ROOT/p for p in ['IMPLEMENTATION_STATUS.md', 'ARCHITECTURE.md',
                            'docs/adrs/006-m5-development-message-boundary.md',
                            'docs/operations/m5-validation.md']]
    def entries(items):
        return [dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in sorted(items)]
    return dict(parent_checkpoint=BASE,
        attribution='Runtime tests on the M5 working-tree source, not unchanged parent HEAD. Audit script and documentation completed after runtime tests.',
        previous_milestone_inputs_and_outputs_match=True,
        reviewer_draft_sha256=old['reviewer_draft_sha256'],
        preserved_m3_helper_sha256=old['helper_executable_sha256'],
        native_libcrypto_sha256=old['native_libcrypto_sha256'],
        m5_helper_sha256=sha(ROOT/'tmp/m2/target/debug/qumail-m5-provider.exe'),
        environment=dict(python=sys.version, platform=platform.platform(), sqlite=sqlite3.sqlite_version,
            smtp_tls=ssl.OPENSSL_VERSION, packages={name:importlib.metadata.version(name) for name in
                ['cryptography','google-auth','google-auth-oauthlib','pytest','PyQt6','liboqs-python']}),
        executed_python_tests=normal, inputs=entries(paths), documentation=entries(docs),
        outputs=entries(evidence.glob('*.txt')))


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2))
