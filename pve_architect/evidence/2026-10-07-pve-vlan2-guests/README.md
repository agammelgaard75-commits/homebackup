> Superseded: management now uses tagged VLAN 4. See [final tagged configuration](../2026-10-07-pve-tagged-management/README.md).

# Native VLAN 4 management / tagged VLAN 2 guests — 2026-10-07

Host: `sandboxpve` / `10.10.1.10`. **Applied and verified.**

User confirmed the switch port uses native VLAN 4 for management and VLAN 2 is for VMs.

| Purpose | PVE configuration | Switch-facing traffic |
| --- | --- | --- |
| Management | `10.10.1.10/24` on `vmbr0`, gateway `10.10.1.1` | Untagged; switch assigns native VLAN 4 |
| VM/container network | Bridge `vmbr0`, virtual NIC VLAN tag **2** | Tagged VLAN 2 |

## Changes

- Enabled `bridge-vlan-aware yes` and `bridge-vids 2` on `vmbr0`; physical uplink remains `enp1s0f0`.
- Kept management IP and gateway directly on `vmbr0`. No `vmbr0.4` or host IP on VLAN 2 was added.
- Changed `bridge-fd 0` to `bridge-fd 2`: the upgraded ifupdown2 syntax checker rejected the old value as outside its supported 2–255 range. STP remains disabled. The initial syntax-check failure occurred before applying live changes; validation then passed and `ifreload -a` succeeded.
- Applied without a reboot, protected by a 180-second automatic rollback timer. Cancelled the timer after successful fresh API login, fresh SSH connection and gateway ping.

## Verification

- PVE API confirms `bridge_vlan_aware=1`, `bridge_vids=2`, management `10.10.1.10`.
- Runtime VLAN table: uplink has VLAN 2 tagged and the default internal PVID 1 untagged. Internal PVID 1 represents the untagged path within Linux; the external switch maps these untagged frames to native VLAN 4. It does not mean management moved to switch VLAN 1.
- Gateway reachable; PVE services and SSH active; fresh root API login HTTP 200.
- DNS, SSH and storage configuration checksums unchanged.
- Physical NIC capture observed **802.1Q VLAN 2 ARP broadcasts from `192.168.2.1`**, confirming tagged VLAN 2 reaches PVE. No switch changes were required or performed.
- No existing guests needed changes. Future VM/container NICs must explicitly use **VLAN tag 2**; leaving the tag blank would attach them to the native management network.
- Guest IP addressing, DHCP and end-to-end guest connectivity were not tested because no guest exists.

## Evidence and recovery

`before.txt`, `changes.txt`, `apply-verification.txt` and `final-verification.txt` contain the observations and results. The two shell scripts record the applied changes and validation adjustment.

Original configuration on PVE: `/root/pve-network-vlan2-20261007/interfaces.before`. Recovery script: `/root/pve-network-vlan2-20261007/rollback.sh` (restores the original file and runs `ifreload -a`). Automatic rollback timer is inactive.

Reference: [Official Proxmox network configuration](https://github.com/proxmox/pve-docs/blob/master/pve-network.adoc).
