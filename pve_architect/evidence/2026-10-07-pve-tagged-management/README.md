# Tagged VLAN management and guests — 2026-10-07

**Completed at 19:21:13 UTC; external access verified at 19:22 UTC.**

| Purpose | Configuration |
| --- | --- |
| PVE management | `10.10.1.10/24` on `vmbr0.4`, tagged VLAN **4** |
| Default gateway | `10.10.1.1` through `vmbr0.4` |
| VM/container traffic | Virtual NIC bridge `vmbr0`, VLAN tag **2** |
| Physical uplink | `enp1s0f0`, tagged VLANs **2 and 4 only**, untagged traffic disabled |

Configuration is persistent in `/etc/network/interfaces`. `vmbr0` has no IPv4 address. Its internal default VLAN entry is not present on the physical uplink and does not provide an untagged path through the switch port. No reboot was required or performed.

## Verification

- Automatic cutover status: `complete`; committed marker present.
- Fresh external SSH and root PVE API login succeeded (HTTP 200).
- PVE API confirms management interface `vmbr0.4` and bridge allowed VLANs `2 4`.
- Runtime uplink VLAN table contains only VLANs 2 and 4, with no PVID or Egress Untagged flags.
- VLAN 4 gateway ping: 3/3 replies. DNS works; `NTPSynchronized=yes`.
- Core PVE services, SSH and Chrony active; zero failed systemd units.
- Network syntax validation passed after application.
- Cutover service exited successfully and rollback timer is inactive.
- No guests exist, so actual guest IP addressing/DHCP connectivity remains untested. Guest NICs must specify tag 2.

Final evidence: `final-tagged-verification.txt`. Exact persistent configuration: `interfaces.proposed` (now applied).

## Cutover history

The initial switch change interrupted access before preparation; the user restored native VLAN 4. A one-shot detector was then staged to apply the tagged-only configuration after a verified tagged VLAN 4 ARP reply from the gateway.

The first automated attempt successfully applied tagged management and reached the gateway, but a validation bug treated an empty IPv4 result for the parent bridge as an error and unnecessarily rolled back. The bug was corrected and the validation tested against real iproute2 output in an isolated temporary network namespace, which was removed afterward. The second attempt completed successfully.

Supporting evidence: `recovery-diagnosis.txt`, `validation-regression.txt`, `rearming-v2.txt`, plus earlier baseline and preparation logs. `cutover.py` is the corrected deployed script; `cutover-before-fix.py` preserves the first version. These files are audit records, not instructions to rerun a completed cutover.

## Recovery material

PVE directory `/root/pve-network-tagged4-20261007/` retains `status.json`, `cutover-v2.log`, original `interfaces.before`, and the proposal and scripts. The original configuration requires switch native/untagged VLAN 4 and is incompatible with the current tagged-only uplink without a coordinated switch change. The committed marker prevents the old rollback script from automatically undoing the completed cutover.

No switch configuration was changed by the agent; the user performed the switch changes.
