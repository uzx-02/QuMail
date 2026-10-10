"""Read-only integrated snapshot attribution; no credential or user data reads."""
import hashlib
import json
from pathlib import Path
import tomllib

ROOT=Path(__file__).resolve().parents[2]
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

if __name__=='__main__':
    old=json.loads((ROOT/'docs/operations/evidence/m2/20261005-input-audit.json').read_text())
    for item in old['experiment_inputs']: assert sha(ROOT/item['path'])==item['sha256'],item['path']
    def packages(path):
        return {(p['name'],p['version']):(p.get('source'),p.get('checksum'))
            for p in tomllib.loads(path.read_text())['package'] if not p['name'].startswith('qumail-')}
    assert packages(ROOT/'experiments/m2/Cargo.lock')==packages(ROOT/'experiments/m3/provider/Cargo.lock')
    assert sha(ROOT/'tmp/m2/openssl-install/lib/libcrypto.lib')==old['native_libcrypto_sha256']
    evidence=ROOT/'docs/operations/evidence/m3/integration'
    def names(path): return [line[10:] for line in path.read_text().splitlines() if line.startswith('EXECUTED: ')]
    normal,reverse=names(evidence/'normal.txt'),names(evidence/'reverse.txt')
    assert len(normal)==len(set(normal))==len(reverse)==54 and normal==list(reversed(reverse))
    paths=[ROOT/p for p in ['main.py','core/account_session.py','core/identity_service.py',
        'transport/development_google.py','ui/identity_settings.py']]
    paths += [p for p in (ROOT/'experiments/m3').rglob('*') if p.is_file() and '__pycache__' not in p.parts and 'target' not in p.parts]
    manifest=dict(parent_checkpoint='ef4b3086d8eac16fd65a3a34f107e75ad4966ec4',
        attribution='Integrated M3 working-tree snapshot; not execution on unchanged parent HEAD',
        m2_inputs_preserved=True,third_party_cargo_inputs_equal_m2=True,
        native_libcrypto_sha256=old['native_libcrypto_sha256'],
        helper_executable_sha256=sha(ROOT/'tmp/m2/target/debug/qumail-m3-provider.exe'),
        reviewer_draft_sha256=sha(ROOT/'docs/operations/m2-reviewer-request.md'),
        executed_python_tests=normal,
        inputs=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(paths)],
        outputs=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(evidence.glob('*.txt'))])
    print(json.dumps(manifest,indent=2))
