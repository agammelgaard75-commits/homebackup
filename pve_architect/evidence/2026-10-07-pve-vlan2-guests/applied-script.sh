
set -eu
export LC_ALL=C
work_dir=/root/pve-network-vlan2-20261007
install -d -m 700 "$work_dir"
test ! -e /etc/network/interfaces.new
test ! -e "$work_dir/interfaces.before"
cp -a /etc/network/interfaces "$work_dir/interfaces.before"
cat > "$work_dir/rollback.sh" <<'ROLLBACK'
#!/bin/bash
set -eu
cp -a /root/pve-network-vlan2-20261007/interfaces.before /etc/network/interfaces
ifreload -a
ROLLBACK
chmod 700 "$work_dir/rollback.sh"
systemd-run --unit=pve-vlan2-rollback --on-active=180s /bin/bash "$work_dir/rollback.sh"
python3 - <<'INNER'
from pathlib import Path
import difflib
p=Path('/etc/network/interfaces');old=p.read_text()
assert 'bridge-vlan-aware' not in old
assert '\tbridge-fd 0\n' in old
new=old.replace('\tbridge-fd 0\n','\tbridge-fd 0\n\tbridge-vlan-aware yes\n\tbridge-vids 2\n',1)
p.write_text(new)
print(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='interfaces.before',tofile='interfaces.after')))
INNER
ifreload -a -s
ifreload -a
printf '\n=== Applied VLAN configuration ===\n'
cat /etc/network/interfaces
bridge vlan show
ip -br address
ip route
ping -c 3 -W 2 10.10.1.1
