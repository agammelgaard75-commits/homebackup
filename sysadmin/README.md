# Local AI Sysadmin

This repository implements a conservative daily maintenance lifecycle for an
Ubuntu VM:

1. A preparation timer runs the day before maintenance. It inspects the host,
   creates an ITIL-style change record, and records the planned actions.
2. A maintenance timer updates package indexes, applies safe package upgrades,
   verifies the host, and closes the change record.
3. Every decision and command is appended as JSON Lines for Splunk ingestion.

The executor has a fixed action catalogue. Planning output can select approved
actions, but it cannot provide shell commands. The workflow never reboots,
never performs release upgrades, and never runs destructive package cleanup.

## Validate and install

```bash
./scripts/validate.sh
sudo ./scripts/install.sh
```

The installer copies the program and systemd units, creates state directories,
and reloads systemd. It deliberately does not enable or start the timers.
After reviewing the generated installation, enable scheduling explicitly:

```bash
sudo systemctl enable --now ai-sysadmin-prepare.timer ai-sysadmin-maintenance.timer
systemctl list-timers 'ai-sysadmin-*'
```

For a manual lifecycle test that only inspects the host:

```bash
sudo /opt/ai-sysadmin/bin/ai-sysadmin prepare
```

Run maintenance for the prepared change with:

```bash
sudo /opt/ai-sysadmin/bin/ai-sysadmin maintain
```

## Files and audit data

- Configuration: `/etc/ai-sysadmin/config.toml`
- Change records: `/var/lib/ai-sysadmin/changes/`
- Current prepared change: `/var/lib/ai-sysadmin/current-change`
- Audit events for Splunk: `/var/log/ai-sysadmin/audit.jsonl`
- Health events for Splunk: `/var/log/ai-sysadmin/health.jsonl`
- Anomaly events for Splunk: `/var/log/ai-sysadmin/anomalies.jsonl`
- Accepted software exceptions: `/etc/ai-sysadmin/IGNORE.md`
- Ignored-software events for Splunk: `/var/log/ai-sysadmin/ignored.jsonl`

The Splunk dashboard XML and deployment notes are in `splunk/`.

`IGNORE.md` accepts one strict Markdown bullet per exception: `- software-name:
reason`. Names are case-insensitive and match APT package names (without an
architecture suffix), discovered software names, and configured container names.
Ignored software is inventoried but omitted from automatic updates. Each entry,
including entries not currently detected, is written to its own Splunk log and
shown in the Ignored Software dashboard. Changing the file after preparation
blocks execution so the approved change and executed policy cannot diverge.

## Readiness and integration configuration

`READY_FOR_PROD` records the verified deployment as of 2026-09-13. A real
AI-approved maintenance run completed successfully and both installed services
passed a repeat-run check without changing the closed artifacts. Daily timers run maintenance at 20:00 Europe/Copenhagen and preparation at 23:00 for the following evening, with automatic daylight saving adjustment and no random delay. Local Splunk integration is enabled and verified: audit, health and anomaly logs
are searchable in `index=ai_sysadmin`, with separate health and anomaly dashboards.
See `splunk/README.md` for access and verification.

