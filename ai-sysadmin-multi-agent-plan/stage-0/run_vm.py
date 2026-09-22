#!/usr/bin/env python3
"""Restore a captured baseline only inside a NIC-less disposable QEMU guest."""
import argparse
import base64
import datetime as dt
import hashlib
import io
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tarfile

IMAGE_SHA256='612b2c0cc1bc413a6cb8c38fd611794caf0f2b436c50013d8b3794db12ad7354'
IMAGE_URL='https://cloud-images.ubuntu.com/noble/20260911/noble-server-cloudimg-amd64.img'

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report',required=True,type=Path)
    parser.add_argument('--image',required=True,type=Path)
    parser.add_argument('--name',default='vm')
    parser.add_argument('--qemu-root',type=Path)
    args=parser.parse_args()
    assert os.geteuid()==0
    report=args.report.resolve()
    assert report.parent==Path('/home/bot/ai-sysadmin-multi-agent-plan/stage-0')
    capture=json.loads((report/'capture.json').read_text())
    backup=Path(capture['backup_path']).resolve()
    assert backup.parent==Path('/var/backups/ai-sysadmin-migration')
    assert sha(args.image)==IMAGE_SHA256, 'Ubuntu image checksum mismatch'
    os.umask(0o077)
    assert re.fullmatch(r'vm(?:-[a-z0-9]+)?',args.name)
    vm=backup/args.name
    vm.mkdir(mode=0o700)
    payload=vm/'payload'
    payload.mkdir(mode=0o700)
    for name in ('source.tar.gz','deployment-state.tar.gz','deployment-manifest.private.json'):
        shutil.copyfile(backup/name,payload/name)
    for name in ('capture.json','source-manifest.json'):
        shutil.copyfile(report/name,payload/name)
    source=Path(__file__).resolve().parent
    for name,dest in [('guest_validate.py','guest_validate.py'),('vm-user-data','user-data'),
                      ('vm-meta-data','meta-data'),('vm-network-config','network-config')]:
        shutil.copyfile(source/name,payload/dest)
    shutil.copyfile(args.image,vm/'ubuntu-noble.img')
    snap=Path('/snap/lxd/current').resolve()
    env={**os.environ,'LD_LIBRARY_PATH':':'.join(str(snap/p) for p in
         ('lib/x86_64-linux-gnu','lib/x86_64-linux-gnu/ceph','usr/lib/x86_64-linux-gnu'))}
    qemu=snap/'bin/qemu-system-x86_64'
    if args.qemu_root:
        qemu_root=args.qemu_root.resolve()
        qemu=qemu_root/'usr/bin/qemu-system-x86_64'
        env['LD_LIBRARY_PATH']=str(qemu_root/'usr/lib/x86_64-linux-gnu')+':'+env['LD_LIBRARY_PATH']
        env['QEMU_MODULE_DIR']=str(qemu_root/'usr/lib/x86_64-linux-gnu/qemu')
    subprocess.run([str(snap/'bin/genisoimage'),'-quiet','-R','-J','-V','cidata','-o',str(vm/'seed.iso'),str(payload)],env=env,check=True)
    subprocess.run([str(snap/'bin/qemu-img'),'create','-f','qcow2','-F','qcow2','-b',str(vm/'ubuntu-noble.img'),str(vm/'guest.qcow2'),'12G'],env=env,check=True)
    cmd=[str(qemu),'-L',str(snap/'share/qemu'),
         '-machine','q35,accel=tcg','-cpu','max','-smp','2','-m','2048',
         '-nic','none','-display','none','-monitor','none','-no-reboot',
         '-serial','file:'+str(vm/'console.log'),
         '-drive','file='+str(vm/'guest.qcow2')+',format=qcow2,if=virtio',
         '-drive','file='+str(vm/'seed.iso')+',format=raw,media=cdrom,readonly=on']
    run={'started_at':dt.datetime.now(dt.timezone.utc).isoformat(),'argv':cmd,
         'image_url':IMAGE_URL,'image_sha256':IMAGE_SHA256,'qemu_bundle':str(snap),
         'qemu_binary_sha256':sha(qemu),'qemu_version':subprocess.check_output([str(qemu),'--version'],env=env,text=True),
         'guest_harness_sha256':sha(source/'guest_validate.py'),
         'host_network_changes':False,'guest_nic':False,'live_restore':False}
    print('Starting offline Ubuntu restore VM; console retained in root-private backup.',flush=True)
    try:
        with (vm/'qemu.log').open('w') as log:
            completed=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1500)
        run['qemu_returncode']=completed.returncode
    except subprocess.TimeoutExpired:
        run['qemu_returncode']=124
    run['completed_at']=dt.datetime.now(dt.timezone.utc).isoformat()
    console=(vm/'console.log').read_text(errors='replace') if (vm/'console.log').exists() else ''
    result_lines=[line.split('STAGE0_RESULT_JSON=',1)[1] for line in console.splitlines() if 'STAGE0_RESULT_JSON=' in line]
    evidence_lines=[line.split('STAGE0_EVIDENCE_BASE64=',1)[1] for line in console.splitlines() if 'STAGE0_EVIDENCE_BASE64=' in line]
    run['guest_completed']='STAGE0_GUEST_COMPLETE' in console
    if result_lines:
        run['guest_result']=json.loads(result_lines[-1])
    if evidence_lines:
        decoded=base64.b64decode(evidence_lines[-1],validate=True)
        with tarfile.open(fileobj=io.BytesIO(decoded),mode='r:gz') as archive:
            assert all(m.name=='evidence' or m.name.startswith('evidence/') for m in archive.getmembers())
            assert not any(m.issym() or m.islnk() for m in archive.getmembers())
            archive.extractall(report,filter='data')
        for p in [report/'evidence',*(report/'evidence').rglob('*')]:
            os.chown(p,1000,1000)
            p.chmod(0o755 if p.is_dir() else 0o644)
    path=report/(args.name+'-run.json')
    path.write_text(json.dumps(run,indent=2)+'\n')
    path.chmod(0o644); os.chown(path,1000,1000)
    print(json.dumps(run.get('guest_result',{'guest_completed':run['guest_completed'],'qemu_returncode':run['qemu_returncode']})),flush=True)
    return 0 if run['guest_completed'] and run.get('guest_result',{}).get('status')=='PASS' else 1

if __name__=='__main__':
    raise SystemExit(main())
