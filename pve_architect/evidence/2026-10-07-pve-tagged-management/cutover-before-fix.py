#!/usr/bin/python3
"""One-shot native-to-tagged management cutover, gated by tagged gateway ARP."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import time

WORK = Path('/root/pve-network-tagged4-20261007')
NIC = 'enp1s0f0'
HOST = '10.10.1.10'
GATEWAY = '10.10.1.1'
GATEWAY_MAC = bytes.fromhex('6e63f815eaa0')
SOL_PACKET = 263
PACKET_AUXDATA = 8

def status(state, **extra):
    value = dict(state=state, utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), **extra)
    temp = WORK / 'status.tmp'
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(WORK / 'status.json')
    print(json.dumps(value), flush=True)

def run(args, timeout=30):
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    print('$ ' + ' '.join(args) + '\n' + result.stdout, flush=True)
    result.check_returncode()
    return result.stdout

def gateway_reply(packet, ancillary, mac):
    if len(packet) < 42:
        return False
    ether_type = struct.unpack('!H', packet[12:14])[0]
    vlan = None
    offset = 14
    if ether_type == 0x8100:
        if len(packet) < 46:
            return False
        vlan = struct.unpack('!H', packet[14:16])[0] & 0xfff
        ether_type = struct.unpack('!H', packet[16:18])[0]
        offset = 18
    else:
        for level, kind, data in ancillary:
            if level == SOL_PACKET and kind == PACKET_AUXDATA and len(data) >= 20:
                fields = struct.unpack('=IIIHHHH', data[:20])
                if fields[0] & (1 << 4):
                    vlan = fields[5] & 0xfff
    arp = packet[offset:offset + 28]
    return (vlan == 4 and ether_type == 0x0806 and len(arp) == 28
            and arp[:8] == struct.pack('!HHBBH', 1, 0x0800, 6, 4, 2)
            and arp[8:14] == GATEWAY_MAC
            and arp[14:18] == socket.inet_aton(GATEWAY)
            and arp[18:24] == mac and arp[24:28] == socket.inet_aton(HOST))

def apply_configuration():
    current = Path('/etc/network/interfaces')
    expected = (WORK / 'before.sha256').read_text().strip()
    if hashlib.sha256(current.read_bytes()).hexdigest() != expected:
        status('aborted', reason='Live interfaces configuration changed after preparation')
        return
    status('applying', reason='Verified tagged VLAN 4 ARP reply from the management gateway')
    run(['systemd-run', '--unit=pve-tagged4-rollback', '--on-active=180s', '/bin/bash', str(WORK / 'rollback.sh')])
    try:
        shutil.copyfile(WORK / 'interfaces.proposed', current)
        run(['ifreload', '-a', '-s'])
        run(['ifreload', '-a'], timeout=60)
        run(['ping', '-I', 'vmbr0.4', '-c', '3', '-W', '2', GATEWAY], timeout=12)
        route = json.loads(run(['ip', '-j', 'route', 'get', GATEWAY]))
        assert route[0]['dev'] == 'vmbr0.4', route
        addresses = json.loads(run(['ip', '-j', '-4', 'address', 'show', 'dev', 'vmbr0.4']))
        assert any(a.get('local') == HOST for a in addresses[0]['addr_info']), addresses
        parent = json.loads(run(['ip', '-j', '-4', 'address', 'show', 'dev', 'vmbr0']))
        assert not parent[0]['addr_info'], parent
        vlans = json.loads(run(['bridge', '-j', 'vlan', 'show', 'dev', NIC]))[0]['vlans']
        assert {v['vlan'] for v in vlans} == {2, 4}, vlans
        assert not any('PVID' in v.get('flags', []) or 'Egress Untagged' in v.get('flags', []) for v in vlans), vlans
        run(['systemctl', 'is-active', 'pveproxy', 'pvedaemon', 'pvestatd', 'pve-cluster', 'ssh'])
        run(['curl', '--fail', '--silent', '--insecure', '--max-time', '8', '--output', '/dev/null', 'https://127.0.0.1:8006/'])
        (WORK / 'committed').write_text('Tagged VLAN 4 gateway and tagged-only uplink verified.\n')
        run(['systemctl', 'stop', 'pve-tagged4-rollback.timer'])
        status('complete', management='10.10.1.10/24 on vmbr0.4', uplink_tagged_vlans=[2, 4])
    except Exception as exc:
        status('rolling_back', error=str(exc))
        run(['/bin/bash', str(WORK / 'rollback.sh')], timeout=70)
        run(['systemctl', 'stop', 'pve-tagged4-rollback.timer'])
        status('rolled_back', reason='Validation failed; switch may need native VLAN 4 restored', error=str(exc))

def main():
    mac = bytes.fromhex(Path('/sys/class/net/' + NIC + '/address').read_text().strip().replace(':', ''))
    packet = (b'\xff' * 6 + mac + struct.pack('!HHH', 0x8100, 4, 0x0806)
              + struct.pack('!HHBBH', 1, 0x0800, 6, 4, 1) + mac + socket.inet_aton(HOST)
              + b'\x00' * 6 + socket.inet_aton(GATEWAY))
    packet = packet.ljust(60, b'\x00')
    with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3)) as sock:
        sock.setsockopt(SOL_PACKET, PACKET_AUXDATA, 1)
        sock.bind((NIC, 0))
        sock.settimeout(0.5)
        start = time.monotonic()
        next_probe = start
        deadline = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15)
        status('armed', expires_utc=deadline.isoformat(), trigger='Tagged VLAN 4 ARP reply from 10.10.1.1')
        while time.monotonic() - start < 900:
            if time.monotonic() >= next_probe:
                sock.send(packet)
                next_probe = time.monotonic() + 2
            try:
                data, ancillary, flags, address = sock.recvmsg(4096, 128)
            except socket.timeout:
                continue
            if address[2] != 4 and gateway_reply(data, ancillary, mac):
                apply_configuration()
                return
        status('expired', reason='No verified tagged VLAN 4 gateway reply in 15 minutes; live configuration unchanged')

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        status('failed', error=str(exc))
        raise
