"""Audited, bounded restoration for this host; refuses repeated tree replacement."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import sys
import tarfile

ROOT=Path('/home/bot/sysadmin')
DEPLOY=Path('/home/bot/splunk/deployment')
sys.path.insert(0,str(ROOT/'src'))
from ai_sysadmin import Controller, atomic_write
c=Controller(Path('/etc/ai-sysadmin/config.toml'))
backup=c.state/'splunk-integration-20260913'
backup.mkdir(mode=0o700,exist_ok=True)
plan=(ROOT/'reports/2026-09-13-splunk-integration.md').read_text()
atomic_write(backup/'change-plan.md',plan)
c.event('decision','Restore and integrate local Splunk as requested',change_id='SPLUNK-20260913',plan=plan)
c.event('anomaly','Local Splunk unavailable: startup wrapper and prior runtime state missing',severity='high',change_id='SPLUNK-20260913',service='Splunkd.service')

def action(name,argv,mutate=False,timeout=120):
    r=c.command(name,argv,timeout=timeout,mutate=mutate)
    if r['returncode']:
        c.event('closure','Splunk restoration stopped; inspect audited action',status='FAILED',action=name,change_id='SPLUNK-20260913')
        raise SystemExit(r['returncode'])
    return r

with Path('/home/bot/splunk/automation/state/lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    home=Path('/opt/splunk')
    preserved=Path('/opt/splunk-incomplete-20260913')
    staging=Path('/opt/splunk-recovery-staging-20260913')
    if '--resume' not in sys.argv:
        assert not preserved.exists() and not staging.exists(), 'Restore already attempted; review state'
        assert not (home/'etc/passwd').exists() and not (home/'var/lib/splunk').exists(), 'Unexpected existing runtime data'
        archive=Path('/home/bot/splunk/downloads/splunk-9.3.14-02bbaf562558-Linux-x86_64.tgz')
        expected='7d9a4dba1e78ce8f1a3352b174acacd0989c6c5b6e78dc35b6653458d7f44688125d94f2c9bf11feac4f5fa4b904a8986ee2c1bbd63a53a3a00083a9e5d84af6'
        with archive.open('rb') as f: digest=hashlib.file_digest(f,'sha512').hexdigest()
        assert digest==expected, 'Installer checksum mismatch'
        c.event('verification','Cached installer SHA-512 matched saved vendor checksum',sha512=digest)
        action('stop_broken_splunk_restart_loop',['systemctl','stop','Splunkd.service'],True)
        atomic_write(backup/'ai-sysadmin-config.toml',Path('/etc/ai-sysadmin/config.toml').read_text())
        shutil.copy2('/home/bot/splunk/evidence/splunk-ca.pem',backup/'prior-splunk-ca.pem')
        atomic_write(backup/'log-permissions.json',json.dumps({str(p):{'uid':p.stat().st_uid,'gid':p.stat().st_gid,'mode':oct(p.stat().st_mode&0o7777)} for p in [c.logs,*c.logs.glob('*.jsonl')]}))
        staging.mkdir(mode=0o700)
        c.event('command_start','Extract verified Splunk archive into isolated staging',action='extract_splunk',archive=str(archive),destination=str(staging))
        with tarfile.open(archive) as tf:
            assert all(m.name=='splunk' or m.name.startswith('splunk/') for m in tf.getmembers())
            tf.extractall(staging,filter='data')
        c.event('command_result','Archive extraction completed',action='extract_splunk',returncode=0)
        home.rename(preserved)
        (staging/'splunk').rename(home)
        staging.rmdir()
        c.event('change','Incomplete Splunk tree preserved and verified distribution installed',preserved=str(preserved),version='9.3.14')
    else:
        assert preserved.exists() and 'VERSION=9.3.14' in (home/'etc/splunk.version').read_text()
        assert not (home/'etc/passwd').exists(), 'Initialization already completed; do not reseed account'
        c.event('recovery','Resume verified extraction after missing initial launch configuration was identified')
    for source in (DEPLOY/'system-local').glob('*.conf'):
        shutil.copy2(source,home/'etc/system/local'/source.name)
    launch=home/'etc/splunk-launch.conf'
    text=(launch if launch.exists() else home/'etc/splunk-launch.conf.default').read_text()
    for setting,value in [('SPLUNK_OS_USER','splunk'),('SPLUNK_BINDIP','127.0.0.1')]:
        text='\n'.join(line for line in text.splitlines() if not line.startswith(setting+'='))+'\n'+setting+'='+value+'\n'
    atomic_write(launch,text,0o644)
    wrapper=(DEPLOY/'systemd/splunk-launch-no-thp.py').read_text()
    wrapper=wrapper.replace("['/opt/splunk/bin/splunk', '_internal_launch_under_systemd']", "['/opt/splunk/bin/splunk', '_internal_launch_under_systemd', '--accept-license', '--answer-yes', '--no-prompt']")
    atomic_write(home/'etc/system/local/splunk-launch-no-thp.py',wrapper,0o755)
    shutil.copytree(DEPLOY/'server_health',home/'etc/apps/server_health',dirs_exist_ok=True)
    shutil.copytree(ROOT/'reports/splunk-stage/ai_sysadmin',home/'etc/apps/ai_sysadmin',dirs_exist_ok=True)
    credential=json.loads(Path('/home/bot/splunk/.secrets/splunk-admin.json').read_text())
    assert credential['username']=='admin' and '\n' not in credential['password']
    atomic_write(home/'etc/system/local/user-seed.conf','[user_info]\nUSERNAME = '+credential['username']+'\nPASSWORD = '+credential['password']+'\n',0o600)
    c.event('change','Restored saved local settings, startup wrapper, apps and existing private admin credential seed; no credential values logged')
    action('set_splunk_tree_ownership',['chown','-R','splunk:splunk',str(home)],True)
    gid=pwd.getpwnam('splunk').pw_gid
    os.chown(c.logs,-1,gid); os.chmod(c.logs,0o2750)
    for path in c.logs.glob('*.jsonl'):
        os.chown(path,-1,gid); os.chmod(path,0o640)
    c.event('change','Splunk group can read existing logs and inherit new log group ownership')
    config=Path('/etc/ai-sysadmin/config.toml')
    text=config.read_text().replace('# Deferred by operator; do not change the running Splunk installation.','# Enabled by operator for local Splunk integration.').replace('install_app = false','install_app = true')
    atomic_write(config,text,0o644)
    action('initialize_splunk_license',['runuser','-u','splunk','--','/opt/splunk/bin/splunk','version','--accept-license','--answer-yes','--no-prompt'],True)
    action('validate_splunk_configuration',['runuser','-u','splunk','--','/opt/splunk/bin/splunk','btool','check'])
    action('start_restored_splunk',['systemctl','start','Splunkd.service'],True)
    c.event('phase','Splunk restored and started; live integration verification pending',phase='verification',change_id='SPLUNK-20260913')
