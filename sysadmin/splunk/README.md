# Splunk integration

Enabled and verified on this host on 2026-09-13. The `ai_sysadmin` app monitors
production audit, health and anomaly JSONL files. Dry-run logs are excluded.
The dedicated index retains up to 365 days or 2 GiB, whichever comes first;
bucket overhead can temporarily exceed the size limit. Source logs rotate weekly
and retain 52 archives independently of indexed retention.

## Access

Splunk remains on localhost HTTPS. Use the existing SSH tunnel or open one:

```sh
ssh -N -L 8000:127.0.0.1:8000 bot@192.168.2.100
```

- [Server Health](https://localhost:8000/en-US/app/ai_sysadmin/health_dashboard)
- [Anomalies](https://localhost:8000/en-US/app/ai_sysadmin/anomaly_dashboard)

Use the existing `admin` credentials stored privately in
`/home/bot/splunk/.secrets/splunk-admin.json`. They were reused without being printed
or changed. Splunk uses a local certificate, so a browser certificate notice is
expected. No listener or firewall port was opened to the network.

The health dashboard shows current disk space, failed/restarting services,
available upgrades, health history and maintenance closures. The anomaly dashboard
shows recorded findings and severity history. Historical findings can include
resolved issues; the count is not a count of currently open incidents.

## Installation and verification

`sudo ./scripts/install.sh` deploys the app when `splunk.install_app=true` and
`splunk.home` identifies a local Splunk Enterprise installation. Existing config
is preserved. The installer grants the Splunk group read/traverse access to
existing logs and uses setgid directory ownership for future logs. Install the
`logrotate` package to run the supplied weekly rotation policy; it is installed
and its timer is enabled on this host.

The installer does not restart Splunk or start maintenance timers. Apply app
changes through the site's normal Splunk activation procedure. This restoration
started Splunk with the app already installed. Reinstallation was checked to avoid
duplicate configuration or inputs; all source events remained indexed once per
source occurrence.

```spl
index=ai_sysadmin | stats count by sourcetype
```

All three monitored inputs, exact source event counts, timestamp extraction,
eight dashboard searches, the successful maintenance closure, the Splunk outage
anomaly, and the additional upgrade smoke searches were verified through the
existing authenticated loopback API. Evidence is in
`reports/splunk-live-verification.json` and `reports/2026-09-13-splunk-integration.md`.
Browser rendering was not separately automated.

To render assets without installation:

```sh
python3 scripts/render_deployment.py config/config.toml /tmp/ai-sysadmin-preview
```

For a Universal Forwarder topology, deploy inputs on the forwarder and the
index/props/dashboard assets on the appropriate indexer/search-head tier. This
host uses a standalone local Enterprise installation.

## Recovery notes

The incomplete 9.0.9 tree is preserved at `/opt/splunk-incomplete-20260913`.
The verified cached 9.3.14 release and saved local deployment settings restored
service. Earlier indexed Splunk history was absent and could not be recovered;
the maintenance JSONL source history was fully ingested. The restored trial allows 500 MiB/day through 2026-11-12 12:12:21 UTC.
The prior deployment's 9.3 support exception remains; recovery does not make the platform vendor-supported.
Backups, the original plan and closure are under
`/var/lib/ai-sysadmin/splunk-integration-20260913/`.

Final verification found intermittent red Splunk Resource Usage/IOWait. Ingestion
and dashboard queries passed, but the performance finding remains open and is
recorded separately in the anomaly stream. See `reports/splunk-final-health.json`.
