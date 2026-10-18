from admin import *
import io,tarfile,uuid,hashlib,ssl,shlex
# Dedicated HEC token restricted to the two sysadmin indexes; never print it.
entries=api('splunk-idx1','/services/data/inputs/http')['entry']
entry=next((e for e in entries if e['name']=='http://sysadmin'),None)
token=entry['content']['token'] if entry else str(uuid.uuid4())
for h in ['splunk-idx1','splunk-idx2']:
 exists=any(e['name']=='http://sysadmin' for e in api(h,'/services/data/inputs/http')['entry'])
 data={'token':token,'index':'sysadmin_vm','indexes':'sysadmin_pve,sysadmin_vm','sourcetype':'sysadmin:json','disabled':'0','useACK':'1'}
 if not exists:data['name']='sysadmin'
 api(h,'/servicesNS/nobody/splunk_httpinput/data/inputs/http'+('/sysadmin' if exists else ''),data)
 print(h,'HEC configured')
endpoints=[]
for h in ['splunk-idx1','splunk-idx2']:
 pem=ssh(h,'sudo openssl x509 -in /opt/splunk/etc/auth/server.pem -outform PEM')
 endpoints.append({'host':HOSTS[h],'sha256':hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()})
def package(role):
 files={'usr/local/lib/sysadmin-splunk/collector.py':Path('deployment/collector.py').read_bytes(),'etc/systemd/system/sysadmin-splunk.service':Path('deployment/sysadmin-splunk.service').read_bytes(),'etc/systemd/system/sysadmin-splunk.timer':Path('deployment/sysadmin-splunk.timer').read_bytes(),'etc/sysadmin-splunk/config.json':json.dumps({'role':role,'token':token,'endpoints':endpoints}).encode()}
 buf=io.BytesIO()
 with tarfile.open(fileobj=buf,mode='w') as tar:
  for name,data in files.items():
   t=tarfile.TarInfo(name);t.size=len(data);t.mode=0o600 if name.endswith('config.json') else 0o644;tar.addfile(t,io.BytesIO(data))
 return buf.getvalue()
for h in ['splunk-cm','splunk-idx1','splunk-idx2','splunk-sh','sandboxpve','dns01']:
 role='pve' if h=='sandboxpve' else ('container' if h=='dns01' else 'vm')
 if h=='dns01':
  ssh('sandboxpve','install -m 600 /dev/null /tmp/sysadmin-ct.tar && cat > /tmp/sysadmin-ct.tar',package(role))
  print(h,ssh('sandboxpve','pct push 104 /tmp/sysadmin-ct.tar /tmp/sysadmin-ct.tar && pct exec 104 -- tar -xf /tmp/sysadmin-ct.tar -C / && pct exec 104 -- rm /tmp/sysadmin-ct.tar && rm /tmp/sysadmin-ct.tar && pct exec 104 -- systemctl daemon-reload && pct exec 104 -- systemctl enable --now sysadmin-splunk.timer && pct exec 104 -- systemctl start --no-block sysadmin-splunk.service').strip())
 else:
  sudo='' if role=='pve' else 'sudo '
  ssh(h,sudo+'tar -xf - -C /',package(role))
  print(h,ssh(h,sudo+'systemctl daemon-reload && '+sudo+'systemctl enable --now sysadmin-splunk.timer && '+sudo+'systemctl start --no-block sysadmin-splunk.service').strip())
