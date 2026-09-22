# Decisions

These decisions replace the open choices in `../07-reuse-map-and-decisions.md` and resolve the six review findings in `../FUTURE_REFERENCE.md`. Changes to them require a documented revision with affected tests and rollout steps; they are not runtime choices for an AI.

## Previously open questions

| ID | Question | Decision and reason |
| --- | --- | --- |
| D01 | Cadence | Final cadence is weekly: Saturday preparation at 20:00 and Sunday maintenance at 20:00, Europe/Copenhagen. This follows the governing weekly requirement. Preserve the measured legacy cadence during framework cutover, then change schedule separately. |
| D02 | Names | Source: `/home/bot/ai-sysadmin-multi-agent`. Install: `/opt/ai-sysadmin-multi-agent`. Config: `/etc/ai-sysadmin-multi-agent`. Units: `ai-sysadmin-v2-prepare` and `ai-sysadmin-v2-maintenance`, each with `.service` and `.timer`. The CLI remains named `ai-sysadmin` inside the new installation. |
| D03 | Artifact compatibility | Keep production state/log roots and the existing `changes/<id>.txt`, `<id>.plan.json`, `current-change`, and `controller.lock` locations. Add `lifecycle.sqlite3`, evidence, and receipt subdirectories. Import terminal history without rewriting it; never consume a legacy PREPARED plan with v2. |
| D04 | AI roles | Use AI only for preparation assessments of flows that propose changes. No closure AI. All policy, command construction, verification, and closure are deterministic. This limits model load and makes failure reporting independent of AI availability. |
| D05 | Approval | Registered routine actions proceed automatically when deterministic policy and every required preparation assessment pass. First registration of a target, cutover, retry, recovery, and changes outside the catalogue require an explicit operator action. AI labels never grant additional authority. |
| D06 | Privileges | Retain the root lifecycle oneshot and in-process executor at initial cutover. Before enabling new manual/pip handlers, apply the specified restricted collector/AI subprocess profiles and unprivileged staging. The orchestrator retains root for compatibility and bookkeeping; application mutation exists only in the executor module. This is a code boundary, not a claim that root is technically incapable of other writes. |
| D07 | Splunk schema | Preserve `ai_sysadmin:audit`, `ai_sysadmin:health`, `ai_sysadmin:anomaly`, and `ai_sysadmin:ignored`. Add implementation, component, phase, flow, schema version, and stable event IDs. Update aggregations to deduplicate event IDs; no new production index is introduced. |
| D08 | Retention | Keep records, plans, policy snapshots, receipts, and decision history indefinitely. Raw evidence and local logs become eligible for operator-approved archival after 90 days. Keep successful application/container backups for at least 90 days and at least the last three successful versions per target; retain unresolved failure evidence/backups indefinitely. Preserve the current Splunk index limits at cutover; do not promise a full year of searchable data under a size cap. No unattended purge. |
| D09 | Plan lifetime | Keep a 48-hour maximum age, additionally bind execution to a named maintenance window and the 30-minute start allowance. Age alone never authorizes execution outside the window. |
| D10 | Container scope | All four flows inspect from the first canary. Only APT mutates in that first canary. Carry reviewed Docker registrations forward as disabled entries, then enable them after the dedicated Docker canary. Container enablement is a required migration stage. |
| D11 | Observation | Three consecutive shadow preparation/maintenance pairs; one supervised APT canary; two successful scheduled v2 cycles at legacy cadence; then weekly cadence. Each new handler needs an isolated success/failure/repeat-run test and one supervised production canary when an eligible target exists. Finish with four successful consecutive weekly cycles. |
| D12 | Operator ownership | The requesting host owner is the accountable operator and cutover approver. Record the authenticated operating-system identity for each privileged CLI action. Delegation uses an explicit named operator entry in configuration; no additional operator is assumed and no account is created by this plan. |

## Additional decisions

