import json, os, shlex, subprocess
from pathlib import Path
BASE=Path(__file__).resolve().parent
ACCESS=json.load(open('/home/bot/pve_architect/.secrets/splunk-lab-access.json'))
def pve(cmd,timeout=120):
 r=subprocess.run(['sshpass','-e','ssh','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(BASE/'pve_known_hosts'),'-o','ConnectTimeout=10','root@10.10.1.10',cmd],env={**os.environ,'SSHPASS':os.environ['PVE_PASSWORD']},capture_output=True,text=True,timeout=timeout)
 if r.returncode: raise RuntimeError(r.stderr or r.stdout)
 return r.stdout

def guest(vmid,cmd):
 d=json.loads(pve(shlex.join(['qm','guest','exec',str(vmid),'--','bash','-lc',cmd])))
 if not d.get('exited') or d.get('exitcode'): raise RuntimeError(str(d))
 return d.get('out-data','')

def vm(ip,script,timeout=120):
 r=subprocess.run(['ssh','-i',ACCESS['ssh_key'],'-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(BASE/'known_hosts'),'-o','ConnectTimeout=10',ACCESS['ssh_user']+'@'+ip,'sudo -n bash -s'],input=script,text=True,capture_output=True,timeout=timeout)
 if r.returncode: raise RuntimeError(r.stderr or r.stdout)
 return r.stdout
if __name__=='__main__':
 import concurrent.futures
 mapping={100:'192.168.2.169',101:'192.168.2.171',102:'192.168.2.173',103:'192.168.2.175'}
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  results=list(pool.map(lambda i:(i,guest(i,'cat /etc/ssh/ssh_host_ed25519_key.pub')),mapping))
 (BASE/'known_hosts').write_text(''.join(mapping[i]+' '+key for i,key in results))
 for i,ip in mapping.items():
  print(i,ip,vm(ip,'hostname; /opt/splunk/bin/splunk version; /opt/splunk/bin/splunk btool outputs list --debug | grep -E "server =|defaultGroup ="; resolvectl status eth0 | head -15'))
