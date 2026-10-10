"""Explicit isolated suite order/identity/skip check; no secrets in the retained output."""
import argparse
import sys
import uuid
import pytest

class Results:
    def __init__(self, reverse):
        self.reverse=reverse
        self.discovered=[]
        self.passed=[]
        self.skipped=[]

    def pytest_collection_modifyitems(self,items):
        items.sort(key=lambda item:item.nodeid,reverse=self.reverse)
        self.discovered=[item.nodeid for item in items]

    def pytest_runtest_logreport(self,report):
        if report.skipped: self.skipped.append(report.nodeid)
        if report.when=='call' and report.passed: self.passed.append(report.nodeid)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--reverse',action='store_true')
    args=parser.parse_args()
    results=Results(args.reverse)
    code=pytest.main(['experiments/m3/tests','-q','--tb=short',
        '--basetemp=tmp/m3-pytest-'+uuid.uuid4().hex],plugins=[results])
    if code or results.skipped or len(set(results.discovered))!=len(results.discovered) or set(results.passed)!=set(results.discovered):
        raise SystemExit(code or 1)
    print('IDENTITY CHECK:', 'reverse' if args.reverse else 'normal',len(results.passed),'distinct tests passed; zero skips')
    for name in results.passed: print('EXECUTED:',name)
