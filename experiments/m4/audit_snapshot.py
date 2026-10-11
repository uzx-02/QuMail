"""Read-only tested-input/evidence attribution; never opens credential stores."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[2]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == '__main__':
    old = json.loads((ROOT/'docs/operations/evidence/m3/integration/input-hashes.json').read_text())
    for item in old['inputs'] + old['outputs']:
        assert sha(ROOT/item['path']) == item['sha256'], item['path']
    assert sha(ROOT/'docs/operations/m2-reviewer-request.md') == old['reviewer_draft_sha256']
    assert sha(ROOT/'tmp/m2/target/debug/qumail-m3-provider.exe') == old['helper_executable_sha256']
    assert sha(ROOT/'tmp/m2/openssl-install/lib/libcrypto.lib') == old['native_libcrypto_sha256']
    m2 = json.loads((ROOT/'docs/operations/evidence/m2/20261005-input-audit.json').read_text())
    for item in m2['experiment_inputs']:
        assert sha(ROOT/item['path']) == item['sha256'], item['path']
    evidence = ROOT/'docs/operations/evidence/m4'
    def names(path):
        return [line[10:] for line in path.read_text().splitlines() if line.startswith('EXECUTED: ')]
    normal, reverse = names(evidence/'normal.txt'), names(evidence/'reverse.txt')
    assert len(normal) == len(set(normal)) == len(reverse) == 40 and normal == list(reversed(reverse))
    paths = [p for p in (ROOT/'experiments/m4').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    print(json.dumps(dict(parent_checkpoint='1af13a1ee8a58016bdca2dfa25055eb689ec7fd8',
        attribution='M4 tested working-tree source; read-only audit added/executed after suite; no results attributed to unchanged M3 HEAD',
        m2_m3_inputs_and_outputs_preserved=True, reviewer_draft_sha256=old['reviewer_draft_sha256'],
        helper_executable_sha256=old['helper_executable_sha256'], native_libcrypto_sha256=old['native_libcrypto_sha256'],
        environment=dict(python=sys.version, platform=platform.platform(), sqlite=sqlite3.sqlite_version,
            packages={name:importlib.metadata.version(name) for name in
                ['cryptography','google-auth','google-auth-oauthlib','pytest','PyQt6','liboqs-python']}),
        executed_python_tests=normal,
        inputs=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in sorted(paths)],
        outputs=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in sorted(evidence.glob('*.txt'))]), indent=2))
