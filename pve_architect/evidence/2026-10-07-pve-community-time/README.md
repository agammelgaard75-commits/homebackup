# PVE community repositories and time synchronization

Host: `sandboxpve` / `10.10.1.10`. Date: 2026-10-07.
Result: requested configuration applied; SSH and fresh authenticated PVE API access verified.

| Item | Evidence |
| --- | --- |
| Time fixed | Chrony stepped the clock backward by 7204.170623 seconds. |
| Persistent time sources | `162.159.200.1` and `162.159.200.123`, configured in `/etc/chrony/sources.d/sandbox-ip.sources`; Chrony enabled at boot. |
| Synchronization | `NTPSynchronized=yes`; leap status `Normal`; selected source `162.159.200.123`. Initial frequency estimates were still converging. |
| Community repositories | PVE `trixie/pve-no-subscription` and Ceph Squid `trixie/no-subscription`; enterprise repository disabled. APT source parsing passed with no enterprise targets. |
| Access | Fresh root API login HTTP 200; authenticated version request HTTP 200; SSH and all checked core PVE services active. |
| Preserved settings | DNS, network interfaces, SSH configuration and storage checksums unchanged; firewall remains disabled. No backup jobs or access settings changed. |
| Installed software | PVE 9.0.3, kernel 6.14.8-2-pve. No packages installed/upgraded; no reboot. |

DNS remains configured as `127.0.0.1` with no local resolver, per instruction. Repository downloads remain blocked by that existing DNS issue; repository configuration was validated without downloading indexes. The subscription notification was not patched. Time-based log entries move backward during the correction.

## Changed files on PVE

- `/etc/chrony/chrony.conf`: disabled the hostname-based pool.
- `/etc/chrony/sources.d/sandbox-ip.sources`: added two IP-based time sources.
- `/etc/apt/sources.list.d/pve-enterprise.sources`: added `Enabled: no`.
- `/etc/apt/sources.list.d/pve-no-subscription.sources`: added the signed community repository.
- `/etc/apt/sources.list.d/ceph.sources`: switched the existing Squid repository to no-subscription.

## Evidence and rollback

- `before.txt`: baseline and successful direct NTP probes.
- `applied-script.sh`: exact remote change script, without credentials. Audit record; not intended for rerunning.
- `changes-and-verification.txt`: configuration diffs, initial synchronization and service checks.
- `final-verification.txt`: OS synchronization confirmation, repository checks and fresh API login.
- Original files and manifest retained on PVE at `/root/pve-change-backups/community-time-20261007T160539Z` (directory timestamp predates the clock correction).

Rollback: restore files listed under `existing` in that directory's `manifest.json` to their original paths, remove only the two files listed under `created`, then validate with `chronyd -p` and restart `chrony`. This would restore the previous unsynchronized time configuration and enterprise repositories.

## References

- [Cloudflare published NTP addresses](https://developers.cloudflare.com/time-services/ntp/usage/)
- [Official Proxmox repository documentation](https://github.com/proxmox/pve-docs/blob/master/pve-package-repos.adoc)
