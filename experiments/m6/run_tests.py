"""Explicit bounded M6 suite, with executed-identity checks and optional reverse order."""
import argparse
import uuid
import pytest
from experiments.m3.run_tests import Results

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--reverse', action='store_true')
    args = parser.parse_args()
    results = Results(args.reverse)
    code = pytest.main(['experiments/m6/test_mailbox.py', 'experiments/m6/test_workflows.py', '-q', '--tb=short', '-rP',
                       '--basetemp=tmp/m6-pytest-'+uuid.uuid4().hex], plugins=[results])
    if code or results.skipped or len(set(results.discovered)) != len(results.discovered) or set(results.passed) != set(results.discovered):
        raise SystemExit(code or 1)
    print('IDENTITY CHECK:', 'reverse' if args.reverse else 'normal', len(results.passed), 'distinct tests passed; zero skips')
    for name in results.passed: print('EXECUTED:', name)
