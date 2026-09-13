# Splunk server health deployment

## Local restoration and AI Sysadmin integration — 2026-09-13

The local instance was restored from the saved 9.3.14 installer and deployment
configuration after an incomplete 9.0.9 tree was found with no runtime data. The
incomplete tree is preserved at /opt/splunk-incomplete-20260913. Existing admin
credentials were reused; the public CA reference was refreshed. Earlier indexed
history was absent; the AI Sysadmin source logs were fully ingested.

The ai_sysadmin app and its two dashboards are now installed and live-verified.
It is registered in the guarded upgrade policy with health/audit smoke searches.
KV Store is ready; final Splunk health reports an outstanding red IOWait finding. The active trial expires
2026-11-12 12:12:21 UTC (500 MiB/day); this supersedes the earlier trial date below.
The prior support exception remains. Full recovery and integration evidence:
/home/bot/sysadmin/reports/2026-09-13-splunk-integration.md


Installed and verified on 2026-09-09 on Ubuntu 24.04.5 host `sandbox`.

## Running installation

Splunk Enterprise **9.3.14**, build `02bbaf562558`, is installed in `/opt/splunk`. The `Splunkd` systemd service is enabled and runs as the dedicated non-login `splunk` account. KV Store is enabled and reports **ready**. The user explicitly requested a CPU-compatible older release after rejecting a current release with KV Store disabled.

9.3 is the last branch compatible with this VM's CPU features. It reached vendor end of support on **2026-07-24**. The archived download lists Linux 6.x, but the 9.3 system requirements table does not mark Enterprise support for Linux 6.x. This installation has been verified to run on this host; it is not a currently vendor-supported deployment. Future migration to a supported release requires a compatible CPU configuration or another host.

**No server reboot occurred.** Boot ID remains `4d9616ea-5b93-4d19-b182-b9920425dde4`. Existing Docker, LiteLLM and SSH services remained active. Only the newly installed Splunk service was started/stopped while correcting its initial configuration.

## Access

From your workstation, use the same server address you normally use for SSH:

```sh
ssh -N -L 8000:127.0.0.1:8000 bot@SERVER_ADDRESS
```

Open **https://localhost:8000/en-US/app/server_health/server_health**.

Username: **admin**. The generated password is in `/home/bot/splunk/.secrets/splunk-admin.json`, owned by `bot`, mode `0600`, inside a `0700` directory. Retrieve it locally; it was not printed to task logs. Splunk consumed and removed the initial `user-seed.conf` file after creating the account.

HTTPS uses Splunk's initial local certificate, so the browser may display a certificate warning. The API verification helper trusts the installation CA but disables hostname checking for the default certificate. All four Splunk listeners (8000, 8089, 8065, 8191) bind to **127.0.0.1**. No inbound firewall ports were opened.

The active trial allows **500 MiB/day**, expiring **2026-11-08 at 15:33:30 UTC**. Apply an appropriate license before that date for continued Enterprise functionality. The installation was not switched to the authentication-free Free license.

## Resource sizing and OS tuning

The host has 4 vCPUs, about 16 GiB RAM, and a 97 GiB root filesystem shared with other services.

| Setting | Applied value |
| --- | --- |
| CPU quota | 200%, equivalent to two CPU cores |
| CPU / I/O scheduling weights | 50 / 50, lower relative priority |
| Process nice level | 5 |
| Memory high / hard ceiling | 5 GiB / 6 GiB |
| Splunk swap ceiling | 512 MiB |
| Open files / user process limit | 65,536 / 16,000 |
| Service task limit | 4,096 |
| Concurrent searches | 2; dashboard base searches run in sequence |
| Real-time searches | Disabled through concurrency limit |
| Indexing pipelines | 1 |
| KV Store cache | 5% of host RAM |
| Indexing free-space guard | Stops indexing below 15 GiB free |

Transparent Huge Pages are disabled **only for Splunk and its descendants**, using `PR_SET_THP_DISABLE` in the service startup wrapper. `/proc/<splunkd-pid>/status` was checked and reported `THP_enabled: 0` and `NoNewPrivs: 1`. Global THP, swappiness, swap devices, networking, storage, bootloader, and unrelated service limits were not changed. Existing `vm.max_map_count` and `fs.file-max` are sufficient; the system clock is synchronized.

Splunk used about 0.5–0.7 GiB during verification, comfortably below the limit. A hard memory limit can terminate Splunk processes if future workloads exceed it. The limit protects host headroom; additional apps/search load require reassessment.

## Data and dashboard

