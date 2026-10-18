#!/usr/bin/env python3
import pathlib,json,subprocess,concurrent.futures
root=pathlib.Path(__file__).resolve().parents[1];e=root/'evidence/2026-10-07-splunk-cluster';private=root/'.secrets'
nodes=json.loads((e/'inventory.json').read_text());secrets=json.loads((private/'splunk-lab-access.json').read_text())
source=(e/'bootstrap.py').read_text()
def install(n):
 print('Installing',n['name'],n['ip'],flush=True)
 payload='CONFIG = '+repr({'node':n,'nodes':nodes,'secrets':secrets})+'\n'+source
 cmd=['ssh','-i',str(private/'splunk-lab-id_ed25519'),'-o','StrictHostKeyChecking=accept-new','-o','UserKnownHostsFile='+str(private/'splunk-lab-known_hosts'),'-o','ConnectTimeout=8','-o','ServerAliveInterval=15','ubuntu@'+n['ip'],'sudo python3 -']
 r=subprocess.run(cmd,input=payload,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=1000)
 output=r.stdout
 for k in ('password','cluster_secret','license_secret','hec_token'):output=output.replace(secrets[k],'[REDACTED]')
 (e/f'install-{n["vmid"]}.log').write_text(output+'\nExit code: '+str(r.returncode)+'\n')
 print('Finished',n['name'],'exit',r.returncode,'\n'+output[-1800:],flush=True)
 return r.returncode
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(install,nodes))
raise SystemExit(1 if any(results) else 0)
