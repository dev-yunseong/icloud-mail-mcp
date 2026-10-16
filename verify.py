"""Offline validation and deliberately small heuristic secret scan; no packages/network."""
import contextlib
import io
import json
from importlib.metadata import version
from pathlib import Path
import re
import sys
import unittest

FILES = ['.gitignore','README.md','THREAT_MODEL.md','core.py','fixtures.py','demo.py',
         'http_guard.py','server.py','tests/test_core.py','tests/test_protocol.py',
         'verify.py','VALIDATION.json','requirements.lock','audit_dependencies.py','DEPENDENCIES.json']
PATTERNS = [r'gh[pousr]_[A-Za-z0-9]{30,}', r'github_pat_[A-Za-z0-9_]{30,}',
            r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
            r'\b[a-z]{4}(?:-[a-z]{4}){3}\b']

def main():
    root = Path(__file__).parent
    sdk_version = version('mcp')  # Full verification requires the reviewed SDK environment.
    problems = []
    for name in FILES:
        path = root / name
        if not path.exists() and name == 'VALIDATION.json': continue
        data = path.read_text(encoding='utf-8')
        if any(re.search(pattern,data) for pattern in PATTERNS):
            problems.append(name)  # Never print matched values.
        if path.suffix == '.py':
            compile(data,name,'exec')
    capture = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(root/'tests'))
    result = unittest.TextTestRunner(stream=capture,verbosity=2).run(suite)
    report = {'python':sys.version.split()[0], 'tests_run':result.testsRun,
              'failures':len(result.failures),'errors':len(result.errors),
              'secret_scan':'PASS' if not problems else 'FAIL',
              'scan_scope':'explicit source/doc allowlist; heuristic, not a security guarantee',
              'live_mailbox_access':False,'listener_started':False,
              'mcp_sdk_version':sdk_version,
              'mcp_sdk_integration':'in-process ASGI + official SDK client; see test_protocol.py',
              'result':'PASS' if result.wasSuccessful() and not problems else 'FAIL'}
    (root/'VALIDATION.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(capture.getvalue())
    print(json.dumps(report,indent=2))
    return 0 if report['result']=='PASS' else 1

if __name__ == '__main__': raise SystemExit(main())
