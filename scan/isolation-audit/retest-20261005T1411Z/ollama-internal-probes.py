import concurrent.futures,json,time,pathlib,urllib.request,urllib.error
out=pathlib.Path(__file__).resolve().parent
marker='isolation-audit-20261005-1411';rows=[]
targets=[('192.168.1.1',22,True),('192.168.1.1',443,False),('192.168.2.1',443,False),('192.168.3.1',443,False),('192.168.1.43',22,True),('192.168.1.43',80,True),('192.168.1.43',443,False),('192.168.1.43',8080,True),('192.168.1.43',8443,False),('192.168.1.201',22,True),('192.168.1.201',443,False),('192.168.1.201',8006,False),('192.168.1.50',443,False),('192.168.3.189',445,True),('127.0.0.1',22,True),('127.0.0.1',8080,True),('127.0.0.1',3000,True)]
def probe(t):
 host,port,insecure=t;row={'host':host,'port':port,'insecure':insecure};start=time.monotonic()
 model=f'{host}:{port}/audit/{marker}:latest'
 req=urllib.request.Request('http://192.168.3.189:11434/api/pull',data=json.dumps({'model':model,'insecure':insecure,'stream':False}).encode(),headers={'Content-Type':'application/json'})
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 try:
  with opener.open(req,timeout=5) as r:row.update(status=r.status,body=r.read(8192).decode(errors='replace'))
 except urllib.error.HTTPError as e:row.update(status=e.code,body=e.read(8192).decode(errors='replace'))
 except Exception as e:row['error']=str(e)
 row['elapsed']=round(time.monotonic()-start,3);return row
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 for row in pool.map(probe,targets):
  rows.append(row);print(json.dumps(row),flush=True);(out/'ollama-internal-probes.json').write_text(json.dumps(rows,indent=2)+'\n')
