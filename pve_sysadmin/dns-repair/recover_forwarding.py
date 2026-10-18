import time,json
from ops import vm
from check_splunk import api
for name,ip in [('splunk-sh','192.168.2.175'),('splunk-cm','192.168.2.169')]:
 current=api(ip,'data/outputs/tcp/server').get('entry',[])
 if any(e['content'].get('status') in ('connected','connect_done') for e in current):
  print(name,'forwarding already connected; no restart',flush=True);continue
 print(name,'restarting Splunk service',flush=True)
 print(vm(ip,'systemctl restart Splunkd; systemctl is-active Splunkd',timeout=180),flush=True)
 for attempt in range(24):
  try:
   j=api(ip,'data/outputs/tcp/server')
   rows=[{'server':e['name'],'status':e['content'].get('status')} for e in j.get('entry',[])]
   if any(r['status'] in ('connected','connect_done') for r in rows):
    print(name,json.dumps(rows),flush=True);break
  except Exception:pass
  time.sleep(5)
 else:raise SystemExit(name+' forwarding did not recover; stopping before other restarts')
