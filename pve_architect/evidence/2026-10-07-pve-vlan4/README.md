# VLAN 4 assessment — 2026-10-07

Host: `sandboxpve` / `10.10.1.10`. No network configuration changes applied during this assessment.

## Verified

- Physical NIC: `enp1s0f0`, attached to `vmbr0`.
- Management: `10.10.1.10/24` directly on `vmbr0`; gateway `10.10.1.1`.
- Bridge VLAN filtering is disabled; no VLAN 4 interface exists.
- Gateway ping succeeded. Packet headers show untagged IPv4 gateway requests and replies on the physical NIC.
- No VLAN 4 ingress packets were observed in a roughly 14-second capture. This does not establish that VLAN 4 is absent from the switch port.
- No VMs or containers currently configured.

## Required distinction

An access/native VLAN 4 switch port presents untagged frames to PVE; the observed management configuration can be correct for that setup. If management must use tagged VLAN 4 on a trunk, the standard VLAN-aware design places the management address and gateway on `vmbr0.4`, with `vmbr0` VLAN-aware and VLAN 4 allowed. Guests on that trunk use VLAN tag 4 on their virtual NICs.

Before applying network changes, clarify whether VLAN 4 carries management, guests, or both, and whether the PVE-facing switch port tags VLAN 4. The switch has not been inspected or modified; only the PVE host was accessed. An incorrect tagging change could interrupt the current working management connection.

Evidence: `before.txt` and `traffic-observation.txt`.

Reference: [Official Proxmox network configuration](https://github.com/proxmox/pve-docs/blob/master/pve-network.adoc).

Follow-up: switch native VLAN 4 confirmed by user; [tagged VLAN 2 guest configuration applied and verified](../2026-10-07-pve-vlan2-guests/README.md).
