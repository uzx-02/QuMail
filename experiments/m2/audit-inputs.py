"""Read-only source/build audit; emits hashes, never key/message contents."""
import hashlib
import json
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[2]
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

upstream = ROOT / 'tmp/m2/probe-source/sequoia-openpgp-2.4.1'
patched = ROOT / 'tmp/m2/probe-sequoia'
changed = []
files = 0
for original in upstream.rglob('*'):
    if not original.is_file():
        continue
    rel = original.relative_to(upstream)
    copy = patched / rel
    assert copy.is_file(), f'Missing source file: {rel}'
    files += 1
    if original.read_bytes() != copy.read_bytes():
        changed.append(rel.as_posix())
assert sorted(changed) == ['Cargo.toml', 'src/lib.rs'], changed
original = (upstream / 'src/lib.rs').read_text(encoding='utf-8')
actual = (patched / 'src/lib.rs').read_text(encoding='utf-8')
accessor = '''
/// QuMail isolated M2 diagnostic accessor. No algorithm/RNG/verification changes.
#[cfg(feature = "qumail-m2-fault-probe")]
pub fn qumail_m2_probe_context() -> *mut std::ffi::c_void {
    crypto::backend::context().ptr().cast()
}
'''
assert actual == original + accessor, 'Unexpected diagnostic code change'
manifest = (upstream / 'Cargo.toml').read_text().replace('[features]', '[features]\nqumail-m2-fault-probe = []')
assert (patched / 'Cargo.toml').read_text().rstrip() == manifest.rstrip()

def packages(path):
    lock = tomllib.loads(path.read_text())
    return {(p['name'], p['version']): (p.get('source'), p.get('checksum'))
            for p in lock['package'] if not p['name'].startswith('qumail-') and p['name'] != 'sequoia-openpgp'}
assert packages(ROOT / 'experiments/m2/Cargo.lock') == packages(ROOT / 'experiments/m2/backend-probe/Cargo.lock'), 'Unexpected transitive version/source/checksum change'
native = ROOT / 'tmp/m2/openssl-install/lib/libcrypto.lib'
assert digest(native) == '5ceb47b86bec9b3b8d6e666e718947391c59f8763be1347b0e3c2a692e022241'
normal = (ROOT / 'tmp/m2/20261005-normal.log').read_text(encoding='utf-8-sig')
reverse = (ROOT / 'tmp/m2/20261005-reverse.log').read_text(encoding='utf-8-sig')
def identities(log):
    return [line.removeprefix('EXECUTED: ') for line in log.splitlines() if line.startswith('EXECUTED: ')]
n, r = identities(normal), identities(reverse)
assert len(n) == len(r) == 17 and len(set(n)) == 17 and sorted(n) == sorted(r)
inputs = []
for file in sorted((ROOT / 'experiments/m2').rglob('*')):
    if file.is_file() and 'target' not in file.parts and '__pycache__' not in file.parts:
        inputs.append({'path': file.relative_to(ROOT).as_posix(), 'sha256': digest(file)})
print(json.dumps({'source_files_compared': files, 'only_changed_upstream_files': changed,
    'patched_source_hashes': {name: digest(patched / name) for name in changed},
    'transitive_locks_identical_except_diagnostic_sequoia': True,
    'native_libcrypto_sha256': digest(native), 'normal_reverse_same_17_tests': sorted(n),
    'experiment_inputs': inputs}, indent=2))
