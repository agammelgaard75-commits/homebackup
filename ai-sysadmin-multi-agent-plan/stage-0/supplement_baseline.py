#!/usr/bin/env python3
"""Read-only deployment detail and end-of-run integrity checks."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tomllib

def run(argv):
    p=subprocess.run(argv,text=True,capture_output=True,timeout=45)
    return {'argv':argv,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report',required=True,type=Path)
    args=parser.parse_args()
    report=args.report.resolve()
    assert report.parent==Path('/home/bot/ai-sysadmin-multi-agent-plan/stage-0')
    assert os.geteuid()==0
    config=tomllib.loads(Path('/etc/ai-sysadmin/config.toml').read_text())
    key=Path(config['ai']['api_key_file']).read_text().strip()
    data={'at':dt.datetime.now(dt.timezone.utc).isoformat(),'live_controller_invoked':False}
    units=['ai-sysadmin-prepare.service','ai-sysadmin-maintenance.service','ai-sysadmin-prepare.timer','ai-sysadmin-maintenance.timer']
    definition=run(['systemctl','cat',*units])
    definition['stdout']=re.sub(r'(?m)^(Environment|EnvironmentFile|SetCredential|SetCredentialEncrypted)=.*$',r'\1=[REDACTED]',definition['stdout'])
    data['unit_definitions']=definition
    data['unit_states']=run(['systemctl','show',*units,'--property=Id,MainPID,ActiveState,SubState,UnitFileState,NextElapseUSecRealtime,Result,ExecMainStatus'])
    data['failed_units']=run(['systemctl','list-units','--state=failed,auto-restart','--no-legend','--plain','--all'])
    data['maintenance_journal']=run(['journalctl','-u','ai-sysadmin-maintenance.service','-n','15','--no-pager'])
    metadata=[]
    for path in sorted(Path('/opt/litellm/venv/lib').glob('python*/site-packages/*.dist-info/METADATA')):
        head=path.read_text(errors='replace').split('\n\n',1)[0]
        name=re.search(r'^Name: (.+)$',head,re.M)
        version=re.search(r'^Version: (.+)$',head,re.M)
        if name and version:
            metadata.append({'name':name[1],'version':version[1],'metadata_path':str(path)})
    data['python_metadata']=metadata
    data['manual_manifests']=[]
    for path in sorted(Path('/opt').glob('*/etc/splunk.version')):
        values=dict(line.split('=',1) for line in path.read_text().splitlines() if '=' in line)
        data['manual_manifests'].append({'path':str(path),**{k:values.get(k) for k in ('PRODUCT','VERSION','BUILD')}})
    data['registrations']={'docker':config.get('containers',{}),
        'manual':config.get('manual',{}),'pip':config.get('pip',{}),
        'note':'Inventory and installed metadata do not authorize updates. The captured v1 configuration has Docker registration only; no manual/pip update registrations.'}
    data['n8n_identity']=run(['docker','inspect','n8n','--format','{{.Name}} {{.Config.Image}} {{.Image}} {{.State.Status}}'])
    data['n8n_digests']=run(['docker','image','inspect','docker.n8n.io/n8nio/n8n:latest','--format','{{json .RepoDigests}}'])
    data['latest_plan']={}
    state=Path(config['paths']['state_dir'])
    change=(state/'current-change').read_text().strip()
    assert re.fullmatch(r'CHG-\d{8}(?:-R\d+)?',change)
    plan=json.loads((state/(change+'.plan.json')).read_text())
    data['latest_plan']={'change_id':change,'generated_at':plan.get('generated_at'),
                         'blocked_reasons':plan.get('blocked_reasons'),'ai_assessment':plan.get('ai_assessment')}
    for file,keyname in [('source-manifest.json','source_integrity'),('deployment-manifest.json','deployment_integrity')]:
        manifest=json.loads((report/file).read_text())
        rows=manifest['files'] if isinstance(manifest,dict) else manifest
        results=[]
        for row in rows:
            if row['type']!='file' or not re.fullmatch(r'[0-9a-f]{64}',row.get('sha256','')):
                continue
            path=Path(row['path'])
            if keyname=='deployment_integrity' and str(path).startswith(('/var/lib/','/var/log/')):
                continue
            results.append({'path':str(path),'unchanged':path.is_file() and sha(path)==row['sha256']})
        data[keyname]={'files_checked':len(results),'all_unchanged':all(r['unchanged'] for r in results),
                       'changed_files':[r for r in results if not r['unchanged']]}
    data['snap_state']=run(['snap','list','lxd'])
    data['package_tooling_state']=run(['dpkg-query','-W','-f=${binary:Package}\t${db:Status-Status}\n','qemu-system-x86','qemu-system-common','libslirp0'])
    data['download_only_validation_packages']=[{'filename':p.name,'sha256':sha(p),
        'identity':run(['dpkg-deb','-f',str(p),'Package','Version'])}
        for p in sorted(Path('/tmp/ai-sysadmin-stage0-vm.cZs7Rw/qemu-download').glob('*.deb'))]
    raw=json.dumps(data,indent=2,sort_keys=True)+'\n'
    if key: raw=raw.replace(key,'[REDACTED]')
    path=report/'supplement.json'
    path.write_text(raw); path.chmod(0o644); os.chown(path,1000,1000)
    print(json.dumps({'source':data['source_integrity'],'deployment':data['deployment_integrity'],
                      'python_distributions':len(metadata),'latest_plan':data['latest_plan']}))

if __name__=='__main__':
    main()
