
set -eu
export LC_ALL=C
python3 - <<'INNER'
import subprocess,json
ns='pve-tagged4-validation'
def run(*args):
 r=subprocess.run(args,check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 return r.stdout
run('ip','netns','add',ns)
try:
 run('ip','-n',ns,'link','add','enp1s0f0','type','dummy')
 run('ip','-n',ns,'link','add','vmbr0','type','bridge','vlan_filtering','1')
 run('ip','-n',ns,'link','set','enp1s0f0','master','vmbr0')
 run('ip','-n',ns,'link','set','enp1s0f0','up')
 run('ip','-n',ns,'link','set','vmbr0','up')
 run('bridge','-n',ns,'vlan','del','dev','enp1s0f0','vid','1')
 for vid in ('2','4'):run('bridge','-n',ns,'vlan','add','dev','enp1s0f0','vid',vid)
 run('bridge','-n',ns,'vlan','add','dev','vmbr0','vid','4','self')
 run('ip','-n',ns,'link','add','link','vmbr0','name','vmbr0.4','type','vlan','id','4')
 run('ip','-n',ns,'address','add','10.10.1.10/24','dev','vmbr0.4')
 run('ip','-n',ns,'link','set','vmbr0.4','up')
 parent=json.loads(run('ip','-n',ns,'-j','-4','address','show','dev','vmbr0'))
 print('IPv4-less parent bridge response:',json.dumps(parent))
 assert all(not interface.get('addr_info',[]) for interface in parent),parent
 address=json.loads(run('ip','-n',ns,'-j','-4','address','show','dev','vmbr0.4'))
 assert any(a.get('local')=='10.10.1.10' for a in address[0]['addr_info'])
 route=json.loads(run('ip','-n',ns,'-j','route','get','10.10.1.1'))
 assert route[0]['dev']=='vmbr0.4'
 ports=json.loads(run('bridge','-n',ns,'-j','vlan','show','dev','enp1s0f0'))
 print('Tagged-only uplink response:',json.dumps(ports))
 assert len(ports)==1
 vlans=ports[0]['vlans']
 assert {v['vlan'] for v in vlans}=={2,4},vlans
 assert not any('PVID' in v.get('flags',[]) or 'Egress Untagged' in v.get('flags',[]) for v in vlans)
 print('PASS: management VLAN, route, IPv4-less parent and tagged-only uplink validation using real iproute2 output in an isolated namespace.')
finally:
 run('ip','netns','delete',ns)
 print('Temporary network namespace removed; live networking untouched.')
INNER
