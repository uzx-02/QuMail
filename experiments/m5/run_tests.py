"""Explicit M5 suite identity/order check, no optional skips."""
import argparse
import uuid
import pytest
from experiments.m3.run_tests import Results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--reverse', action='store_true')
    args = parser.parse_args()
    results = Results(args.reverse)
    code = pytest.main(['experiments/m5/tests', '-q', '--tb=short', '-rP',
                       '--basetemp=tmp/m5-pytest-'+uuid.uuid4().hex], plugins=[results])
    if code or results.skipped or len(set(results.discovered)) != len(results.discovered) or set(results.passed) != set(results.discovered):
        raise SystemExit(code or 1)
    print('IDENTITY CHECK:', 'reverse' if args.reverse else 'normal', len(results.passed), 'distinct tests passed; zero skips')
    for name in results.passed: print('EXECUTED:', name)
