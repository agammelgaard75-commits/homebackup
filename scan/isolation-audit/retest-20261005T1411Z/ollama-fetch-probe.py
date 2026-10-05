"""Bounded manifest-fetch checks. Callback always fails, never serves a model.
No valid manifests, blobs, credentials or generation requests are sent.
"""
import http.server,threading,urllib.request,urllib.error,json,time,pathlib,uuid
out=pathlib.Path(__file__).resolve().parent
marker='isolation-audit-'+uuid.uuid4().hex[:10]
events=[];rows=[];routes={}
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  events.append({'time':time.time(),'peer':self.client_address[0],'method':'GET','path':self.path,'user_agent':self.headers.get('User-Agent')})
  route=next((v for k,v in routes.items() if '/'+k+'/' in self.path),None)
  if route:
   self.send_response(302);self.send_header('Location',route);self.send_header('Content-Length','0');self.end_headers()
  else:
   body=marker.encode();self.send_response(418);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def log_message(self,*a):pass
server=http.server.ThreadingHTTPServer(('192.168.2.100',18089),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def pull(label,model):
 start=time.monotonic();row={'label':label,'model':model,'insecure':True,'stream':False}
 req=urllib.request.Request('http://192.168.3.189:11434/api/pull',data=json.dumps({'model':model,'insecure':True,'stream':False}).encode(),headers={'Content-Type':'application/json'})
 try:
  with opener.open(req,timeout=6) as r:row.update(status=r.status,body=r.read(8192).decode(errors='replace'))
 except urllib.error.HTTPError as e:row.update(status=e.code,body=e.read(8192).decode(errors='replace'))
 except Exception as e:row['error']=str(e)
 row['elapsed']=round(time.monotonic()-start,3);rows.append(row);print(json.dumps(row),flush=True)
 (out/'ollama-fetch-probe.json').write_text(json.dumps({'marker':marker,'events':events,'results':rows},indent=2)+'\n')
try:
 pull('controlled-callback','192.168.2.100:18089/audit/'+marker+':latest')
 if events:
  # Unique nonexistent manifest paths terminate before any model download.
  for host,port in [('192.168.1.1',80),('192.168.1.50',80),('192.168.1.201',80),('192.168.2.1',80),('192.168.3.1',80),('192.168.3.189',80),('127.0.0.1',11434),('192.168.1.50',8006)]:
   pull('direct-registry-probe',f'{host}:{port}/audit/{marker}:latest')
  # Redirect to nonexistent paths, preserving read-only semantics.
  for index,target in enumerate(['http://192.168.1.1/'+marker,'http://192.168.3.1/'+marker,'https://192.168.1.50:8006/'+marker]):
   name=marker+'-redirect-'+str(index);routes[name]=target
   pull('redirect-to-'+target,'192.168.2.100:18089/audit/'+name+':latest')
finally:
 server.shutdown();server.server_close();thread.join(timeout=2)
 (out/'ollama-fetch-probe.json').write_text(json.dumps({'marker':marker,'events':events,'results':rows,'listener_closed':True},indent=2)+'\n')
 with opener.open('http://192.168.3.189:11434/api/tags',timeout=5) as r:(out/'ollama-tags-after.json').write_bytes(r.read())
