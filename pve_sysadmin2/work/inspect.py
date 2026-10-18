import requests,json,concurrent.futures
requests.packages.urllib3.disable_warnings()
a=json.load(open('/home/bot/pve_architect/.secrets/splunk-lab-access.json'))
def inspect(ip):
 s=requests.Session();s.auth=(a['username'],a['password']);s.verify=False
 out={}
 for path in ['server/info','data/indexes','data/inputs/http','cluster/manager/info','search/distributed/peers','licenser/pools']:
  r=s.get(f'https://{ip}:8089/services/{path}',params={'output_mode':'json','count':100},timeout=15)
  if r.status_code!=200:out[path]=r.status_code;continue
  out[path]=[{ 'name':e['name'],'content':{k:v for k,v in e['content'].items() if k in ['serverName','version','disabled','index','indexes','useACK','port','enableSSL','repFactor','maxTotalDataSizeMB','frozenTimePeriodInSecs','mode','status','master_uri','manager_uri','isReady','quota','used_bytes','stack_id']}} for e in r.json().get('entry',[])]
 return ip,out
with concurrent.futures.ThreadPoolExecutor() as ex:
 for ip,out in ex.map(inspect,['192.168.2.169','192.168.2.171','192.168.2.173','192.168.2.175']):print(ip,json.dumps(out))
