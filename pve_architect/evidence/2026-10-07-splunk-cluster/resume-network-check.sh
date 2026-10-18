export LC_ALL=C
python3 - <<'PY'
import socket,time,re,subprocess,concurrent.futures

def console():
 s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(1)
 try:
  s.connect('/var/run/qemu-server/100.serial0');s.sendall(b'\n');end=time.monotonic()+5;chunks=[]
  while time.monotonic()<end:
   try:chunks.append(s.recv(16384))
   except socket.timeout:pass
  out=b''.join(chunks).decode(errors='replace');out=re.sub(r'\x1b\[[0-9;]*[A-Za-z]','',out)
  return 'SERIAL:\n'+out[-2000:]
 finally:s.close()
def capture():
 r=subprocess.run(['timeout','-s','INT','10','tcpdump','-nn','-e','-i','tap100i0','-c','10','arp or (udp port 67 or udp port 68)'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 return 'TAP NETWORK:\n'+r.stdout
with concurrent.futures.ThreadPoolExecutor() as pool:
 for r in pool.map(lambda f:f(),[console,capture]):print(r)
PY
