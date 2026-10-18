#!/usr/bin/env python3
import argparse,os,pathlib,re,subprocess,sys
root=pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--script');p.add_argument('--command');p.add_argument('--log');p.add_argument('--timeout',type=int,default=600);p.add_argument('--quiet',action='store_true');a=p.parse_args()
env=os.environ.copy();env['SSHPASS']=re.search(r'^Password\s+(\S+)',(root/'AGENTS.md').read_text(),re.M).group(1)
cmd=['sshpass','-e','ssh','-o','StrictHostKeyChecking=no','-o','UserKnownHostsFile=/dev/null','-o','ConnectTimeout=8','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','root@10.10.1.10', 'bash -s' if a.script else a.command]
r=subprocess.run(cmd,input=pathlib.Path(a.script).read_text() if a.script else None,text=True,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=a.timeout)
if a.log:pathlib.Path(a.log).write_text(r.stdout+'\nRemote exit code: '+str(r.returncode)+'\n')
if not a.quiet:print(r.stdout)
print('Remote exit code:',r.returncode)
sys.exit(r.returncode)
