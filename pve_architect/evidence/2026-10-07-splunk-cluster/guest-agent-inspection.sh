export LC_ALL=C
qm help guest exec
python3 - <<'PY'
import subprocess,json,pathlib
w=pathlib.Path('/root/splunk-lab');nodes=json.loads((w/'inventory.json').read_text())
for n in nodes:
 data=json.loads(subprocess.check_output(['qm','guest','cmd',str(n['vmid']),'network-get-interfaces'],text=True))
 n['ip']=next(a['ip-address'] for iface in data if iface.get('hardware-address','').lower()==f'bc:24:11:52:02:{n["vmid"]-99:02x}' for a in iface.get('ip-addresses',[]) if a['ip-address-type']=='ipv4')
 n['mac']=f'BC:24:11:52:02:{n["vmid"]-99:02X}'
 print(n['vmid'],n['name'],n['ip'],n['mac'])
(w/'inventory.json').write_text(json.dumps(nodes,indent=2)+'\n')
PY
qm guest exec 100 -- /bin/bash -lc 'cloud-init status; cat /etc/os-release | head -4; systemctl is-active ssh; ss -lnt | head; ip route; curl -I --max-time 10 https://download.splunk.com/ 2>&1 | head -6; free -h; df -h /'
