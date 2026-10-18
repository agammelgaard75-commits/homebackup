set -eu
python3 - <<'PY'
import subprocess,json,pathlib
w=pathlib.Path('/root/splunk-lab');nodes=json.loads((w/'inventory.json').read_text())
for n in nodes:
 data=json.loads(subprocess.check_output(['qm','guest','cmd',str(n['vmid']),'network-get-interfaces'],text=True))
 n['ip']=next(a['ip-address'] for iface in data if iface['hardware-address'].lower()==f'bc:24:11:52:02:{n["vmid"]-99:02x}' for a in iface.get('ip-addresses',[]) if a['ip-address-type']=='ipv4')
 n['mac']=f'BC:24:11:52:02:{n["vmid"]-99:02X}'
 print(n['vmid'],n['name'],n['ip'],n['mac'])
 cmd=['ssh','-i',str(w/'id_ed25519'),'-o','StrictHostKeyChecking=accept-new','-o','UserKnownHostsFile='+str(w/'known_hosts'),'-o','ConnectTimeout=5','ubuntu@'+n['ip'],'cloud-init status; cat /etc/os-release | head -4; free -h; df -h /; ip route; timedatectl show -p NTPSynchronized']
 r=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=15);print(r.stdout);r.check_returncode()
(w/'inventory.json').write_text(json.dumps(nodes,indent=2)+'\n')
PY