- `host_metrics`: CPU, load, RAM, swap, uptime, local filesystem capacity/inodes, sampled disk/network I/O, systemd service state, and the ten processes with largest resident memory. Runs every **60 seconds**. CPU/I/O measure a one-second sample, so short spikes between samples can be missed. Process arguments and environments are not collected.
- `host_os`: journal priorities **0–6**, collected every **30 seconds**, at most **2,000 events per batch**, with a 25-second time limit. Initial collection begins five minutes before first run. Only selected journal fields are indexed; messages over 12,000 characters are truncated and flagged.
- Journal checkpoint: `/opt/splunk/var/lib/splunk/server_health/journal.cursor`. It advances after stdout flush. A crash before checkpoint can replay a batch; expired cursors emit an error and recover the last five minutes. This is a lightweight scripted input, not transactional exactly-once delivery.
- The `splunk` account belongs to `systemd-journal` to read system logs. It has no sudo privileges and no Docker socket access.
- The **Server Health** app has 14 panels covering telemetry freshness, utilization, storage, I/O, failed/main services, processes, collector errors and recent journal warnings/errors. Refresh the page to update. Inventory covers five minutes, trends one hour and journal warnings fifteen minutes. Three base searches are sequenced to avoid self-contention under the two-search cap.

Metrics retain up to **14 days or 2 GiB**; journals retain up to **14 days or 4 GiB**, whichever limit is reached first. Internal indexes have explicit or inherited smaller size limits; the effective active-index caps sum to about **13 GiB**, with possible transient bucket overhead. Binaries, KV Store, dispatch artifacts and log files need additional space. The free-space guard is not a filesystem quota. Retention removes indexed copies; it does not delete original OS journals.

The dashboard reports a pre-existing failed `systemd-networkd-wait-online.service`. No network repair was attempted. Initial Splunk setup failures can appear in recent journal history; they do not indicate the current service is failed.

## Files and maintenance

| Purpose | Location |
| --- | --- |
| App/collectors | `/opt/splunk/etc/apps/server_health` |
| Live dashboard override | `/opt/splunk/etc/apps/server_health/local/data/ui/views/server_health.xml` |
| Server, web, index, search settings | `/opt/splunk/etc/system/local` |
| Generated service | `/etc/systemd/system/Splunkd.service` |
| Resource drop-in | `/etc/systemd/system/Splunkd.service.d/resource-limits.conf` |
| THP and URI-cache startup wrapper | `/opt/splunk/etc/system/local/splunk-launch-no-thp.py` |
| Readable deployment sources | `/home/bot/splunk/deployment` |
| Verification evidence and screenshot | `/home/bot/splunk/evidence` |
| Verified 9.3.14 installer | `/home/bot/splunk/downloads` |

The startup wrapper also populates Splunk's local management-URI cache using `splunk cmd splunkd local-rest-uri`. This prevents repeated missing-cache errors from the built-in 9.3 maintenance script. Optional outbound usage telemetry is disabled. Email alerts and remote forwarding/receiving are not configured.

Check service state with `systemctl status Splunkd`. Validate configuration with `sudo runuser -u splunk -- /opt/splunk/bin/splunk btool check`. Manage **only this service** when changes require a restart. To stop and disable the installation without deleting data, use `sudo systemctl disable --now Splunkd`.

Before future changes, back up the configuration and relevant data outside this server. Avoid editing Splunk's shipped defaults. The dashboard was updated through the REST API in the shared `nobody/server_health` namespace; its final source is also saved in this deployment directory.

## Verification

- Official installer SHA-512 matched the vendor checksum.
- Splunk configuration and systemd unit validation passed.
- Authenticated API reports version 9.3.14 and KV Store ready.
- Metrics and journal events are indexed with valid JSON fields and timestamps.
- A journal verification event was indexed exactly once across multiple polling intervals.
- Every dashboard query executed successfully against live data.
- Browser login passed; all **14 panels** completed, the journal event was visible, and there were **no JavaScript errors**. See `../evidence/dashboard.png`.
- Cgroup limits are enforced; no memory high/max/OOM events occurred during validation.
- Splunk is enabled at boot; a server reboot was deliberately not tested.
- Boot ID and existing service health checked against the original baseline.

## Vendor references

- [Official previous releases](https://www.splunk.com/en_us/download/previous-releases.html)
- [Support lifecycle](https://www.splunk.com/en_us/legal/splunk-software-support-policy.html)
- [9.3 system requirements](https://help.splunk.com/en/splunk-enterprise/get-started/install-and-upgrade/9.3/plan-your-splunk-enterprise-installation/system-requirements-for-use-of-splunk-enterprise-on-premises)
- [Newer CPU requirements](https://help.splunk.com/en/splunk-enterprise/get-started/install-and-upgrade/10.4/upgrade-or-migrate-splunk-enterprise/about-upgrading-to-10.4-read-this-first)

Configuration settings were checked against the installed 9.3.14 README specifications, then checked using `btool` and runtime observations.
