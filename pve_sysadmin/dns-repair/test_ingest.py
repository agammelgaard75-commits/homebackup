import json,urllib.request,time,uuid
from check_splunk import api,CTX
from ops import ACCESS
marker='dns-repair-'+str(uuid.uuid4())
for name,ip in [('splunk-idx1','192.168.2.171'),('splunk-idx2','192.168.2.173')]:
 event={'event':{'message':'Sandbox DNS repair validation','repair_id':marker,'target':name},'index':'lab','sourcetype':'_json','source':'sandbox-dns-validation','host':'dns-validation'}
 req=urllib.request.Request('https://'+ip+':8088/services/collector/event',data=json.dumps(event).encode(),headers={'Authorization':'Splunk '+ACCESS['hec_token'],'Content-Type':'application/json'})
 r=json.load(urllib.request.urlopen(req,context=CTX,timeout=10))
 assert r.get('code')==0,r
 print(name,'ingest accepted',flush=True)
query='search index=lab earliest=-15m "'+marker+'" | stats count dc(target) as targets values(target) as target'
for attempt in range(18):
 r=api('192.168.2.175','search/jobs',{'search':query,'exec_mode':'oneshot','output_mode':'json'})
 rows=r.get('results',[])
 if rows and rows[0].get('count')=='2' and rows[0].get('targets')=='2':
  print(json.dumps({'marker':marker,'search':rows,'result':'PASS'}));break
 time.sleep(5)
else:raise SystemExit('FAIL: both test events were not searchable within 90 seconds')
