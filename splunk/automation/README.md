# Codex Splunk upgrades

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


This installation uses a **systemd timer → Python controller → Codex decision → guarded executor → Codex validation → Splunk report** workflow. n8n is unnecessary for this single Ubuntu host. Codex selects an eligible upgrade and evaluates the validation evidence; fixed Python procedures perform privileged operations. The model cannot supply arbitrary installation commands or override compatibility gates.

The timer checks daily at **03:00 UTC**, with up to 15 minutes of jitter. It catches up after downtime. Compatible upgrades are authorized to proceed without another maintenance-window approval. A lock prevents overlapping runs. At most one eligible package is upgraded per run, allowing each intermediate installation to be validated.

## Deployment verification — 2026-09-13

The systemd service and timer are installed and enabled. The daily check runs at 03:00 UTC plus up to 15 minutes of jitter. Sixteen automated tests and systemd unit validation pass. Live inventory, release discovery, Codex review, and report ingestion have been exercised on this host.

The live check retained Splunk 9.3.14: the VM lacks AVX required for newer branches. Python Upgrade Readiness 4.7.0 is an end-of-life placeholder and its official release metadata rejects standalone installation; the bundled 4.6.2 is retained. The first check reported red Resource Usage/IOWait health; it recovered before the systemd run, whose full health validation passed. KV Store, license, configuration, ingestion, and the 14 dashboard queries passed. The systemd run exited successfully and its two compatibility errors were confirmed searchable with at most two message lines each; the report outbox is empty. These are observed results, not a guarantee of future health.

Health reports identify the unhealthy feature, and recovery reports preserve individual validation errors. Each error remains at most two message lines. No live upgrade or restore drill was performed because no eligible update was available.

## Current installation policy

- Splunk Enterprise 9.3.14, `/opt/splunk`, standalone `Splunkd`, Ubuntu 24.04, localhost HTTPS management API.
- This VM lacks AVX. Splunk 9.4+ requires CPU features this VM does not expose. KV Store must remain enabled and ready; there is no workaround that disables it.
- Automatic platform upgrades are limited to newer stable **9.3 patches**. Discovery checks both current and archived official download pages; newer branches are reported as blocked. Changing the branch setting alone does not authorize a cross-branch migration.
- The 9.3 installation is an existing, locally validated exception; it is past its vendor support lifecycle. This workflow does not make the existing OS/platform combination vendor-supported.
- Vendor manifest membership identifies bundled apps. These update with the platform. Separately published bundled-app releases are also checked on Splunkbase and reported if they need independent qualification.
- `server_health` is a local app, qualified for 9.3 through its ingestion checks and 14 live dashboard queries. It has no upstream release feed. `splunk_ingest_actions` is a generated metadata-only directory in this installation.
- Unknown apps, including disabled apps, block upgrades until their source, dependencies, and tests are mapped. Do not infer compatibility from an app's author or its name.

## Upgrade and recovery

1. Read live platform, app, license, CPU, topology, and storage inventory. Discover release metadata over verified HTTPS. An unavailable source or unknown response format is an error, never “up to date.”
2. Validate the running service, `btool check`, health, KV Store, license, metrics/journal ingestion and all 14 dashboard queries. App-specific configured searches must explicitly return `pass=1`.
3. Enforce exact app-release platform compatibility, dependency constraints, local app branch policy, same-branch platform policy and simple app-install requirements. Codex reviews this evidence and release notes. Unknown compatibility means hold.
4. Download the exact selected package, validate archive paths and package version metadata, and verify the vendor SHA-512 for platform installers. App packages use authenticated TLS provenance and a locally recorded SHA-512; a local digest is not claimed to be a vendor signature. A Splunkbase download requiring login will fail closed on this installation, which has no Splunkbase credential configured.
5. Stop **only Splunkd**, create a full cold archive of `/opt/splunk`, compare the archive with the stopped source, record its checksum, and restart Splunk. The archive includes indexes, KV Store, credentials and configuration; it is root-private. Save the systemd unit and drop-ins alongside it. External index paths and clusters are rejected by this adapter.
6. Confirm inventory has not changed. Apply the selected upgrade, restart through the existing systemd service, wait for KV Store, and observe two minutes of ingestion. Preserve the existing THP/resource configuration. Platform startup uses noninteractive migration/license flags.
7. Check expected versions and app enabled/disabled states, repeat validation, and check new error-producing components in `_internal`. Codex must explicitly validate the evidence before success is recorded.
8. On failure, restore the **whole pre-upgrade instance**, including data and KV Store, and validate it. This is full snapshot recovery, not an in-place binary downgrade. Retain the failed tree as `/opt/splunk-failed-<run_id>`. Latch the transaction for investigation instead of retrying a failing release every day.

Backups live at `/var/backups/splunk-upgrade/<run_id>/`. They are on this server's disk: they protect against upgrade failure, **not loss of this server or disk**. An off-host/VM snapshot adapter can be added later. Backup and failed-tree retention is deliberately manual; insufficient free space blocks further upgrades rather than deleting recovery evidence. A rollback restores data to the backup point, so events received during a failed upgrade's validation period may need replay from their original sources.

