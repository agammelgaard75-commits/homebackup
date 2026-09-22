#!/usr/bin/env python3
"""Check public evidence integrity without printing known credential values."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import tarfile
import tomllib

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report',required=True,type=Path)
    args=parser.parse_args()
    report=args.report.resolve()
    assert report.parent==Path('/home/bot/ai-sysadmin-multi-agent-plan/stage-0')
    assert os.geteuid()==0
    capture=json.loads((report/'capture.json').read_text())
    config=tomllib.loads(Path('/etc/ai-sysadmin/config.toml').read_text())
    secrets={Path(config['ai']['api_key_file']).read_bytes().strip()}
    with tarfile.open(Path(capture['backup_path'])/'deployment-state.tar.gz') as archive:
        secrets.add(archive.extractfile(config['ai']['api_key_file'].lstrip('/')).read().strip())
    def collect(value):
        if isinstance(value,dict):
            for k,v in value.items():
                if re.search(r'password|secret|token|api.?key',k,re.I) and isinstance(v,str) and len(v)>7:
                    secrets.add(v.encode())
                else: collect(v)
        elif isinstance(value,list):
            for v in value: collect(v)
    collect(json.loads(Path('/home/bot/splunk/.secrets/splunk-admin.json').read_text()))
    assert all(secrets)
    leaked=[]
    for p in report.parent.rglob('*'):
        if p.is_file() and any(s in p.read_bytes() for s in secrets):
            leaked.append(str(p.relative_to(report.parent)))
    assert not leaked, 'Known credential detected in public artifact(s): '+', '.join(leaked)
    files=[]
    for p in sorted(report.rglob('*')):
        if p.is_file() and p.name!='evidence-check.json':
            content=p.read_bytes()
            if p.suffix=='.json': json.loads(content)
            files.append({'path':str(p.relative_to(report)),'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)})
    vm=json.loads((report/'vm-tcg-run.json').read_text())
    supplement=json.loads((report/'supplement.json').read_text())
    gate=(vm['guest_completed'] and vm['qemu_returncode']==0 and vm['guest_result']['status']=='PASS'
          and supplement['source_integrity']['all_unchanged'] and supplement['deployment_integrity']['all_unchanged'])
    result={'checked_at':dt.datetime.now(dt.timezone.utc).isoformat(),
            'stage0_baseline_gate_passed':gate,'known_credential_scan_passed':True,
            'known_credential_values_checked':len(secrets),'scope':'Known live/captured AI key and Splunk credential values; not a universal secret detector.',
            'production_health_passed':False,'gateway_acceptance_passed':False,
            'files':files}
    path=report/'evidence-check.json'
    path.write_text(json.dumps(result,indent=2)+'\n'); path.chmod(0o644); os.chown(path,1000,1000)
    print(json.dumps({k:v for k,v in result.items() if k!='files'}))
    return 0 if gate else 1

if __name__=='__main__':
    raise SystemExit(main())
