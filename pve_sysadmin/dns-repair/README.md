# Sandbox DNS and Splunk repair — 2026-10-16

DNS is served by unprivileged Debian container **104**, `dns01`, at **192.168.2.127**. It starts before the Splunk guests (PVE startup order 5). dnsmasq serves short names, `home.lab` names and PTR records; other queries forward to 1.1.1.1/8.8.8.8. It does not provide DHCP. Manage it through `pct exec 104`; SSH is disabled.

| Guest | Name | Static address | MAC |
|---|---|---|---|
| CT 104 | dns01.home.lab | 192.168.2.127 | BC:24:11:53:00:01 |
| VM 100 | splunk-cm.home.lab | 192.168.2.169 | BC:24:11:52:02:01 |
| VM 101 | splunk-idx1.home.lab | 192.168.2.171 | BC:24:11:52:02:02 |
| VM 102 | splunk-idx2.home.lab | 192.168.2.173 | BC:24:11:52:02:03 |
| VM 103 | splunk-sh.home.lab | 192.168.2.175 | BC:24:11:52:02:04 |

All use /24 and gateway 192.168.2.1. The four VMs use only 192.168.2.127 for DNS, with search domain home.lab. These are their current DHCP-assigned addresses converted to static addresses; **the network owner still needs to reserve/exclude all five addresses in UniFi**. No UniFi configuration was changed. To resolve these names from other clients, configure those clients or the router's DNS forwarding/DHCP DNS option to use this DNS server. No controller network settings were changed.

Search UI: https://192.168.2.175:8000 or https://splunk-sh.home.lab:8000 when using sandbox DNS. Manager UI: https://192.168.2.169:8000. Existing self-signed TLS certificates and credentials remain in use. Indexers intentionally do not run a web UI.

Configuration:
- CT 104: `/etc/dnsmasq.conf` (copy in this directory); PVE CT configuration supplies its static interface and boot order. `nesting=1` is required for this Debian/systemd container's mounts; unprivileged mode remains enabled.
- VMs: `/etc/netplan/50-cloud-init.yaml`; cloud-init network regeneration disabled by `/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg`. PVE `ipconfig0`, nameserver and searchdomain also updated to match.
- Original configuration backups: `/root/dns-repair-20261016/` on PVE and each VM.
- Secrets remain in `/home/bot/pve_architect/.secrets/splunk-lab-access.json`; its old IP URLs are stale. Use the addresses above. `known_hosts` here was generated from guest-agent-verified host keys; the previous host-key warnings were due to DHCP addresses moving between VMs.

Validation completed: DNS UDP/TCP, short/FQDN/PTR, external forwarding, DNS reboot persistence with no failed units; both indexers Up/searchable, replication factor 2 and search factor 2 met; two HEC test events ingested into `lab` and retrieved through the search head; recent `_internal` events from all four servers searchable. Only Splunkd on the search head was restarted. No VM or PVE reboot and no patches performed.

Residual observations: Splunk reported I/O-wait and ingestion-latency alerts during backlog recovery. An indexer startup log also recorded an automatically truncated/rebuilt `_metrics` bucket from the previous unclean shutdown. These are separate from the resolved DNS failure; historic metrics integrity is not guaranteed.

Inspection helpers (run from this directory): `python3 check_splunk.py`. `test_ingest.py` deliberately adds two labelled validation events to the lab index. Mutation helpers require `PVE_PASSWORD` in the environment; do not rerun them as health checks.
