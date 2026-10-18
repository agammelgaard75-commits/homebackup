import base64,shlex
from ops import pve,guest
mapping={100:('splunk-cm','192.168.2.169','bc:24:11:52:02:01'),101:('splunk-idx1','192.168.2.171','bc:24:11:52:02:02'),102:('splunk-idx2','192.168.2.173','bc:24:11:52:02:03'),103:('splunk-sh','192.168.2.175','bc:24:11:52:02:04')}
for i,(name,ip,mac) in mapping.items():
 print(pve(f'mkdir -p /root/dns-repair-20261016; cp -an /etc/pve/qemu-server/{i}.conf /root/dns-repair-20261016/; qm set {i} --ipconfig0 ip={ip}/24,gw=192.168.2.1 --nameserver 192.168.2.127 --searchdomain home.lab'),flush=True)
 config=f'''# Static sandbox networking, managed 2026-10-16.
network:
  version: 2
  ethernets:
    eth0:
      match:
        macaddress: "{mac}"
      set-name: eth0
      dhcp4: false
      dhcp6: false
      accept-ra: false
      addresses: [{ip}/24]
      routes:
        - to: default
          via: 192.168.2.1
      nameservers:
        addresses: [192.168.2.127]
        search: [home.lab]
'''
 b=base64.b64encode(config.encode()).decode()
 script='''set -eu
mkdir -p /root/dns-repair-20261016
cp -an /etc/netplan /root/dns-repair-20261016/
cp -an /etc/cloud/cloud.cfg.d /root/dns-repair-20261016/
printf '%s' '''+shlex.quote(b)+''' | base64 -d > /etc/netplan/50-cloud-init.yaml
chmod 600 /etc/netplan/50-cloud-init.yaml
printf '%s\n' 'network: {config: disabled}' > /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg
netplan generate
netplan apply
resolvectl flush-caches
ip -4 -br addr show eth0
ip route show default
resolvectl dns eth0
getent ahostsv4 splunk-cm
getent ahostsv4 splunk-idx1
getent ahostsv4 splunk-idx2
'''
 print(name,guest(i,script),flush=True)
