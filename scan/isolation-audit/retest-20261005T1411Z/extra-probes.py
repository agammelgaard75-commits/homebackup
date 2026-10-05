import concurrent.futures,json,socket,struct,subprocess,time,pathlib,urllib.request,urllib.error
out=pathlib.Path(__file__).resolve().parent

def save(name,obj):
 (out/name).write_text(json.dumps(obj,indent=2)+'\n');print(name,json.dumps(obj)[:2500],flush=True)

def ollama():
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));rows=[]
 for path in ['/','/api/version','/api/tags','/api/ps','/v1/models']:
  row={'path':path}
  try:
   with opener.open('http://192.168.3.189:11434'+path,timeout=5) as r:row.update(status=r.status,headers=dict(r.headers),body=r.read(131072).decode())
  except Exception as e:row['error']=str(e)
  rows.append(row)
 for origin in ['https://example.com','http://localhost','http://192.168.2.100']:
  row={'method':'OPTIONS','origin':origin}
  req=urllib.request.Request('http://192.168.3.189:11434/api/tags',method='OPTIONS',headers={'Origin':origin,'Access-Control-Request-Method':'GET'})
  try:
   with opener.open(req,timeout=5) as r:row.update(status=r.status,headers=dict(r.headers))
  except urllib.error.HTTPError as e:row.update(status=e.code,headers=dict(e.headers))
  except Exception as e:row['error']=str(e)
  rows.append(row)
 save('ollama-api.json',rows)

def multicast():
 s=socket.socket(socket.AF_INET6,socket.SOCK_RAW,socket.IPPROTO_ICMPV6);s.setsockopt(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,b'ens18\0');s.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_MULTICAST_HOPS,1);s.settimeout(.2)
 ident=30511;replies=[]
 for seq in range(2):s.sendto(struct.pack('!BBHHH',128,0,0,ident,seq)+b'isolation-retest',('ff02::1',0,0,socket.if_nametoindex('ens18')))
 end=time.monotonic()+5
 while time.monotonic()<end:
  try:d,src=s.recvfrom(2048)
  except socket.timeout:continue
  if len(d)>=8 and d[0]==129 and struct.unpack('!H',d[4:6])[0]==ident and src[0] not in replies:replies.append(src[0])
 s.close();save('multicast-ens18.json',{'requests':2,'reply_addresses':replies,'other_addresses':[a for a in replies if a!='fe80::be24:11ff:feac:52ab']})

def container():
 pid=subprocess.check_output(['sudo','-n','docker','inspect','--format','{{.State.Pid}}','n8n'],text=True).strip()
 jobs=[('container-ipv4.txt',['nmap','--unprivileged','-n','-sT','-Pn','--reason','--max-retries','1','--max-rate','50','--host-timeout','60s','-p','22,53,80,443,445,2375,3000,4000,5678,8006,8080,8443,11434','192.168.1.1','192.168.1.50','192.168.2.1','192.168.3.1','192.168.3.189']),('container-ollama.txt',['curl','--noproxy','*','-sS','-D','-','--connect-timeout','4','--max-time','8','http://192.168.3.189:11434/api/version']),('container-internet.txt',['curl','--noproxy','*','-4','-sS','-I','--connect-timeout','4','--max-time','8','--resolve','example.com:443:'+socket.gethostbyname('example.com'),'https://example.com'])]
 for name,args in jobs:
  cmd=['sudo','-n','nsenter','-t',pid,'-n']+args
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=90);(out/name).write_text(repr(cmd)+'\n'+p.stdout+p.stderr+'\nexit='+str(p.returncode)+'\n');print(name,p.stdout[-2000:],flush=True)

def control():
 cmd=['curl','--noproxy','*','-4','-sS','-I','--connect-timeout','4','--max-time','8','https://example.com'];p=subprocess.run(cmd,capture_output=True,text=True,timeout=12);(out/'internet-ipv4.txt').write_text(p.stdout+p.stderr)

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 for f in [pool.submit(x) for x in [ollama,multicast,container,control]]:f.result()
