#!/usr/bin/env python3
import time,uuid,json,datetime
from splunk_lab_ops import *
marker='pve-lab-'+uuid.uuid4().hex
result={'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'marker':marker,'ingestion':[]}
for n in NODES[1:3]:
 r=requests.post('https://'+n['ip']+':8088/services/collector/event',headers={'Authorization':'Splunk '+ACCESS['hec_token']},json={'index':'lab','host':n['name'],'event':{'marker':marker,'origin':n['name'],'message':'PVE Splunk cluster acceptance test'}},verify=False,timeout=30)
 r.raise_for_status();body=r.json();assert body['code']==0,body
 result['ingestion'].append({'node':n['name'],'result':body})
def search():
 r=requests.post('https://'+NODES[3]['ip']+':8089/services/search/jobs',auth=(ACCESS['username'],ACCESS['password']),verify=False,data={'search':'search index=lab "'+marker+'" | stats count values(origin) as origins','exec_mode':'oneshot','output_mode':'json','earliest_time':'-1h'},timeout=120)
 r.raise_for_status();return r.json()
for attempt in range(12):
 data=search()
 if data.get('results') and data['results'][0].get('count')=='2':break
 time.sleep(5)
result['search']=data
(EVIDENCE/'functional-test.json').write_text(redact(json.dumps(result,indent=2)))
print(json.dumps(result,indent=2))
assert data['results'][0]['count']=='2'
for n in NODES[1:3]:
 api(n,'/services/data/indexes/lab/roll-hot-buckets',method='POST')
print('Test data ingested on both peers, found on search head; requested hot bucket roll.')
