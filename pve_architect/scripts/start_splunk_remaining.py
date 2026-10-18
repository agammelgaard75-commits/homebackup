import time,concurrent.futures
from splunk_lab_ops import *
fix="from pathlib import Path\np=Path('/opt/splunk/etc/system/local/server.conf')\ns=p.read_text().replace('[license]\\nmanager_uri = https://splunk-cm:8089','[license]\\nmanager_uri = self\\nactive_group = Trial')\np.write_text(s)\n"
def start(n):
 deadline=time.time()+600
 while not (EVIDENCE/f'install-{n["vmid"]}.log').exists():
  if time.time()>deadline:raise RuntimeError('Installation timeout')
  time.sleep(5)
 assert 'Exit code: 0' in (EVIDENCE/f'install-{n["vmid"]}.log').read_text()
 ssh(n,'sudo python3 -',stdin=fix)
 r=ssh(n,'sudo systemctl start Splunkd && systemctl is-active Splunkd',timeout=180)
 print(n['name'],r.stdout,flush=True)
with concurrent.futures.ThreadPoolExecutor() as pool:list(pool.map(start,NODES[2:]))
