set -eu
cat > /root/splunk-lab/create-vms.sh <<'PROVISION'
set -euo pipefail
export LC_ALL=C
work_dir=/root/splunk-lab
test -f "$work_dir/download-complete"
if [ ! -f "$work_dir/id_ed25519" ]; then
 ssh-keygen -q -t ed25519 -N '' -C splunk-lab-provisioning -f "$work_dir/id_ed25519"
fi
install -d -m 755 /var/lib/vz/snippets
pvesm set local --content iso,vztmpl,backup,snippets
python3 - <<'PY'
from pathlib import Path
import json,subprocess
key=Path('/root/splunk-lab/id_ed25519.pub').read_text().strip()
nodes=[{'vmid':100,'name':'splunk-cm','role':'manager','cores':1,'memory':2048,'disk':16,'order':10},
 {'vmid':101,'name':'splunk-idx1','role':'indexer','cores':2,'memory':3072,'disk':24,'order':20},
 {'vmid':102,'name':'splunk-idx2','role':'indexer','cores':2,'memory':3072,'disk':24,'order':20},
 {'vmid':103,'name':'splunk-sh','role':'searchhead','cores':2,'memory':3072,'disk':20,'order':30}]
for n in nodes:
 assert not Path(f'/etc/pve/qemu-server/{n["vmid"]}.conf').exists(),n
Path('/root/splunk-lab/inventory.json').write_text(json.dumps(nodes,indent=2)+'\n')
for n in nodes:
 data={'hostname':n['name'],'manage_etc_hosts':True,'ssh_pwauth':False,'users':[{'name':'ubuntu','groups':['adm','sudo'],'shell':'/bin/bash','sudo':'ALL=(ALL) NOPASSWD:ALL','lock_passwd':True,'ssh_authorized_keys':[key]}],
 'package_update':True,'packages':['qemu-guest-agent','curl','ca-certificates','chrony','libatomic1','libnuma1'],
 'swap':{'filename':'/swapfile','size':1073741824},
 'write_files':[{'path':'/etc/sysctl.d/60-splunk-lab.conf','content':'vm.swappiness=10\n'},
 {'path':'/etc/chrony/sources.d/lab-ntp.sources','content':'server 162.159.200.1 iburst\nserver 162.159.200.123 iburst\n'}],
 'runcmd':[['systemctl','enable','--now','qemu-guest-agent'],['systemctl','restart','chrony'],['sysctl','--system']]}
 filename=f'splunk-{n["vmid"]}-user.yaml'
 Path('/var/lib/vz/snippets/'+filename).write_text('#cloud-config\n'+json.dumps(data,indent=2)+'\n')
 cmd=['qm','create',str(n['vmid']),'--name',n['name'],'--ostype','l26','--machine','q35','--cpu','host','--cores',str(n['cores']),'--memory',str(n['memory']),'--balloon','0','--scsihw','virtio-scsi-single','--net0',f'virtio=BC:24:11:52:02:{n["vmid"]-100+1:02X},bridge=vmbr0,tag=2','--agent','enabled=1,fstrim_cloned_disks=1','--serial0','socket','--vga','serial0','--onboot','1','--startup',f'order={n["order"]},up=30','--tags','splunk;ubuntu26;lab', '--description',f'Minimal Splunk lab: {n["role"]}; Ubuntu 26.04; VLAN 2.']
 subprocess.run(cmd,check=True)
 subprocess.run(['qm','set',str(n['vmid']),'--scsi0','local-lvm:0,import-from=/var/lib/vz/template/iso/splunk-lab/ubuntu-26.04-server-cloudimg-amd64.img,discard=on,iothread=1','--ide2','local-lvm:cloudinit','--boot','order=scsi0','--ipconfig0','ip=dhcp','--nameserver','1.1.1.1 8.8.8.8','--cicustom','user=local:snippets/'+filename],check=True)
 subprocess.run(['qm','resize',str(n['vmid']),'scsi0',str(n['disk'])+'G'],check=True)
 subprocess.run(['qm','start',str(n['vmid'])],check=True)
 print('CREATED',n,flush=True)
PY

PROVISION
systemd-run --unit=splunk-lab-create --property=Type=exec --property=StandardOutput=append:/root/splunk-lab/create-vms.log --property=StandardError=append:/root/splunk-lab/create-vms.log /bin/bash /root/splunk-lab/create-vms.sh
