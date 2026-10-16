"""Development-only PyPI metadata check. Not imported or exposed by the MCP server."""
import concurrent.futures
import datetime
import json
from pathlib import Path
import re
import urllib.request

def check(line):
    match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([A-Za-z0-9_.]+) --hash=sha256:([a-f0-9]{64})',line)
    if not match: raise ValueError('invalid_lock_entry')
    name, version, digest = match.groups()
    url = f'https://pypi.org/pypi/{name}/{version}/json'
    with urllib.request.urlopen(url,timeout=20) as response:
        data = json.load(response)
    wheels = [item for item in data['urls'] if item['filename'].endswith('.whl')
              and item['digests']['sha256'] == digest and not item['yanked']]
    if len(wheels) != 1: raise ValueError('wheel_provenance_mismatch')
    info = data['info']
    if name.lower() == 'mcp':
        assert info['project_urls']['Repository'] == 'https://github.com/modelcontextprotocol/python-sdk'
    return {'name':name,'version':version,'wheel':wheels[0]['filename'],'sha256':digest,
            'project_urls':info.get('project_urls'),
            'license':info.get('license_expression') or info.get('license'),
            'pypi_reported_vulnerabilities':[v['id'] for v in data.get('vulnerabilities',[])]}

if __name__ == '__main__':
    lines = [x for x in Path('requirements.lock').read_text().splitlines() if x and not x.startswith('#')]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        packages = list(pool.map(check,lines))
    vulnerable = any(x['pypi_reported_vulnerabilities'] for x in packages)
    report = {'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'source':'https://pypi.org','scope':'Published wheel hashes, project metadata, and PyPI reported advisories; not a source-code security audit.',
              'package_count':len(packages),'packages':packages,
              'result':'REVIEW_REQUIRED' if vulnerable else 'PASS'}
    Path('DEPENDENCIES.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'packages':len(packages),'result':report['result']}))
    raise SystemExit(1 if vulnerable else 0)
