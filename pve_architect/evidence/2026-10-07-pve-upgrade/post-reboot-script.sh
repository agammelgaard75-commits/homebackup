
set -eu
export LC_ALL=C
printf '\n=== Version and boot ===\n'
date -u
pveversion
cat /etc/debian_version
uname -r
cat /proc/sys/kernel/random/boot_id
uptime
test "$(uname -r)" = 7.0.14-22-pve
printf '\n=== Packages ===\n'
test -z "$(dpkg --audit)"
apt-get check
apt-get -s dist-upgrade | tail -5
printf '\n=== Services ===\n'
systemctl is-active pveproxy pvedaemon pvestatd pve-cluster pvescheduler ssh chrony
systemctl --failed --no-pager
printf '\n=== Storage and virtualization ===\n'
pvesm status
df -h /
lvs -o lv_name,lv_size,data_percent,metadata_percent
qm list
pct list
test -c /dev/kvm && echo KVM-ready
smartctl -H /dev/nvme0n1
printf '\n=== DNS, network, and time ===\n'
ip -br address
ip route
getent ahostsv4 download.proxmox.com | head -3
getent ahostsv4 sandboxpve.home.lab | head -3
chronyc waitsync 20 0.1 0 1
chronyc -n tracking
timedatectl show -p NTPSynchronized -p Timezone
printf '\n=== Access and configuration preservation ===\n'
sshd -t
sshd -T | grep -E '^(permitrootlogin|passwordauthentication|pubkeyauthentication) '
pve-firewall status
sha256sum /etc/resolv.conf /etc/network/interfaces /etc/ssh/sshd_config /etc/pve/storage.cfg /etc/chrony/chrony.conf /etc/chrony/sources.d/sandbox-ip.sources /etc/apt/sources.list.d/*.sources
printf '\n=== Boot errors ===\n'
journalctl -b -p err --no-pager -n 30
