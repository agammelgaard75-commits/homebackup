import json,os,subprocess,requests
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ACCESS=json.load(open('/home/bot/pve_architect/.secrets/splunk-lab-access.json'))
requests.packages.urllib3.disable_warnings()
HOSTS={'splunk-cm':'192.168.2.169','splunk-idx1':'192.168.2.171','splunk-idx2':'192.168.2.173','splunk-sh':'192.168.2.175','sandboxpve':'10.10.1.10'}
def ssh(host,cmd,data=None,check=True):
 if host=='sandboxpve':
  args=['sshpass','-e','ssh','-o','UserKnownHostsFile=/tmp/pve-sysadmin-known-hosts','root@10.10.1.10',cmd];env=dict(os.environ,SSHPASS='botbotbot')
 else:
  args=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-o',f'UserKnownHostsFile={ROOT}/known_hosts','-i',ACCESS['ssh_key'],'ubuntu@'+HOSTS[host],cmd];env=os.environ
 return subprocess.run(args,input=data,capture_output=True,check=check,env=env).stdout.decode()
def api(host,path,data=None,method=None):
 r=requests.request(method or ('POST' if data is not None else 'GET'),'https://'+HOSTS[host]+':8089'+path,params={'output_mode':'json','count':0},data=data,auth=(ACCESS['username'],ACCESS['password']),verify=False,timeout=90)
 if not r.ok:raise RuntimeError(f'{host} {path}: {r.status_code} {r.text[:800]}')
 return r.json()
def search(q,earliest='-1h'):
 r=requests.post('https://'+HOSTS['splunk-sh']+':8089/services/search/jobs/export',data={'search':q,'earliest_time':earliest,'latest_time':'now','output_mode':'json'},auth=(ACCESS['username'],ACCESS['password']),verify=False,timeout=120)
 r.raise_for_status();return [json.loads(l) for l in r.text.splitlines() if l]