| ID | Topic | Decision |
| --- | --- | --- |
| D13 | n8n | Use systemd, not n8n, for this migration. The problem is local host maintenance with existing Python safety code, durable state, and privilege controls. n8n's visual workflow capability is useful, but embedding the same host policy/executor behind it would leave those components necessary and add a workflow runtime to operate. The supplied drawing addresses flow visibility without that dependency. This is an architectural judgment, not a claim that n8n cannot implement the workflow. |
| D14 | Component model | Four deterministic flow modules, a bounded assessment adapter, and shared lifecycle services in one repository. No agent framework, message broker, distributed scheduler, or autonomous command-generating agent. |
| D15 | APT authorization | Preserve current bounded-policy semantics: preparation records observed candidates as indicative; maintenance refreshes metadata and then constructs a fresh, safety-checked exact transaction. Exact versions and its digest are committed to a separate execution manifest before installation. Do not pretend preparation pinned the final APT versions. |
| D16 | Other target versions | Docker digests, manual artifacts, and pip lock manifests are exact at preparation. Any relevant identity, configuration, version, or artifact drift blocks execution; it does not trigger automatic replanning. |
| D17 | State | Four persisted record statuses only. Inspection, assessment, preflight, execution, verification, and finalization are phases. Verification after mutation retains RUNNING until a terminal transaction commits. |
| D18 | Durability | SQLite via Python's standard library, local filesystem, `journal_mode=DELETE`, `synchronous=EXTRA`, foreign keys enabled, one writer under the lifecycle lock. A terminal transaction commits record content, receipts, current pointer, and outbox events together. |
| D19 | Update order | APT → Docker → manual software → pip. Verify each action before starting the next. Any selected action failure stops all subsequent mutations and makes the combined change FAILED. |
| D20 | Registration | Discovery grants no mutation authority. A root-owned target registration selects a code-owned handler, approved locations/artifact sources, version rules, service identity, restart permission, readiness check, and recovery limits. Unknown installations are report-only. |
| D21 | Manual software | Implement a handler for registered relocatable vendor archives/binaries installed as versioned releases. Splunk, the AI gateway/model runtime, the controller itself, software with database migrations, and arbitrary installer scripts remain report-only and require a separate product-specific change. |
| D22 | pip | Manage registered application virtual environments through exact wheel manifests and a new versioned environment. Do not modify system Python, use `--break-system-packages`, run source builds, upgrade the interpreter, or add/remove distribution names during routine maintenance. |
| D23 | Recovery | No automatic retry or package downgrade. Manual/pip release reactivation is a documented operator recovery action, allowed only when application data compatibility is verified. Docker preserves the existing pre-replacement recovery of the original service when backup fails; after replacement there is no automatic database/image rollback. |
| D24 | Missed runs | Final weekly timers use `Persistent=false`, `RandomizedDelaySec=0`, `AccuracySec=1min`. A missed window is reported, not executed on reboot. Final scheduling checks are introduced with the separate weekly schedule change. |
| D25 | AI limits | `qwen3.5:9b` maximum; one call at a time, at most four calls per preparation, no automatic retry. Each complete prompt is at most 4 KiB UTF-8; generated output at most 384 tokens and accepted JSON at most 4 KiB; 120-second request limit. No AI calls in maintenance. |
| D26 | Runtime dependencies | Use the host's supported Python 3.11+ and standard library for orchestration. Reuse APT, dpkg, systemd, Docker/Compose/Buildx, Splunk, and LiteLLM. Pin `packaging` for the pip handler's version/specifier parsing in the controller's private runtime environment provisioned by the installer. Pin test tooling in development only. Do not upgrade production dependencies as an incidental refactor step. |
| D27 | Success with deferred work | Items deferred before action selection are reported as attention items and do not masquerade as completed updates. A change may close CLOSED if every selected action verifies and host health passes. A missing required collector or a failed selected action prevents CLOSED. |
| D28 | Execution budget | APT-only canary/compatibility: 90 minutes total, two-hour service cap. Final four-flow operation: 150 minutes total, three-hour service cap, activated in Stage 7. Both reserve 10 minutes for final verification and admit only complete action groups that fit. Two consecutive capacity deferrals require a separately scheduled application change. |

n8n is documented as a workflow automation platform with self-hosting options in its [official overview](https://docs.n8n.io/). No assumption that every n8n deployment requires Redis or a separate database underlies D13.

SQLite documents the additional directory synchronization provided by `synchronous=EXTRA` with DELETE journaling in its [synchronous pragma reference](https://www.sqlite.org/pragma.html#pragma_synchronous). This is why D18 selects EXTRA rather than relying on individual file replacements alone.

## Review finding resolution map

| Review finding | Resolution |
| --- | --- |
| Missing software flows | D14, D19–D22; complete contracts in [software flows](SOFTWARE_FLOWS.md) |
| Old preparation timer during cutover | Both legacy timers explicitly stopped/disabled and active services drained in [migration](MIGRATION.md) |
| State and recovery contradictions | D17 and the state/recovery tables in [lifecycle](LIFECYCLE.md) |
| Unachievable parity | D03, D15–D16; extraction parity separated from v2 behavior changes in [migration](MIGRATION.md) |
| Partial finalization after crash | D18 and transactional outbox/projection recovery in [lifecycle](LIFECYCLE.md) |
| Model budget, orchestration, drawing | D13, D25; [architecture](ARCHITECTURE.md), [operations](OPERATIONS.md), and [flow drawing](flow.svg) |
