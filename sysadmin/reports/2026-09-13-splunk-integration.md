# Local Splunk integration — 2026-09-13

Status: CLOSED

Authorization: user requested Splunk integration and confirmed use of local Splunk.

Inspection: Splunkd is in a restart loop because its configured startup wrapper
is absent. /opt/splunk contains an uninitialized 9.0.9 distribution with no account
database, index data, local settings or custom apps. Earlier deployment evidence
and upgrade policy identify 9.3.14 as the CPU-compatible deployment; its installer,
configuration sources and existing admin credential file remain available. No
active upgrade transaction or running upgrade service was found. Cached 9.3.14
installer SHA-512 matches the previously saved vendor checksum.

Plan: preserve the incomplete tree; restore 9.3.14 from the verified local archive,
existing resource/loopback settings, THP wrapper and server_health app. Initialize
the absent account database using the existing private admin credential (do not
print it or change it). Install the ai_sysadmin app and grant the Splunk group
read/traverse access to existing and future JSONL logs. Enable app integration in
production configuration. Start only Splunkd, verify authenticated API/KV Store,
searchable events, JSON fields, timestamps and every dashboard query. Register
the verified local app with the existing guarded upgrade workflow.

The dedicated ai_sysadmin index retains up to 365 days or 2 GiB, whichever is
reached first (bucket overhead can temporarily exceed the cap). Existing logrotate
policy retains source logs separately. Dashboards display health, change closures
and recorded anomalies; historical anomalies are not labelled as open incidents.

Risk/limits: this repairs missing Splunk runtime state and does not recover absent
historical indexed data. Existing maintenance JSONL files can be indexed in full.
The old tree and configuration backups will be preserved. No reboot, network
changes, firewall changes or unrelated service restarts. Splunk remains loopback
only. 9.3.14 retains the earlier deployment's documented support exception.

Backout: stop Splunkd, preserve the restored tree, return the incomplete tree to
/opt/splunk and restore saved config/CA/log permissions as appropriate. No source
logs or historical change records will be deleted. Original state cannot provide
a working Splunk service; keep evidence for further recovery if needed.

Validation: app renderer/idempotency and lifecycle tests; btool check; actual
service listeners and login; counts and fields for all three sourcetypes; dashboard
queries and anomaly visibility; fresh health event; repeat-install/rotation checks.

Closure: implemented and verified; results below.

## Implementation and verification

Local Splunk 9.3.14 (build 02bbaf562558) is running as the existing splunk account.
The incomplete 9.0.9 tree remains at `/opt/splunk-incomplete-20260913`. Saved local
settings, the THP wrapper, resource limits and server_health app were restored.
Credentials were reused; the public CA reference was refreshed after the old CA
was backed up. All listeners (8000/8089/8065/8191) bind to 127.0.0.1. No network,
firewall or unrelated service changes were made, and no reboot was performed.

A fresh archive supplies `splunk-launch.conf.default`, so the initial restoration
paused with FileNotFoundError when it expected an initialized launch file. The
error and recovery decision were audited; configuration resumed from the shipped
template without repeating extraction or replacing the preserved old tree.

The ai_sysadmin app is enabled, with exactly three monitor inputs and two
dashboards. Existing log files are root:splunk mode 0640; the containing directory
uses mode 2750, and a temporary file test confirmed future logs inherit a readable
Splunk group. The previously missing logrotate package was installed. Its enabled
daily timer evaluates the configured weekly/52-archive policy; debug validation
passed. No forced log rotation or source-log deletion was performed.

The host inspector now includes systemd auto-restart state, since the earlier
`--failed` check missed the Splunk restart loop. A regression test confirms restart
loops are reported as anomalies and block maintenance. The new app was registered
with the existing guarded Splunk upgrade configuration for branch 9.3; new health
freshness and audit/health ingestion smoke searches both passed. No upgrade
workflow was launched.

Validation results:

- All 32 tests and the complete validator passed.
- Splunk btool validation passed with no diagnostics.
- Exact source-to-index comparison after repeat installation: 151 audit events,
  7 health events, 9 anomaly events. No input duplicates or additional indexed
  copies. One identical historical audit line occurs twice in its source; both
  occurrences are correctly represented. Counts are a verification snapshot.
- Timestamp validation found zero invalid/mismatched event timestamps.
- All 8 AI Sysadmin dashboard queries passed with live results.
- All 14 queries in the restored Server Health dashboard passed.
- The successful CHG-20260913-R2 closure and Splunk outage anomaly are searchable.
- Repeat installation left every integration app file byte-identical. Fresh health
  reporting continued to ingest. No Splunk restart was needed for the repeat check.
- Final host inspection: 75.86% root space free, zero failed/restarting services,
  zero available APT upgrades, no reboot-required flag; dpkg audit clean.
- Splunk was green during ingestion verification, KV Store ready, license OK. PID 10146 remained unchanged after
  startup. NRestarts=706 is the inherited count from the earlier broken service;
  it did not increase during live verification.

Splunk briefly reported yellow Resource Usage/IOWait during verification. Current
vmstat samples showed zero IOWait; the warning was written to the anomaly stream
and was searchable. Splunk returned to green in the final verification. Thresholds
and resource limits were not relaxed.

Evidence: `splunk-live-verification.json`, `splunk-tests.log`,
`splunk-validation.log`, `splunk-restored-dashboard-verification.json`, and
`splunk-license-state.json`. Browser rendering was not separately automated.

## Access and remaining constraints

Use the existing SSH tunnel or:

```sh
ssh -N -L 8000:127.0.0.1:8000 bot@192.168.2.100
```

- [Server Health](https://localhost:8000/en-US/app/ai_sysadmin/health_dashboard)
- [Anomalies](https://localhost:8000/en-US/app/ai_sysadmin/anomaly_dashboard)

Existing admin credentials remain in the private
`/home/bot/splunk/.secrets/splunk-admin.json` file. The local certificate can prompt
a browser certificate notice. No credential values were printed or added to the
repository/audit stream.

Historical indexed data was absent from the incomplete installation and was not
recovered. Existing maintenance JSONL history was fully ingested. The restored
trial is valid for 500 MiB/day through 2026-11-12 12:12:21 UTC; appropriate licensing
is needed beyond the trial. The previously documented 9.3 support exception
remains. These are deployment constraints, not unverified claims of readiness.

Overall closure: integration succeeded; logs, dashboards, repeatability and fresh
reporting verified. An intermittent Splunk IOWait performance finding remains
open, as detailed in the final status update below. The initial
plan, config/CA/permissions backups and final closure are retained under
`/var/lib/ai-sysadmin/splunk-integration-20260913/`; action results are in the audit
stream and are now searchable in Splunk.

## Final status update

The closing remark was confirmed searchable. The subsequent health check returned
red specifically for `Splunk/Resource Usage/IOWait`; all other reported health
components remained green. This supersedes the earlier green snapshot. Details
are in `splunk-final-health.json`. Ingestion, dashboard searches, KV Store, service
stability and source-event matching have passed, but the intermittent disk I/O
performance finding remains unresolved. A high-severity anomaly records this
condition. No health threshold or resource limit was changed to hide it.
