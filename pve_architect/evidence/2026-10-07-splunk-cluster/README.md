# Splunk sandbox — Ubuntu 26.04

Provisioned 7–8 October 2026 on PVE 9.2.21 (10.10.1.10).

| VM | Role | Address (DHCP) | vCPU | RAM | Disk |
|---|---|---|---:|---:|---:|
| 100 splunk-cm | Indexer cluster manager | 192.168.2.168 | 1 | 2 GiB | 16 GiB |
| 101 splunk-idx1 | Indexer | 192.168.2.169 | 2 | 3 GiB | 24 GiB |
| 102 splunk-idx2 | Indexer | 192.168.2.170 | 2 | 3 GiB | 24 GiB |
| 103 splunk-sh | Search head | 192.168.2.171 | 2 | 3 GiB | 20 GiB |

Total: 7 vCPU, 11 GiB RAM, 84 GiB thin-provisioned disks. Small learning lab; sized below production recommendations. All VMs share one physical host.

- Ubuntu 26.04.1 LTS cloud image; Splunk Enterprise 10.6.0.5, build 86587d4e3b27. Download checksums verified.
- Tagged VLAN 2 on vmbr0 for every VM. PVE management remains tagged VLAN 4. No external network changes.
- Replication factor 2; search factor 2. Cluster index definitions distributed by manager app `lab_indexes`.
- `lab`: 512 MiB per peer, seven-day retention; `main`: 1 GiB per peer, seven-day retention. These limits apply to these two indexes, not the entire Splunk installation.
- Splunk runs as the `splunk` service account, starts through systemd; VMs start with PVE. QEMU guest agents and time synchronization enabled.
- Indexer web interfaces and KV Store disabled to reduce resource use; search-head KV Store enabled. Manager and search-head internal logs forwarded to indexers.
- Each instance uses its own built-in Enterprise trial, as required by Splunk for trial distributed deployments. Valid through **7 December 2026**, 500 MB/day per instance. Continued clustering requires an appropriate Enterprise license; the permanent Free license is unsuitable. A shared trial license manager was rejected and corrected before acceptance testing.

## Access

- Search: https://192.168.2.171:8000
- Manager: https://192.168.2.168:8000
- Admin username: `admin`; credentials and HEC token in project `.secrets/splunk-lab-access.json` (mode 0600; excluded from Git).
- Guest SSH: user `ubuntu`, key `.secrets/splunk-lab-id_ed25519`.
- HEC: HTTPS port 8088 on either indexer; forwarder receiver: TCP 9997; management API: HTTPS 8089; replication: TCP 9887. Web/API/HEC use lab certificates.

Reserve these DHCP leases on the external DHCP server to keep cluster addresses stable (external network changes remain user-managed):

| MAC | Reserved address |
|---|---|
| BC:24:11:52:02:01 | 192.168.2.168 |
| BC:24:11:52:02:02 | 192.168.2.169 |
| BC:24:11:52:02:03 | 192.168.2.170 |
| BC:24:11:52:02:04 | 192.168.2.171 |

Guest host mappings currently use these addresses. Management-to-guest SSH from PVE times out; direct administration from the workspace works. PVE guest agents provide a console-independent control path.

## Verification

Completed 8 October 2026:

- Both indexers `Up`; replication factor 2 and search factor 2 met; all data searchable; no pending fixup tasks. All 11 buckets have two searchable copies (`validation.json`, `bucket-status.json`).
- Sent one HEC event to each indexer; search head returned both (`functional-test.json`).
- Stopped indexer 2: both events remained searchable on indexer 1. Restarted indexer 2 and verified full recovery (`failover-test.json`).
- Search-head KV Store ready; all four licenses valid; Splunk services enabled and active. Recent internal logs from all four nodes searchable (`internal-log-search.json`).
- Both web login pages returned HTTP 200 (`web-access.json`).
- Host available memory 2,597 MiB, host swap usage zero; VM autostart and VLAN tags verified (`final-pve-state.txt`).
- Splunk reports I/O-wait health warnings on this small shared host (`health-details.json`). Functional and cluster-redundancy checks pass; no warning thresholds were suppressed.
- During initial license correction, indexer 1 reached its six-minute systemd stop timeout before restarting. Later indexer 2 stop/start completed normally. Full VM/host reboot was not part of acceptance testing.
- Evidence and scripts scanned for generated passwords/tokens: none present.

## Sources

- [Official Ubuntu cloud image](https://cloud-images.ubuntu.com/releases/26.04/release/)
- [Splunk 10.6 supported systems](https://help.splunk.com/en/splunk-enterprise/get-started/install-and-upgrade/10.6/plan-your-splunk-enterprise-installation/system-requirements-for-use-of-splunk-enterprise-on-premises)
- [Splunk license types and separate trial licenses for distributed instances](https://help.splunk.com/en/data-management/splunk-enterprise-admin-manual/9.0/welcome-to-splunk-enterprise-administration/configure-splunk-licenses/types-of-splunk-enterprise-licenses)
