# PVE upgrade — 2026-10-07

Host: `sandboxpve` / `10.10.1.10`. **Completed and verified after reboot.**

| Component | Before | After |
| --- | --- | --- |
| PVE manager | 9.0.3 | **9.2.21** |
| Running kernel | 6.14.8-2-pve | **7.0.14-22-pve** |
| Debian | 13.0 (initial checkup) | **13.7** |

- Refreshed signed Debian and PVE/Ceph no-subscription repositories; reviewed `apt-get -s dist-upgrade` before installation.
- Installed 270 upgrades and 24 new packages; removed only `libzfs6linux`, replaced by the new ZFS library. Download: 762 MB.
- Ran `apt-get dist-upgrade` as a persistent systemd job with existing configuration retained. Exit code **0**.
- Verified the new kernel/initramfs and GRUB configuration, then rebooted. Boot ID changed from `27f17aef-6a61-4810-9d8d-73cd91d8b5c8` to `8658673f-2db9-4b21-991b-355a991b5e4f`.

## Verification

- `dpkg --audit`: clean. `apt-get check`: passed. Upgrade simulation: **0 pending updates**.
- PVE services, scheduler, SSH and Chrony active; **0 failed systemd units**.
- `local` and `local-lvm` active; SSD SMART passed; `/dev/kvm` present. No guests configured; guest operation was not tested.
- DNS resolves repository names; management IP and default route unchanged; `NTPSynchronized=yes`.
- Fresh root API login: **HTTP 200**; authenticated API reports **9.2.21**; web UI HTTP 200.
- Checksums unchanged for DNS, network interfaces, SSH, storage, Chrony and repository configurations. Root password access remains enabled; firewall remains disabled. No backup jobs configured.

Existing boot messages remain: AMD GPIO IRQ 7 disabled and blkmapd missing NFS blocklayout pipe. Both appeared before the upgrade; no associated operational failure observed. Package installation also logged transient system-bus reload messages; final package checks, service checks and reboot verification passed.

## Evidence and recovery

- `preflight.txt`: original state, configuration hashes and upgrade simulation.
- `launch-script.sh`, `launch.txt`: exact upgrade job and launch result.
- `upgrade.log`: full package installation output.
- `pre-reboot.txt`: package checks and verified GRUB entry.
- `reboot.txt`: reboot request and new boot identity.
- `post-reboot.txt`: final health, version, configuration and access verification.
- Supporting scripts and progress are retained alongside these files. Scripts are audit records, not instructions to rerun.

Root-only recovery material on PVE: `/root/pve-upgrade-20261007/config-before.tar.gz`, package inventory, and original upgrade logs. The archive includes sensitive host configuration and was not copied into this project. It is a configuration recovery copy, **not a complete package rollback**. Previous kernels remain available in GRUB; no autoremove was performed.

Reference: [Official Proxmox VE administration guide](https://pve.proxmox.com/pve-docs/pve-admin-guide.pdf).
