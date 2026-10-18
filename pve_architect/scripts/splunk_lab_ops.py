import pathlib,json,subprocess,requests,urllib3
ROOT=pathlib.Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'evidence/2026-10-07-splunk-cluster'
NODES=json.loads((EVIDENCE/'inventory.json').read_text())
ACCESS=json.loads((ROOT/'.secrets/splunk-lab-access.json').read_text())
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
def redact(text):
 for key in ('password','cluster_secret','license_secret','hec_token'):
  text=text.replace(ACCESS[key],'[REDACTED]')
 return text
def ssh(node,command,stdin=None,timeout=60,check=True):
 cmd=['ssh','-i',str(ROOT/'.secrets/splunk-lab-id_ed25519'),'-o','StrictHostKeyChecking=accept-new','-o','UserKnownHostsFile='+str(ROOT/'.secrets/splunk-lab-known_hosts'),'-o','ConnectTimeout=8','-o','ServerAliveInterval=15','ubuntu@'+node['ip'],command]
 r=subprocess.run(cmd,input=stdin,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
 if check and r.returncode:raise RuntimeError(node['name']+': '+redact(r.stdout))
 return r
def api(node,path,method='GET',data=None,params=None,timeout=30):
 query={'output_mode':'json'};query.update(params or {})
 r=requests.request(method,'https://'+node['ip']+':8089'+path,auth=(ACCESS['username'],ACCESS['password']),verify=False,params=query,data=data,timeout=timeout)
 if not r.ok:raise RuntimeError(node['name']+' '+path+' HTTP '+str(r.status_code)+' '+redact(r.text[:1800]))
 return r.json()
