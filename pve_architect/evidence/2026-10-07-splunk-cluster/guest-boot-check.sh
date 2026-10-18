export LC_ALL=C
python3 - <<'PY'
import socket,time,subprocess
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(2)
try:
 s.connect('/var/run/qemu-server/100.serial0');s.sendall(b'\n')
 chunks=[]
 while True:
  try:chunks.append(s.recv(16384))
  except socket.timeout:break
 print(b''.join(chunks).decode(errors='replace')[-7000:])
except Exception as e:print(type(e).__name__,str(e))
finally:s.close()
PY
systemctl show splunk-lab-create -p ActiveState -p SubState -p Result
qm list
qm guest cmd 100 network-get-interfaces || true
