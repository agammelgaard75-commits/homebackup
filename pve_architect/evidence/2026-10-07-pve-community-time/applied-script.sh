
set -eu
export LC_ALL=C
python3 - <<'INNER'
from pathlib import Path
import shutil,datetime,difflib
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=Path('/root/pve-change-backups')/('community-time-'+stamp)
backup.mkdir(parents=True,mode=0o700)
changes={
 '/etc/chrony/chrony.conf':Path('/etc/chrony/chrony.conf').read_text().replace('pool 2.debian.pool.ntp.org iburst','# DNS-independent time sources are configured in sources.d/sandbox-ip.sources'),
 '/etc/chrony/sources.d/sandbox-ip.sources':'# Cloudflare NTP; IP addresses avoid dependence on host DNS.\nserver 162.159.200.1 iburst\nserver 162.159.200.123 iburst\n',
 '/etc/apt/sources.list.d/pve-enterprise.sources':Path('/etc/apt/sources.list.d/pve-enterprise.sources').read_text().rstrip()+'\nEnabled: no\n',
 '/etc/apt/sources.list.d/ceph.sources':Path('/etc/apt/sources.list.d/ceph.sources').read_text().replace('https://enterprise.proxmox.com/debian/ceph-squid','http://download.proxmox.com/debian/ceph-squid').replace('Components: enterprise','Components: no-subscription'),
 '/etc/apt/sources.list.d/pve-no-subscription.sources':'Types: deb\nURIs: http://download.proxmox.com/debian/pve\nSuites: trixie\nComponents: pve-no-subscription\nSigned-By: /usr/share/keyrings/proxmox-archive-keyring.gpg\n',
}
assert not Path('/etc/chrony/sources.d/sandbox-ip.sources').exists()
assert not Path('/etc/apt/sources.list.d/pve-no-subscription.sources').exists()
assert Path('/usr/share/keyrings/proxmox-archive-keyring.gpg').is_file()
manifest={'backup':str(backup),'existing':[],'created':[]}
for name,after in changes.items():
 path=Path(name); before=path.read_text() if path.exists() else ''
 if path.exists():
  dest=backup/name.lstrip('/');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest);manifest['existing'].append(name)
 else:manifest['created'].append(name)
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(after)
 print(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=name+' before',tofile=name+' after')))
import json
(backup/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Rollback backup:',backup)
INNER
chronyd -p >/dev/null
systemctl restart chrony
printf '\n=== Wait for time synchronization (up to 45 seconds) ===\n'
chronyc waitsync 45 0.1 0 1
printf '\n=== Time verification ===\n'
date -u
chronyc -n tracking
chronyc -n sources -v
timedatectl show -p NTPSynchronized -p NTP -p Timezone
systemctl is-enabled chrony
printf '\n=== APT source parsing (no downloads) ===\n'
apt-get --print-uris update
printf '\n=== Preserved configuration checksums ===\n'
sha256sum /etc/resolv.conf /etc/network/interfaces /etc/ssh/sshd_config /etc/pve/storage.cfg
printf '\n=== PVE and access health ===\n'
pveversion
systemctl is-active pveproxy pvedaemon pvestatd pve-cluster ssh chrony
systemctl --failed --no-pager
sshd -T | grep -E '^(permitrootlogin|passwordauthentication|pubkeyauthentication) '
pve-firewall status
