export LC_ALL=C
qm cloudinit dump 100 network
bridge vlan show
printf '\n=== VLAN 2 DHCP traffic ===\n'
timeout -s INT 20 tcpdump -nn -e -i enp1s0f0 -c 12 'vlan 2 and (udp port 67 or udp port 68)' || true
