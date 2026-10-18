#!/usr/bin/env python3
import json,concurrent.futures,datetime
from splunk_lab_ops import *
def entries(node,path):
 return [{ 'name':e['name'], **{k:v for k,v in e['content'].items() if k!='eai:acl'}} for e in api(node,path).get('entry',[])]
def inspect(n):
 try:
  c=entries(n,'/services/server/info')[0]
  info={k:c.get(k) for k in ('serverName','version','licenseState','activeLicenseGroup','isTrial','server_roles','kvStoreStatus','health_info')}
  info['os']=ssh(n,". /etc/os-release; echo $PRETTY_NAME; systemctl is-enabled Splunkd; systemctl is-active Splunkd; free -m; df -h /; chronyc tracking | head -n 6").stdout
  info['trial']=[{k:c.get(k) for k in ('label','expiration_time','quota','status')} for c in entries(n,'/services/licenser/licenses') if c.get('type')=='download-trial']
  return n['name'],info
 except Exception as ex:return n['name'],{'error':redact(str(ex))}
result={'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
with concurrent.futures.ThreadPoolExecutor() as pool:result['nodes']=dict(pool.map(inspect,NODES))
for key,path in [('health','health'),('peers','peers'),('searchheads','searchheads')]:
 try:result[key]=entries(NODES[0],'/services/cluster/manager/'+path)
 except Exception as ex:result[key]={'error':redact(str(ex))}
(EVIDENCE/'validation.json').write_text(redact(json.dumps(result,indent=2)))
print(json.dumps(result,indent=2))