The supplied planner adapter uses authenticated LiteLLM at `ai.base_url`
(currently `http://127.0.0.1:4000/v1`) with model `qwen3.5:9b`.
It follows the [LiteLLM gateway API](https://docs.litellm.ai/).
The key is read from `LITELLM_API_KEY` or `ai.api_key_file`; it is never stored
in tracked configuration. The installer provisions an absent production key
from the ignored `.secrets/litellm.key` file with mode 0600. Alternatively set
`ai.command` to a trusted executable argv list: it receives JSON on stdin and
must return `{"proceed": true, "reasoning": "assessment"}` on stdout within
`ai.timeout_seconds` (660 in the supplied configuration). The adapter receives the selected config
path through `AI_SYSADMIN_CONFIG`.
No model-supplied commands are executed. Missing, invalid, or negative assessments
block maintenance. `ai.required=false` is available for explicit rules-only use.
No model download is performed by the installer.

The installer generates timers from `[schedule]`, enforcing preparation one day
before maintenance. Re-run the installer after schedule changes. If service
restarts are prohibited, package upgrades are blocked because package scripts
may restart services. Software outside APT is inventoried and reported for review;
automated updates cover APT packages and explicitly configured Compose services.

Change plans are immutable after preparation. Closed or failed changes are never
automatically re-executed. Failed/interrupted runs require operator review; prepare
a separate change after remediation, preserving the old artifacts. Plans expire
after 48 hours. A fresh health check gates execution, and unhealthy verification
fails the change. `--dry-run` writes plans, change records, pointers and locks
under `<state_dir>/dry-run/` and logs under `<log_dir>/dry-run/`. It never consumes
or closes a live change, even with the same configuration. Run both `prepare`
and `maintain` with `--dry-run` for a simulated lifecycle. These separate logs
are not monitored by the production Splunk inputs; all events carry `dry_run`.
The validator additionally uses temporary directories.

Package update and upgrade failures emit high-severity anomaly events with the
action, return code, change ID and run ID. Change status is read only from the
single status field in the record header; notes cannot override it. Invalid or
duplicate header fields stop execution and preserve the record for review.

Splunk app installation is enabled through `splunk.install_app=true`.
The installer deploys a dedicated
`ai_sysadmin` Splunk app when `splunk.home` contains Splunk.
Activate it through your normal Splunk reload procedure and
verify events and dashboards before enabling timers. The installer does not
restart Splunk or enable maintenance timers.

## Software inventory and upgrade safety

Every fresh preparation, preflight and postflight records installed APT package
versions, checks `dpkg --audit`, reads Splunk version manifests and Python package
metadata under `/opt` and `/usr/local`, and lists Snap/system Flatpak applications
when those managers are available. Optional `[inventory] roots` configures the
directories whose immediate installation subdirectories are inspected. Python
metadata discovery covers installations and virtual environments one level below
those directories. It does not import or run discovered applications. Unknown
nonempty directories/local executables are recorded with version `unknown` and
reported for identification. Per-user environments, packages within container filesystems and arbitrary
installation locations are not exhaustively scanned. Archived installations can
appear alongside active ones; the location identifies which was inspected.

Full inventory goes into the change record and JSON audit/health logs; individual
extra-software events feed the Server Health dashboard. The planner receives a
bounded summary, prioritizing Splunk and LiteLLM. Version conflicts between the
configured Splunk installation and the package database are reported separately,
and an APT update targeting that conflicting package is refused.

Before upgrades, the executor simulates the refreshed package transaction and
rejects removals, new installations, downgrades, epoch changes, and major or
unclassified upstream version changes. Classification conservatively compares the
leading numeric component of dotted upstream versions; unchanged upstream versions
with distro/security revision updates also qualify. Nonstandard version schemes
require review when their upstream version changes. A rejected transaction stops
the package upgrade as a whole; no persistent package holds are added. The checked
package versions are pinned and the resulting dependency transaction simulated
again before execution. Normal permitted APT updates include security revisions.

Postflight checks actual installed versions against the intended versions and
records before/after package changes. Missing packages, dpkg problems, unexpected
extra-software changes, or unhealthy host checks fail the change even if the update
command returned zero. Dry runs record simulation results without claiming that
package versions changed. Closure lists changes and outstanding review items.

The executor does not perform release upgrades or modify SSH, firewall, network,
users, sudo, storage, or boot configuration directly. Normal permitted package
updates can run their standard maintainer scripts and restart services.

APT option behavior follows the [Ubuntu APT manual](https://manpages.ubuntu.com/manpages/noble/man8/apt-get.8.html);
version parsing follows the [Debian version format](https://www.debian.org/doc/debian-policy/ch-controlfields.html#version).

## Weekly container image maintenance

Container applications are updated by replacing their images; the framework does
not run package managers inside running containers. Docker Engine/CLI/containerd
remain managed through APT and respect APT holds independently of image policy.

Enable `[containers] enabled = true` and add one `[[containers.services]]` policy
per reviewed, single-instance Compose service. Unlisted containers are inventoried
and reported but not changed. See the commented policy in `config/config.toml`.
The installed configuration enables n8n with its existing Compose deployment.
Set `hold = true` on a service to freeze its image; this is checked again at
execution, so a newly added hold invalidates an older prepared update.

During preparation the framework inventories image IDs, digests, application
version labels, Compose ownership, mounts and health. It queries the configured
registry tag without downloading layers, resolves the host-platform digest, and
records that exact candidate in the immutable change plan before AI assessment.
It refuses application major upgrades, downgrades and unrecognized versions. When
present, the Docker Hardened Images dependency version is also checked; a Node.js
24-to-26 transition is deferred even when the application stays on major version 2.
A tag such as `latest` is only a discovery channel; execution uses the prepared
digest. Identical image IDs produce no update or restart.

Maintenance rechecks policy and deployment fingerprints, pulls the exact image,
and verifies its ID/labels. It stops only the configured service for a consistent
snapshot of its writable bind/volume mounts, reads back and checksums each archive,
then recreates only that service with `--no-deps --no-build --pull never`. It does
not run `compose down`, remove volumes, prune images or alter network definitions.
Shared writable mounts, missing health checks, drift, unavailable metadata and
unsupported deployments defer updates. APT failure stops subsequent image updates.

After replacement, the exact image, unchanged mounts and stable process/health
state are verified. An optional loopback readiness URL must return HTTP 200; n8n
uses `/healthz/readiness`. The successful digest is saved in
`/var/lib/ai-sysadmin/containers/<name>/image.json`. Future runs include this override
and reuse the container if already current. To run Compose manually without
losing the managed image selection, include the same override after your original
Compose files. Configuration changes outside the framework require review before
automatic updates resume.

Backups live under `containers/<name>/backups/<change-id>/` with private permissions.
They contain mount archives, their checksums, the original rendered configuration,
old/new image references and results. Each mount has a bounded backup size (default
1 GiB); disk headroom is checked before stopping. Backups are retained without
automatic deletion. If backup fails before replacement, the original container is
started and checked. After replacement failure, the change fails and backups are
preserved for operator recovery. There is no blind image/database rollback because
application migrations may make a downgrade unsafe. Review the saved configuration,
stop the affected service, restore the appropriate data backup and old image as one
coordinated recovery change. These backups do not undo external workflow effects.

Full rendered Compose output may contain credentials: it is never sent to the AI
or ordinary audit logs. Sensitive command output is recorded by hash; the backup
copy is mode 0600. Scheduled services get read-only access only to configured
Compose directories inside their home-directory sandbox. Docker CLI state lives
under the controller state directory. Re-run the installer after changing Compose
file locations so the generated service drop-ins match the configuration.

Preview inventory, candidates and reasons for deferral without pulling or restarting:

```bash
sudo /opt/ai-sysadmin/bin/ai-sysadmin containers
```

Exit 2 means a finding/deferred update needs review. Ordinary `prepare` and
`maintain` include container work automatically on the existing weekly schedule.
The health dashboard shows container inventory; deferrals/failures appear separately
in the anomaly dashboard, and closure records image results and backup paths.

References: [Docker image metadata](https://docs.docker.com/reference/cli/docker/buildx/imagetools/inspect/),
[Compose configuration](https://docs.docker.com/reference/cli/docker/compose/config/),
and [Compose service replacement](https://docs.docker.com/reference/cli/docker/compose/up/).

## Recover a failed change

Preparation now reports failed or incomplete existing changes instead of silently
returning success. After reviewing and fixing the recorded blocker, prepare an
explicit successor (including on the same day):

```bash
sudo /opt/ai-sysadmin/bin/ai-sysadmin prepare --retry-of CHG-20260913 --reason 'Reviewed failure and corrected the network readiness check'
sudo systemctl start ai-sysadmin-maintenance.service
sudo journalctl -u ai-sysadmin-maintenance.service -n 50 --no-pager
```

This produces `CHG-20260913-R1`, preserving the original record and any remaining
plan. Repeating the same retry command reuses that successor; it does not create
another attempt. If that successor fails, review it before explicitly retrying
its ID. A RUNNING change still requires investigation before any recovery; never
remove locks or kill package processes to force a retry.

`prepare` manages `/var/lib/ai-sysadmin/current-change` automatically; it contains
only a change ID, not the change record. A missing, empty, or whitespace-only
pointer is recovered from change history. An intact, unexpired PREPARED plan can
restore the pointer without replanning. If today's latest change is CLOSED,
`prepare` restores its reference and reports that no further action is needed;
clearing the pointer does not start another maintenance run. With no change for
today, preparation creates one normally. Nonempty malformed pointers, invalid
records, and interrupted RUNNING changes still require operator review.
Missing or invalid plans are refused. Inspection and planner progress is printed
to stderr and captured by the systemd journal, as well as the JSON audit log.
