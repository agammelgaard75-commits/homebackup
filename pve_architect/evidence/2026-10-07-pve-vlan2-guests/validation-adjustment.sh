
set -eu
export LC_ALL=C
python3 - <<'INNER'
from pathlib import Path
p=Path('/etc/network/interfaces');s=p.read_text();assert 'bridge-vlan-aware yes' in s
p.write_text(s.replace('\tbridge-fd 0\n','\tbridge-fd 2\n'))
INNER
ifreload -a -s
ifreload -a
cat /etc/network/interfaces
bridge vlan show
ip -br address
ip route
ping -c 3 -W 2 10.10.1.1
