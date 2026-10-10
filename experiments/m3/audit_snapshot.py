"""Read-only test correspondence check and source-input manifest generator."""
import hashlib
import json
from pathlib import Path
import subprocess
import tomllib

ROOT=Path(__file__).resolve().parents[2]

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def packages(path):
    return {(p['name'],p['version']):(p.get('source'),p.get('checksum'))
        for p in tomllib.loads(path.read_text())['package'] if not p['name'].startswith('qumail-')}

if __name__=='__main__':
    baseline=json.loads((ROOT/'docs/operations/evidence/m3/input-hashes.json').read_text())
    if any(sha(ROOT/i['path'])!=i['sha256'] for i in baseline['experiment_inputs']):
        raise SystemExit('Historical ef4b308 snapshot differs; use audit_integration for current results.')
    old=json.loads((ROOT/'docs/operations/evidence/m2/20261005-input-audit.json').read_text())
    for item in old['experiment_inputs']: assert sha(ROOT/item['path'])==item['sha256'],item['path']
    assert packages(ROOT/'experiments/m2/Cargo.lock')==packages(ROOT/'experiments/m3/provider/Cargo.lock')
    assert sha(ROOT/'tmp/m2/openssl-install/lib/libcrypto.lib')==old['native_libcrypto_sha256']
    evidence=ROOT/'docs/operations/evidence/m3'
    def names(path):
        return [line[10:] for line in path.read_text().splitlines() if line.startswith('EXECUTED: ')]
    n,r=names(evidence/'normal.txt'),names(evidence/'reverse.txt')
    assert len(n)==len(set(n))==len(r)==32 and n==list(reversed(r))
    inputs=[]
    for path in sorted((ROOT/'experiments/m3').rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and 'target' not in path.parts:
            inputs.append(dict(path=path.relative_to(ROOT).as_posix(),sha256=sha(path)))
    print(json.dumps(dict(parent_checkpoint='1fc4e55f09e173cec7634d0b2dc776097b552063',
        attribution='M3 tested working-tree inputs, not unchanged parent HEAD',
        m2_15_inputs_unchanged=True,third_party_cargo_inputs_equal_m2=True,
        native_libcrypto_sha256=old['native_libcrypto_sha256'],
        helper_executable_sha256=sha(ROOT/'tmp/m2/target/debug/qumail-m3-provider.exe'),
        m2_reviewer_draft_sha256=sha(ROOT/'docs/operations/m2-reviewer-request.md'),
        normal_reverse_same_tests=n,experiment_inputs=inputs,
        retained_outputs=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p))
            for p in sorted(evidence.glob('*.txt'))]),indent=2))
