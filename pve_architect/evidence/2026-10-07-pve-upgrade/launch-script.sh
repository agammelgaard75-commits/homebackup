
set -eu
export LC_ALL=C
work_dir=/root/pve-upgrade-20261007
install -d -m 700 "$work_dir"
test ! -e "$work_dir/upgrade.sh"
tar -czf "$work_dir/config-before.tar.gz" /etc/pve /etc/network/interfaces /etc/network/interfaces.d /etc/resolv.conf /etc/hosts /etc/ssh /etc/chrony /etc/apt /etc/default/grub /etc/default/grub.d 2>"$work_dir/config-archive.log"
dpkg-query -W > "$work_dir/packages-before.txt"
cat /proc/sys/kernel/random/boot_id > "$work_dir/boot-id-before.txt"
cat > "$work_dir/upgrade.sh" <<'UPGRADE'
#!/bin/bash
set -euo pipefail
export LC_ALL=C DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
work_dir=/root/pve-upgrade-20261007
exec >"$work_dir/upgrade.log" 2>&1
trap 'rc=$?; echo "$rc" > "$work_dir/exit-code"; date -u; exit "$rc"' EXIT
date -u
apt-get -s dist-upgrade > "$work_dir/final-simulation.txt"
python3 - <<'CHECK'
from pathlib import Path
s=Path('/root/pve-upgrade-20261007/final-simulation.txt').read_text()
removed=[x.split()[1] for x in s.splitlines() if x.startswith('Remv ')]
assert set(removed)<= {'libzfs6linux'},removed
CHECK
apt-get -y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold -o Acquire::Retries=2 dist-upgrade
dpkg --audit
apt-get check
pveversion -v
UPGRADE
chmod 700 "$work_dir/upgrade.sh"
systemd-run --unit=pve-upgrade-20261007 --property=Type=exec /bin/bash "$work_dir/upgrade.sh"
printf 'Upgrade running under systemd; evidence and recovery files: %s\n' "$work_dir"
