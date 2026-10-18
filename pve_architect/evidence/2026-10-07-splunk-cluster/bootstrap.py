# Executed as root inside a new Ubuntu VM with CONFIG supplied via SSH stdin.
from pathlib import Path
import subprocess,hashlib,os,json

def run(args):
 print('Running:',args[0], ' '.join(args[1:3]),flush=True)
 subprocess.run(args,check=True)
def write(path,text,mode=0o600):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);p.chmod(mode)

n=CONFIG['node'];nodes=CONFIG['nodes'];secret=CONFIG['secrets']
assert Path('/etc/os-release').read_text().find('VERSION_ID="26.04"')>=0
package=Path('/var/tmp/splunk-10.6.0.5.deb')
expected='4cde78040b0fee84aeb06a25debe8e46e5d5fe7d3e5bf0e75562592a46b91b9bef8688f4253f73643474b773a60f9ad49f98f721b8dd6ed1936c1b0cdc1a586c'
if not Path('/opt/splunk/bin/splunk').exists():
 run(['curl','-fsSL','--retry','2','--connect-timeout','15','--max-time','600','-o',str(package),'https://download.splunk.com/products/splunk/releases/10.6.0.5/linux/splunk-10.6.0.5-86587d4e3b27-linux-amd64.deb'])
 h=hashlib.sha512()
 with package.open('rb') as f:
  for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
 assert h.hexdigest()==expected,'Splunk package checksum mismatch'
 print('Splunk package SHA512 verified',flush=True)
 run(['dpkg','-i',str(package)])
 package.unlink()
if subprocess.run(['id','splunk'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
 run(['useradd','--system','--home','/opt/splunk','--shell','/usr/sbin/nologin','splunk'])

hosts=Path('/etc/hosts').read_text().split('# SPLUNK LAB NODES')[0].rstrip()+'\n# SPLUNK LAB NODES\n'+'\n'.join(x['ip']+' '+x['name'] for x in nodes)+'\n'
write('/etc/hosts',hosts,0o644)
server=f'''[general]
serverName = {n['name']}
pass4SymmKey = {secret['license_secret']}

[diskUsage]
minFreeSpace = 2048

[clustering]
mode = {n['role'] if n['role'] != 'indexer' else 'peer'}
pass4SymmKey = {secret['cluster_secret']}
'''
if n['role']=='manager':
 server+='replication_factor = 2\nsearch_factor = 2\ncluster_label = pve-splunk-lab\n'
 server+='\n[license]\nmanager_uri = self\nactive_group = Trial\n'
else:
 server+='manager_uri = https://splunk-cm:8089\n'
 server+='\n[license]\nmanager_uri = self\nactive_group = Trial\n'
if n['role']=='indexer':server+='\n[replication_port://9887]\n'
if n['role']!='searchhead':server+='\n[kvstore]\ndisabled = true\n'
write('/opt/splunk/etc/system/local/server.conf',server)
write('/opt/splunk/etc/system/local/user-seed.conf','[user_info]\nUSERNAME = admin\nPASSWORD = '+secret['password']+'\n')
web='[settings]\nstartwebserver = '+('0' if n['role']=='indexer' else '1')+'\nhttpport = 8000\nenableSplunkWebSSL = true\n'
write('/opt/splunk/etc/system/local/web.conf',web)
write('/opt/splunk/etc/system/local/limits.conf','[search]\nbase_max_searches = 1\nmax_searches_per_cpu = 1\n')
if n['role']=='indexer':
 inputs=f'''[default]
host = {n['name']}

[splunktcp://9997]
disabled = 0

[http]
disabled = 0
port = 8088
enableSSL = 1

[http://lab]
disabled = 0
token = {secret['hec_token']}
index = lab
indexes = lab
sourcetype = splunk_lab
'''
 write('/opt/splunk/etc/system/local/inputs.conf',inputs)
if n['role']=='manager':
 indexes='''[main]
repFactor = auto
maxTotalDataSizeMB = 1024
frozenTimePeriodInSecs = 604800

[lab]
homePath = $SPLUNK_DB/lab/db
coldPath = $SPLUNK_DB/lab/colddb
thawedPath = $SPLUNK_DB/lab/thaweddb
repFactor = auto
maxTotalDataSizeMB = 512
maxDataSize = 10
maxHotBuckets = 2
frozenTimePeriodInSecs = 604800
'''
 write('/opt/splunk/etc/manager-apps/lab_indexes/local/indexes.conf',indexes)
 write('/opt/splunk/etc/manager-apps/lab_indexes/default/app.conf','[install]\nstate = enabled\n[package]\nid = lab_indexes\n[ui]\nis_visible = 0\n')
else:
 pass
# Avoid indexing local data on management and search roles; forward to both peers.
if n['role'] in ('manager','searchhead'):
 outputs='''[tcpout]
defaultGroup = lab_indexers
indexAndForward = false

[tcpout:lab_indexers]
server = splunk-idx1:9997,splunk-idx2:9997
autoLBFrequency = 15
useACK = true
'''
 write('/opt/splunk/etc/system/local/outputs.conf',outputs)
write('/etc/security/limits.d/90-splunk.conf','splunk soft nofile 65536\nsplunk hard nofile 65536\nsplunk soft nproc 16384\nsplunk hard nproc 16384\n',0o644)
write('/etc/systemd/system/splunk-thp.service','''[Unit]
Description=Disable transparent huge pages for Splunk
Before=Splunkd.service
[Service]
Type=oneshot
ExecStart=/bin/sh -c 'echo never > /sys/kernel/mm/transparent_hugepage/enabled; echo never > /sys/kernel/mm/transparent_hugepage/defrag'
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
''',0o644)
run(['chown','-R','splunk:splunk','/opt/splunk'])
run(['/opt/splunk/bin/splunk','enable','boot-start','-systemd-managed','1','-user','splunk','-group','splunk','--accept-license','--answer-yes','--no-prompt'])
write('/etc/systemd/system/Splunkd.service.d/lab.conf','[Service]\nLimitNOFILE=65536\nLimitNPROC=16384\n',0o644)
run(['systemctl','daemon-reload'])
run(['systemctl','enable','--now','splunk-thp.service'])
print('READY_FOR_START',n['name'],flush=True)
