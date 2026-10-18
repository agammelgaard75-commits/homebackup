
set -eu
export LC_ALL=C
backup_dir=/root/pve-change-backups/dns-$(date -u +%Y%m%dT%H%M%SZ)
install -d -m 700 "$backup_dir"
cp -a /etc/resolv.conf "$backup_dir/resolv.conf"
printf 'Rollback copy: %s/resolv.conf\n' "$backup_dir"
pvesh set /nodes/$(hostname)/dns --search home.lab --dns1 1.1.1.1 --dns2 8.8.8.8
printf '\n=== DNS after ===\n'
cat /etc/resolv.conf
pvesh get /nodes/$(hostname)/dns --output-format json
printf '\n=== Resolver verification ===\n'
for host in download.proxmox.com deb.debian.org security.debian.org sandboxpve.home.lab; do
 getent ahostsv4 "$host" | head -3
done
python3 - <<'INNER'
import socket
for host in ('download.proxmox.com','deb.debian.org','security.debian.org'):
 answers=socket.getaddrinfo(host,80,type=socket.SOCK_STREAM)
 assert answers
 print(host, 'PASS')
assert socket.gethostbyname('sandboxpve.home.lab') == '10.10.1.10'
print('PVE hostname PASS')
INNER
printf '\n=== Repository refresh (no package upgrades) ===\n'
apt-get -o APT::Update::Error-Mode=any -o Acquire::Retries=0 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 update
printf '\n=== Installed and available PVE versions ===\n'
apt-cache policy pve-manager proxmox-ve
printf '\n=== Health and preserved configuration ===\n'
sha256sum /etc/network/interfaces /etc/ssh/sshd_config /etc/pve/storage.cfg
systemctl is-active pveproxy pvedaemon pvestatd pve-cluster ssh chrony
systemctl --failed --no-pager
timedatectl show -p NTPSynchronized
pve-firewall status
