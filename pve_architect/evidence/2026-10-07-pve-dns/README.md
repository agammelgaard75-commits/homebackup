# PVE DNS repair — 2026-10-07

Host: `sandboxpve` / `10.10.1.10`. Result: DNS fixed and package indexes refreshed successfully.

- Replaced non-working resolver `127.0.0.1` with `1.1.1.1` and `8.8.8.8` through the native PVE DNS configuration API. Retained `home.lab` search domain.
- Both resolvers passed direct DNS probes before the change.
- Host resolution passed for Proxmox and Debian repositories; `sandboxpve.home.lab` still resolves to `10.10.1.10` through the host configuration. Public resolvers do not provide other private `home.lab` records.
- `apt-get update` succeeded with strict error handling: Debian, security, updates, PVE no-subscription and Ceph Squid no-subscription indexes fetched and parsed without errors.
- PVE manager installed: **9.0.3**; available candidate: **9.2.21**. No packages upgraded and no reboot.
- Core PVE services, SSH and Chrony active; zero failed systemd units; `NTPSynchronized=yes`; PVE web UI HTTP 200.
- Network interfaces, SSH and storage configuration checksums unchanged. Firewall remains disabled; no management-access or backup changes.

Evidence: `before.txt`, `applied-script.sh`, `changes-and-verification.txt`. The script is an audit record, not an instruction to rerun it.

Rollback copy on PVE: `/root/pve-change-backups/dns-20261007T141212Z/resolv.conf`. Restoring that file to `/etc/resolv.conf` reinstates the previous broken localhost resolver; no networking restart is required.

This repair resolves the DNS limitation recorded in the earlier community/time evidence.
