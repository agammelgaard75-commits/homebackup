#!/usr/bin/env python3
"""Offline VM-only restore/test runner. Never run this on the production host."""
import base64
import copy
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import traceback
from unittest.mock import Mock


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert Path('/etc/stage0-disposable-guest').exists(), 'VM marker required'
    assert Path('/sys/class/dmi/id/product_name').read_text().strip().startswith(('Standard PC','QEMU')), 'Disposable QEMU VM required'
    payload = Path('/mnt/stage0')
    work = Path('/work')
    work.mkdir(exist_ok=True)
    evidence = work/'evidence'
    evidence.mkdir(exist_ok=True)
    result={'started_at':dt.datetime.now(dt.timezone.utc).isoformat(),
            'isolation':'QEMU TCG Ubuntu 24.04 guest; no NIC; read-only seed ISO; private writable qcow2 disk',
            'os_release':Path('/etc/os-release').read_text()}
    try:
        expected = json.loads((payload/'capture.json').read_text())['backup_archive_sha256']
        assert sha(payload/'deployment-state.tar.gz') == expected
        restore = Path('/restore')
        restore.mkdir()
        with tarfile.open(payload/'deployment-state.tar.gz') as archive:
            archive.extractall(restore, filter='data')
        manifest=json.loads((payload/'deployment-manifest.private.json').read_text())
        verified=0
        for row in manifest:
            target=restore/row['path'].lstrip('/')
            if row['type']=='file':
                assert sha(target)==row['sha256'], row['path']
                os.chmod(target,int(row['mode'],8))
                os.chown(target,row['uid'],row['gid'])
                assert target.stat().st_uid==row['uid'] and target.stat().st_gid==row['gid']
                assert target.stat().st_mode & 0o7777 == int(row['mode'],8)
                verified+=1
        result['restore']={'status':'PASS','regular_files_verified':verified,'file_hashes_and_permissions_verified':True,
                           'services_activated':False,'credentials_printed':False}
        with tarfile.open(payload/'source.tar.gz') as archive:
            archive.extractall(work,filter='data')
        source=work/'sysadmin'
        frozen=json.loads((payload/'source-manifest.json').read_text())
        source_count=0
        for row in frozen['files']:
            if row['type']=='file':
                relative=Path(row['path']).relative_to('/home/bot/sysadmin')
                assert sha(source/relative)==row['sha256']
                source_count+=1
        result['source_restore']={'status':'PASS','files_verified':source_count}
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONUNBUFFERED':'1'}
        commands=[('unit_tests',['python3','-B','-m','unittest','discover','-s','tests','-v']),
                  ('full_validation',['/bin/sh','scripts/validate.sh'])]
        for name,cmd in commands:
            start=dt.datetime.now(dt.timezone.utc)
            output=subprocess.run(cmd,cwd=source,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
            (evidence/(name+'.log')).write_text(output.stdout)
            summaries=[line for line in output.stdout.splitlines() if line.startswith(('Ran ','OK','FAILED','Validation passed','ERROR:','FAIL:'))]
            result[name]={'returncode':output.returncode,'summary':summaries,'log_sha256':sha(evidence/(name+'.log')),
                          'seconds':(dt.datetime.now(dt.timezone.utc)-start).total_seconds()}
        sys.path[:0]=[str(source/'src'),str(source/'tests')]
        from test_lifecycle import LifecycleTests
        from ai_sysadmin import record_status
        fixtures=evidence/'fixtures'
        fixtures.mkdir()
        def export_case(case,label):
            dest=fixtures/label
            dest.mkdir()
            for p in case.c.state.rglob('*'):
                if p.is_file() and (p.suffix in ('.txt','.json') or p.name=='current-change'):
                    relative=p.relative_to(case.c.state)
                    (dest/relative).parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(p,dest/relative)
        case=LifecycleTests(); case.setUp()
        case.c.approved_upgrade=Mock(return_value=([],[],[]))
        assert case.c.prepare()==0
        export_case(case,'PREPARED')
        assert case.c.maintain()==0
        export_case(case,'CLOSED')
        before={str(p):p.read_bytes() for p in case.c.state.rglob('*') if p.is_file()}
        with __import__('unittest.mock',fromlist=['patch']).patch.object(case.c,'command',wraps=case.c.command) as calls:
            assert case.c.maintain()==0
            assert calls.call_count==0
        assert before=={str(p):p.read_bytes() for p in case.c.state.rglob('*') if p.is_file()}
        result['no_change_repeat']={'status':'PASS','first_maintenance':0,'second_maintenance':0,
                                    'second_run_command_count':0,'state_bytes_unchanged':True,
                                    'scope':'Existing controller with deterministic healthy/no-update fixtures inside the offline VM; no live package transaction'}
        case.doCleanups()
        case=LifecycleTests(); case.setUp()
        assert case.c.prepare()==0
        case.healthy['root_free_percent']=1
        assert case.c.maintain()==2
        export_case(case,'FAILED')
        parent=case.record().stem
        case.healthy['root_free_percent']=80
        assert case.c.prepare(retry_of=parent,reason='Synthetic Stage 0 fixture: reviewed failure')==0
        export_case(case,'RETRY')
        case.doCleanups()
        for label in ('EXPIRED','TAMPERED','MISSING_POINTER'):
            case=LifecycleTests(); case.setUp(); assert case.c.prepare()==0
            planpath=next(case.c.state.glob('*.plan.json'))
            if label=='EXPIRED':
                plan=json.loads(planpath.read_text()); plan.pop('sha256')
                plan['generated_at']=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=72)).isoformat()
                plan['sha256']=hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()
                planpath.write_text(json.dumps(plan,indent=2)+'\n')
            elif label=='TAMPERED':
                plan=json.loads(planpath.read_text()); plan['reasoning']='Altered without updating checksum'
                planpath.write_text(json.dumps(plan,indent=2)+'\n')
            else:
                (case.c.state/'current-change').unlink()
            export_case(case,label); case.doCleanups()
        result['fixture_types']=sorted(p.name for p in fixtures.iterdir())
        (evidence/'fixtures-origin.json').write_text(json.dumps({'origin':'Synthetic fixtures generated from the frozen controller and existing test harness in an offline VM','production_records_included':False},indent=2)+'\n')
        result['status']='PASS' if all(result[n]['returncode']==0 for n,_ in commands) else 'FAIL'
    except Exception as exc:
        result.update(status='ERROR',error_type=type(exc).__name__,error=str(exc))
        (evidence/'runner-error.log').write_text(traceback.format_exc())
    result['completed_at']=dt.datetime.now(dt.timezone.utc).isoformat()
    (evidence/'vm-result.json').write_text(json.dumps(result,indent=2)+'\n')
    compressed=io.BytesIO()
    with tarfile.open(fileobj=compressed,mode='w:gz') as archive:
        archive.add(evidence,arcname='evidence')
    print('STAGE0_RESULT_JSON='+json.dumps(result,sort_keys=True),flush=True)
    print('STAGE0_EVIDENCE_BASE64='+base64.b64encode(compressed.getvalue()).decode(),flush=True)
    print('STAGE0_GUEST_COMPLETE',flush=True)
    subprocess.run(['systemctl','poweroff'],check=False)


if __name__=='__main__':
    main()
