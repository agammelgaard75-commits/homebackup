#!/usr/bin/env python3
import time,json,datetime
from splunk_lab_ops import *
marker=json.loads((EVIDENCE/'functional-test.json').read_text())['marker']
result={'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'stopped_node':NODES[2]['name'],'marker':marker}
try:
 print('Stopping second indexer for search failover test',flush=True)
 r=ssh(NODES[2],'sudo systemctl stop Splunkd && systemctl is-active Splunkd',timeout=420,check=False)
 result['stop_result']=r.stdout;assert r.stdout.strip()=='inactive',r.stdout
 for attempt in range(18):
  peers=api(NODES[0],'/services/cluster/manager/peers')['entry']
  states={e['content']['label']:e['content']['status'] for e in peers}
  if states.get('splunk-idx2')!='Up':break
  time.sleep(5)
 result['peer_states']=states
 r=requests.post('https://'+NODES[3]['ip']+':8089/services/search/jobs',auth=(ACCESS['username'],ACCESS['password']),verify=False,data={'search':'search index=lab "'+marker+'" | stats count values(origin) as origins values(splunk_server) as serving_peer','exec_mode':'oneshot','output_mode':'json','earliest_time':'-1h'},timeout=120)
 r.raise_for_status();result['search']=r.json()
 assert result['search']['results'][0]['count']=='2',result['search']
 assert result['search']['results'][0]['serving_peer'] in ('splunk-idx1',['splunk-idx1']),result['search']
 result['passed']=True
 print('Both test events searchable with second indexer offline',flush=True)
finally:
 print('Starting second indexer',flush=True)
 result['restart']=ssh(NODES[2],'sudo systemctl start Splunkd && systemctl is-active Splunkd',timeout=180,check=False).stdout
 (EVIDENCE/'failover-test.json').write_text(redact(json.dumps(result,indent=2)))
 print(json.dumps(result,indent=2),flush=True)