The transaction file is written and flushed before mutation. `ExecStopPost` and the next run attempt recovery after interrupted backup/installation phases. An interrupted or failed restore remains latched for manual inspection. Post-upgrade checks cover this installation's configured functions; a new workload requires its own meaningful validation.

## Splunk reports

Reports use the existing authenticated localhost management receiver; no inbound port or HEC service is added. Each error is one JSON event with **at most two display lines in `message`**. If there are no errors there is only one brief status event. Detailed evidence and Codex transcripts stay in the private `state/` directory.

```spl
index=main sourcetype="splunk:upgrade:json" source="codex_upgrade"
| spath
| dedup event_id
| table _time status code message
| sort - _time
```

Reports are written to a durable local outbox before delivery. The controller verifies that each event is searchable before removing it from the outbox. If Splunk is unavailable, reports remain queued and are retried on the next run or with `flush`. Delivery is at least once: use `dedup event_id` because a crash after ingestion but before acknowledgment can cause a duplicate. Platform outages cannot be reported inside Splunk until Splunk recovers; the systemd journal records delivery failures in the meantime.

## Operations

```sh
# Live check and reporting, without upgrading
python3 /home/bot/splunk/automation/upgrade.py check

# Run the authorized workflow now
sudo systemctl start splunk-upgrade.service

# Scheduler and execution status
systemctl list-timers splunk-upgrade.timer
journalctl -u splunk-upgrade.service -n 30 --no-pager

# Retry reports without running Codex or changing Splunk
python3 /home/bot/splunk/automation/upgrade.py flush

# Disable future scheduling (does not interrupt an in-flight transaction)
sudo systemctl disable --now splunk-upgrade.timer

# Tests; no Splunk mutation
python3 -m unittest discover -s /home/bot/splunk/automation/tests -v
```

`check` does not install packages, but it still performs recovery for a previously interrupted transaction, runs validation, invokes Codex, and writes its report. Do not run the low-level `recover` command concurrently with a live upgrade; systemd calls it after the service process has exited.

After a rollback or interrupted transaction, inspect `state/transaction.json`, the referenced run evidence, backup and retained failed tree. Confirm the restored expected version and successful validation before archiving/removing the latch. Investigate why the target failed before allowing it to be attempted again. No automatic latch-clear command is provided.

Codex uses the installed CLI and the `bot` account's existing authentication/model configuration. Shell, app/plugin, browser, computer, image, and delegation features are disabled for decision calls; review evidence contains no Splunk passwords or raw event samples. Expired Codex authentication, invalid output, timeouts or unavailable network access block installation and generate an error. The controller uses the account's already-existing sudo rights; installation grants no new sudo policy.

## Adding apps or moving environments

Environment settings are in `config.json`. A Splunkbase-managed app requires an exact app ID, documented dependency constraints, an explicit dependency review, and meaningful smoke searches:

```json
{
  "id": 12345,
  "dependencies_reviewed": true,
  "dependencies": {"dependent_app": ["1.2.3"]},
  "smoke_searches": [{
    "name": "app_data_is_current",
    "query": "search index=APP_INDEX earliest=-10m | stats latest(_time) as latest | eval pass=if(isnotnull(latest) AND now()-latest<300,1,0)",
    "pass_field": "pass"
  }]
}
```

The ID/index/query above are illustrative and must be replaced with the actual app and workload. Map the rule under the installed app directory name in `splunkbase_apps`. Changes to app dependencies or migrations require a new review, not just a version bump. Premium apps and complex install methods need their own adapter.

The v1 privileged adapter intentionally checks `/opt/splunk`, `Splunkd`, the `splunk` account and the local backup directory. Arbitrary hosts, remote TLS identity/authentication, off-host backups, external volumes, indexer clusters, search-head clusters and cross-branch migrations require additional qualified adapters. Paths and policy are separated now to support that later work; this version does not claim arbitrary-environment support.

## Sources and validation limits

- [Codex noninteractive execution and structured outputs](https://learn.chatgpt.com/docs/non-interactive-mode)
- [Official archived Splunk releases](https://www.splunk.com/en_us/download/previous-releases.html)
- [Current Splunk Enterprise download](https://www.splunk.com/en_us/download/splunk-enterprise.html)
- [Splunk 10.4 upgrade requirements, app compatibility and CPU requirements](https://help.splunk.com/en/splunk-enterprise/administer/install-and-upgrade/10.4/upgrade-or-migrate-splunk-enterprise/about-upgrading-to-10.4-read-this-first)
- [Splunk app installation REST API](https://help.splunk.com/en/splunk-enterprise/leverage-rest-apis/rest-api-reference/9.2/application-endpoints/application-endpoint-descriptions)
- [Splunk input/receiver REST API](https://help.splunk.com/en/splunk-enterprise/rest-api-reference/10.4/input-endpoints/input-endpoint-descriptions)

Automated tests exercise compatibility gates, package rejection, outbox retention and simulated backup/rollback failures. Live verification covers discovery, Codex decisions, the installed validation searches and report indexing. No actual platform upgrade or destructive recovery drill has been performed because no newer qualified platform release is available for this CPU.
