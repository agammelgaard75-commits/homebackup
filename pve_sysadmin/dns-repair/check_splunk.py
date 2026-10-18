import base64,json,ssl,urllib.request,urllib.parse,concurrent.futures
from ops import ACCESS
CTX=ssl._create_unverified_context() # Existing lab endpoints use self-signed certificates.
AUTH='Basic '+base64.b64encode((ACCESS['username']+':'+ACCESS['password']).encode()).decode()
def api(ip,path,data=None):
 url='https://'+ip+':8089/services/'+path
 url+=('&' if '?' in url else '?')+'output_mode=json'
 body=urllib.parse.urlencode(data).encode() if data is not None else None
 return json.load(urllib.request.urlopen(urllib.request.Request(url,data=body,headers={'Authorization':AUTH}),context=CTX,timeout=20))
def check(v):
 ip,path=v
 try:
  j=api(ip,path)
  safe=['status','label','peerName','serverName','replication_factor_met','search_factor_met','all_data_searchable','maintenance_mode','indexing_ready','service_ready','is_searchable','peer_count','searchable','disabled','index','indexes','useSSL','replication_count','searchable_count','fixup_count','active_bundle_id']
  return {'ip':ip,'path':path,'entries':[{'name':e['name'],**{k:v for k,v in e['content'].items() if k in safe}} for e in j.get('entry',[])]}
 except Exception as e:return {'ip':ip,'path':path,'error':str(e)}
if __name__=='__main__':
 jobs=[('192.168.2.169','cluster/manager/health'),('192.168.2.169','cluster/manager/peers'),('192.168.2.175','search/distributed/peers'),('192.168.2.175','data/inputs/http')]
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as e:
  for r in e.map(check,jobs):print(json.dumps(r))
