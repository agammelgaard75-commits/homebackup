#!/usr/bin/python3
"""Sandbox sysadmin collection: journal + health -> durable SQLite -> pinned TLS HEC.
At-least-once delivery; event_id permits deduplication after ambiguous acknowledgments.
"""
import fcntl, hashlib, http.client, json, os, pathlib, re, socket, sqlite3, ssl, subprocess, time, uuid
BASE=pathlib.Path('/var/lib/sysadmin-splunk')
CFG=json.load(open('/etc/sysadmin-splunk/config.json'))
HOST=socket.gethostname().split('.')[0]
INDEX='sysadmin_pve' if CFG['role']=='pve' else 'sysadmin_vm'
BASE.mkdir(mode=0o700,exist_ok=True)
lock=open(BASE/'lock','w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
db=sqlite3.connect(BASE/'queue.sqlite')
db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL')
db.execute('CREATE TABLE IF NOT EXISTS queue(id INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
db.execute('CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
def get(key,default=None):
 row=db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()
 return json.loads(row[0]) if row else default
def put(key,value):db.execute('INSERT OR REPLACE INTO state VALUES (?,?)',(key,json.dumps(value)))
def run(args):return subprocess.check_output(args,text=True,timeout=25,stderr=subprocess.PIPE)
def event(kind,fields,stamp=None,event_id=None):
 data={'kind':kind,'role':CFG['role'],'event_id':event_id or str(uuid.uuid4()),**fields}
 payload={'time':stamp or time.time(),'host':HOST,'index':INDEX,'source':'sysadmin:'+kind,'sourcetype':'sysadmin:json','event':data}
 db.execute('INSERT INTO queue(payload) VALUES (?)',(json.dumps(payload,separators=(',',':')),))
def issue(component,error):
 event('collector_error',{'component':component,'message':str(error)[:1000],'severity':'error','priority':3})
 print(component+': '+str(error)[:250],flush=True)
def journal():
 cursor=get('journal_cursor');args=['journalctl','--no-pager','-o','json','--all']
 if cursor:
  check=subprocess.run(['journalctl','--cursor',cursor,'-n','1','--no-pager'],capture_output=True,timeout=10)
  if check.returncode:
   issue('journal','Saved cursor unavailable; resuming from last event time (possible duplicates after journal rotation)')
   args+=['--since','@'+str(get('journal_time',time.time()-3600))]
  else:args+=['--after-cursor',cursor]
 else:args+=['--since','1 hour ago']
 p=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
 try:
  for i,line in enumerate(p.stdout):
   if i>=2500:break
   j=json.loads(line);cur=j.get('__CURSOR');stamp=int(j['__REALTIME_TIMESTAMP'])/1e6
   msg=j.get('MESSAGE','');msg=msg if isinstance(msg,str) else json.dumps(msg)
   pri=int(j.get('PRIORITY',6));ident=j.get('SYSLOG_IDENTIFIER',j.get('_COMM','unknown'))
   if ident!='sysadmin-splunk':
    event('journal',{'message':msg[:16000],'priority':pri,'severity':['emergency','alert','critical','error','warning','notice','info','debug'][min(pri,7)],'unit':j.get('_SYSTEMD_UNIT',j.get('UNIT','')),'process':ident,'pid':j.get('_PID',''),'uid':j.get('_UID',''),'facility':j.get('SYSLOG_FACILITY',''),'boot_id':j.get('_BOOT_ID','')},stamp,hashlib.sha256((HOST+str(cur)).encode()).hexdigest())
   put('journal_cursor',cur);put('journal_time',stamp)
 finally:
  p.terminate();p.wait(timeout=5)
def health():
 now=time.time();cpu=list(map(int,open('/proc/stat').readline().split()[1:9]));old=get('cpu');total=sum(cpu);idle=cpu[3]+cpu[4]
 cpu_pct=round(100*(1-(idle-old['idle'])/(total-old['total'])),2) if old and total>old['total'] else None
 put('cpu',{'total':total,'idle':idle})
 mem={k:int(v.split()[0])*1024 for k,v in (l.split(':',1) for l in open('/proc/meminfo'))}
 failed=run(['systemctl','list-units','--failed','--no-legend','--plain','--no-pager']).splitlines()
 fields={'cpu_pct':cpu_pct,'load1':os.getloadavg()[0],'cpus':os.cpu_count(),'memory_pct':round(100*(1-mem.get('MemAvailable',mem['MemFree'])/mem['MemTotal']),2),'memory_total':mem['MemTotal'],'swap_used':mem.get('SwapTotal',0)-mem.get('SwapFree',0),'uptime':float(open('/proc/uptime').read().split()[0]),'failed_services':len(failed),'failed_units':[l.split()[0] for l in failed],'queue_events':db.execute('SELECT count(*) FROM queue').fetchone()[0]}
 event('health',fields)
 for m in json.loads(run(['findmnt','--json','--list','-o','TARGET,SOURCE,FSTYPE']))['filesystems']:
  if m['fstype'] not in ('ext4','ext3','xfs','btrfs','zfs','vfat'):continue
  path=m['target']
  try:
   st=os.statvfs(path)
   if not st.f_blocks:continue
   used=st.f_blocks-st.f_bfree
   event('filesystem',{'mount':path,'device':m['source'],'fstype':m['fstype'],'disk_pct':round(100*used/(used+st.f_bavail),2),'disk_total':st.f_blocks*st.f_frsize,'disk_available':st.f_bavail*st.f_frsize,'inode_pct':round(100*(st.f_files-st.f_ffree)/st.f_files,2) if st.f_files else 0})
  except OSError:pass
 net={}
 for line in open('/proc/net/dev').readlines()[2:]:
  name,values=line.split(':');name=name.strip();v=list(map(int,values.split()))
  if name=='lo':continue
  net[name]=[v[0],v[8]];prev=get('net',{});before=prev.get('interfaces',{}).get(name)
  event('network',{'interface':name,'rx_bytes':v[0],'tx_bytes':v[8],'rx_errors':v[2],'tx_errors':v[10],'rx_dropped':v[3],'tx_dropped':v[11],'rx_kbps':round(max(0,v[0]-before[0])*8/(now-prev['time'])/1000,2) if before else None,'tx_kbps':round(max(0,v[8]-before[1])*8/(now-prev['time'])/1000,2) if before else None})
 put('net',{'time':now,'interfaces':net})
def pve():
 def api(path,extra=[]):return json.loads(run(['pvesh','get',path,'--output-format','json']+extra))
 node=HOST
 for vm in api('/cluster/resources',['--type','vm']):
  if vm.get('template'):continue
  vm.update({'cpu_pct':round(100*vm.get('cpu',0),2),'memory_pct':round(100*vm.get('mem',0)/vm['maxmem'],2) if vm.get('maxmem') else 0})
  event('guest',vm)
 for s in api('/nodes/'+node+'/storage'):
  s['disk_pct']=round(s.get('used_fraction',0)*100,2);event('storage',s)
 for s in api('/cluster/status'):event('cluster',s)
 seen=get('tasks',[]);current=[]
 for task in api('/nodes/'+node+'/tasks',['--limit','100']):
  if 'endtime' not in task:continue
  key=task['upid']+':'+str(task['endtime']);current.append(key)
  if key not in seen:event('pve_task',task,task['endtime'],hashlib.sha256(key.encode()).hexdigest())
 put('tasks',current)
def access_log():
 path=pathlib.Path('/var/log/pveproxy/access.log')
 if not path.exists():return
 st=path.stat();previous=get('access',{});offset=previous.get('offset',0) if previous.get('inode')==st.st_ino else 0
 if offset>st.st_size:offset=0
 with path.open('rb') as f:
  f.seek(offset)
  for _ in range(1000):
   start=f.tell();line=f.readline()
   if not line:break
   if not line.endswith(b'\n'):f.seek(start);break
   msg=line.decode(errors='replace').rstrip()
   fields={'message':msg};match=re.search(r'"(?:GET|POST|PUT|DELETE|HEAD|OPTIONS) [^"]*" (\d{3})',msg)
   if match:fields['http_status']=int(match[1])
   event('pve_access',fields,event_id=hashlib.sha256(f'{HOST}:{st.st_ino}:{start}:{msg}'.encode()).hexdigest())
  put('access',{'inode':st.st_ino,'offset':f.tell()})
def post(endpoint,path,body,channel):
 # Authenticate the server by its SHA-256 certificate pin, obtained over verified SSH.
 ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);ctx.check_hostname=False;ctx.verify_mode=ssl.CERT_NONE;ctx.minimum_version=ssl.TLSVersion.TLSv1_2
 conn=http.client.HTTPSConnection(endpoint['host'],8088,context=ctx,timeout=8)
 try:
  conn.connect()
  if hashlib.sha256(conn.sock.getpeercert(binary_form=True)).hexdigest()!=endpoint['sha256']:raise RuntimeError('HEC certificate pin mismatch')
  conn.request('POST','/services/collector/'+path,body=body,headers={'Authorization':'Splunk '+CFG['token'],'X-Splunk-Request-Channel':channel,'Content-Type':'application/json'})
  response=conn.getresponse();data=json.loads(response.read())
  if response.status!=200 or data.get('code',0)!=0:raise RuntimeError(f'HEC status {response.status}: {data}')
  return data
 finally:conn.close()
def flush():
 channel=get('channel') or str(uuid.uuid4());put('channel',channel);db.commit()
 deadline=time.monotonic()+45
 endpoints=CFG['endpoints'];start=int(hashlib.sha256(HOST.encode()).hexdigest(),16)%len(endpoints);endpoints=endpoints[start:]+endpoints[:start]
 while time.monotonic()<deadline:
  rows=db.execute('SELECT id,payload FROM queue ORDER BY id LIMIT 200').fetchall()
  if not rows:return
  body='\n'.join(r[1] for r in rows).encode()
  delivered=False
  for ep in endpoints:
   try:
    ack=post(ep,'event',body,channel)['ackId']
    for _ in range(12):
     if post(ep,'ack',json.dumps({'acks':[ack]}).encode(),channel).get('acks',{}).get(str(ack)):
      with db:db.executemany('DELETE FROM queue WHERE id=?',[(r[0],) for r in rows])
      delivered=True;break
     time.sleep(1)
    if delivered:break
    raise RuntimeError('HEC acknowledgment timed out; batch retained')
   except Exception as e:print('Delivery '+ep['host']+': '+str(e)[:200],flush=True)
  if not delivered:raise RuntimeError('No HEC acknowledgment; queue retained for retry')
# Backpressure: retain the journal cursor and queue when the 64 MiB payload cap is reached.
size=db.execute('SELECT coalesce(sum(length(payload)),0) FROM queue').fetchone()[0]
if size<64*1024*1024:
 for name,fn in [('journal',journal),('health',health)]+([('pve',pve),('access',access_log)] if CFG['role']=='pve' else []):
  try:
   with db:fn()
  except Exception as e:
   with db:issue(name,e)
else:print('Queue payload cap reached; collection paused until delivery succeeds',flush=True)
flush()
print('Collection complete; pending='+str(db.execute('SELECT count(*) FROM queue').fetchone()[0]),flush=True)
