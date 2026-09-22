# Operations, Limits, and Acceptance

## Safety policy

Preserve the existing prohibitions on release upgrades, unclassified/major upgrades, downgrades, package removal, unapproved new products/dependencies, reboots, and autonomous changes to access, users, sudo, network/firewall, disks/filesystems or boot configuration. Registered application release activation and its explicitly permitted service restart are the only added routine mutation workflows. Account/unit creation needed by this framework occurs only in its reviewed installer stage.

IGNORE.md remains strictly parsed, hashed, visible in reporting, and checked for drift before execution. A malformed ignore file is a blocker. No model response, CLI retry rationale or risk label can override a hard denial. Operator authorization for an exceptional action requires a separately designed change; it is not a `--force` switch on routine maintenance.

## Small-model protocol

Use the already configured LiteLLM endpoint and maximum `qwen3.5:9b` model. Verify the actual model identity; do not silently fall back to another model. Preserve authenticated transport and existing credential isolation. Do not install/download models as part of the migration.

Each flow that selects actions gets one short assessment after deterministic policy passes. No-action, report-only and deterministically blocked flows need no AI call. Input includes host health counters, deterministic findings, action counts, summarized version classes, target/evidence IDs and unresolved relevant attention. Full inventories remain in evidence files. Evidence summarization uses typed fields and aggregate counts, never a second AI summarizer; it must not omit blockers or turn missing evidence into a healthy zero.

| Limit | Required value |
| --- | --- |
| Concurrent inference | 1 across this framework, including its shadow invocation |
| Calls per preparation | Maximum 4, one per flow with selected actions |
| Input | Complete prompt text at most 4 KiB UTF-8; reject overflow instead of truncating silently |
| Target runtime context | At least 8,192 tokens available for the bounded request; verify gateway/model configuration before rollout |
| Generated output | Maximum 384 tokens, enforced by the adapter and verified against gateway behavior |
| Accepted response | At most 4 KiB JSON; reasoning at most 600 characters; at most 8 evidence references |
| Request timeout | 120 seconds; no automatic retry |
| Preparation budget | 15 minutes total; service limit 20 minutes |
| AI during maintenance/closure | None |

The token limit is an adapter requirement; acceptance tests must prove the installed gateway/model honors it, including any hidden reasoning output. It is not assumed from an API parameter alone. If the gateway does not enforce the bound, correct the adapter/configuration in isolation before rollout. These are design budgets, not measured performance claims.

Responses contain exactly `proceed` (boolean), `reasoning` (string), and `evidence_ids` (array of known input IDs). Reject additional keys, unknown evidence, malformed JSON, oversized output, negative verdicts, timeouts and gateway errors. Preparation records the failure and becomes blocked. AI cannot output commands, choose artifact URLs/versions, suppress a deterministic finding, or alter a final status. Closure uses a deterministic template with all mandatory action/failure/attention sections.

Benchmark 20 representative requests on the intended hardware: all return valid bounded responses or correctly blocked failure results, and at least 19 complete within 90 seconds. Inject timeout, malformed, oversized and negative responses independently and verify no executable approval is created. Resource failure stops rollout; it does not justify a larger model or unbounded retries.

## Host and action budgets

| Check or action | Limit / behavior |
| --- | --- |
| Required preflight health | No collector errors; zero failed/restarting-loop units; root filesystem at least 15% free |
| Evidence freshness | Host/preflight observations no older than 5 minutes before first mutation; target drift/readiness rechecked immediately before its action |
| Maintenance duration | Final four-flow budget 150 minutes including 10 minutes for final verification/closure; outer service limit 3 hours |
| New action admission | Remaining work budget must cover its registered worst-case duration plus the verification reserve |
| APT refresh / exact install | 30 minutes each, preserving the current configured per-action limit |
| Read-only command | 60 seconds default; APT simulation 180 seconds |
| Docker pull | 15 minutes; readiness 180 seconds by default; preserve tighter/longer reviewed target limits only within the overall budget |
| Manual/pip target | 15 minutes including staging and readiness; an ineligible larger target requires a separate application change |
| Ordinary command log output | 64 KiB per stream retained; record truncation and digest while draining output; never let a pipe block execution |
| Secret output | Hash/redact before persistence; never retain plaintext simply because it fits a size limit |
| Structured collector result | 16 MiB per result; larger inventory must be split into bounded evidence pages with a complete manifest |
| Routine raw evidence/log budget | 2 GiB combined, excluding backups and durable core history; warn at 75%, block new mutations at 90% until reviewed archival restores space |
| Backup admission | Free space after estimated new artifacts/backups must remain above the 15% filesystem floor plus 512 MiB reserve; use explicit per-target backup caps |

Do not start a later action if an earlier action invalidates host health or exceeds its budget. A timeout does not prove a subprocess tree stopped: retain RUNNING and operator review when termination is uncertain. The overall service timeout is a last-resort bound, not the normal way to stop package work.

The final 150-minute budget leaves at most 140 minutes for action groups and intermediate checks. Preparation admission reserves the full registered worst-case times, including APT simulations, backup and readiness, so all four flows can share a change when they fit. During the initial APT-only cutover and compatibility cycles, use a 90-minute total budget with the same 10-minute reserve and retain the legacy two-hour outer service limit. Activate the final budget in Stage 7, before enabling Docker/manual/pip mutations.

Use one root-owned inference lock shared by live and shadow orchestrators so their otherwise separate lifecycle locks cannot overload the model concurrently; waiting for that lock is bounded by the preparation deadline. During coexistence with the legacy planner, run shadow assessments only after the legacy preparation service has ended, because that planner does not implement the new inference lock.

## Observability and event delivery

Keep the four existing streams and sourcetypes. New fields include `implementation=v2`, `schema_version=2`, `component`, `flow`, `phase`, `event_id`, change/run/action identity, outcome, mode and timing. Legacy events remain readable. Global events without a change use an explicit null change ID plus host/run identity.

Maintain the existing health, anomaly and ignored-software dashboards. Add panels for the current change and four flow outcomes, prepared/blocked/expired work, interrupted actions, actual version deltas, deferred targets, reboot-required, component duration, pending outbox count and ingestion lag. Show incidents as open only when explicit resolution correlation exists.

Production searches exclude shadow/dry-run data and deduplicate v2 event IDs. Historical v1 events without IDs retain their existing interpretation; do not deduplicate all missing IDs together. Audit success requires a unique closure event visible in Splunk within 5 minutes of healthy delivery. If that does not occur, record an observability failure without rerunning maintenance or changing the verified application outcome.

Local state/log storage failure blocks further mutation. Splunk outage alone does not prevent a verified local closure while durable local storage is healthy. The operator checks ingestion after each supervised or scheduled acceptance cycle. Normal dashboard access can surface a missed weekly window from stored window metadata; no third maintenance timer or automatic catch-up execution is introduced.

## Retention and storage ownership

Keep records, plans, policy snapshots, action receipts, terminal decisions and imports indefinitely. Keep raw evidence/logs for at least 90 days. Application/container backups require both a 90-day age minimum and the latest three successful versions per target to remain retained. Any unresolved failure or recovery hold overrides age-based eligibility.

No unattended deletion is part of this migration. The operator reviews an exact archive/purge manifest, verifies checksums and readable recovery copies, and authorizes deletion of named eligible files. Existing historical records, current releases, pending outbox data and unresolved evidence are never eligible. Avoid recursive broad-path deletion and never remove a lock inode.

Log rotation uses rename/reopen coordinated with the writer, not copy-and-truncate. Retain rotated segments until their events are accounted for. Keep the existing Splunk index retention/size settings at initial cutover and capture their actual values. Its searchable history can be shorter than a configured time limit because of a size cap; archival records remain the long-term reference.

The operator owns storage management and receives warning/blocker events before capacity exhaustion. Block routine work when safe evidence/backup space is unavailable; do not free space by silently deleting recovery material.

## Operator runbooks to implement

These names specify future CLI behavior; they are not existing commands to execute from this planning directory.

| Operation | Required behavior |
| --- | --- |
| `status` | Show ownership mode, current window/change, record status and phase, active action processes, flow results, last verified closure, storage and delivery lag; read-only |
| `prepare` / `maintain` | Invoked through the reviewed service path; lock and all schema/window/policy checks apply |
| `reconcile` | Repair only missing/known-stale committed projections and replay outbox events; never run a maintenance action |
| `cancel --change-id ... --reason ...` | Operator-only PREPARED→FAILED with no action started; preserve immutable plan and add cancellation closure |
| `recover --change-id ... --reason ...` | Operator-authorized read-only diagnosis of interrupted work, prove process termination, then finalize FAILED with observed facts |
| `prepare --retry-of ... --reason ...` | Only a reviewed FAILED parent; new inspection/approval and one stable successor; no history reopening |
| Emergency scheduling disablement | Stop/disable both new timers; let active commands finish; inspect active process and lifecycle state |
| Restore application | Separate reviewed recovery action using retained artifacts and data-compatibility evidence; record and verify outcome |
| Restore observability | Verify monitored paths/permissions/app assets, reconcile outbox, search by event ID; do not reproduce logs by repeating maintenance |

Document exit codes: `0` complete/no-op; `1` failed or interrupted work requiring review; `2` policy/assessment/window refusal with no further mutation; `3` invalid configuration/artifact/usage; `75` lock contention. Bookkeeping/delivery failures return nonzero with the committed lifecycle status unchanged and a separate error category. Never use an exit code alone as proof of application success.

## Acceptance matrix

All tests run against fixtures or disposable VM targets unless explicitly labeled as supervised production observation. Do not manufacture failures on the production host.

| Area | Evidence required |
| --- | --- |
| Baseline | Captured dirty-source/deployment manifests, sanitized artifacts, passing legacy suite and controlled full validation |
| Extraction | Byte-equivalent artifacts and equal decisions under frozen time/identity/AI fixtures; no undeclared behavior changes |
| Four flows | Separate inventory/proposal/verification outputs for APT, manual, Docker and pip; no target has two mutation owners |
| APT | Safe/security update, no-update, refused removal/new dependency/major/downgrade, changed exact transaction, contention and wrong installed version |
| Docker | Pinned image, backup before replacement, wrong digest, shared-data rejection, drift, readiness failure, original-service recovery before replacement |
| Manual | Valid signed/reviewed artifact, traversal/bomb/unsafe-file rejection, same-series update, unsupported installer deferral, exact release activation and operator recovery |
| pip | Complete hashed wheel set, no new distribution names, source-build rejection, externally-managed Python unchanged, final-path venv, dependency/ABI checks and activation failure |
| Whole change | APT success followed by Docker failure leaves later actions unexecuted and one FAILED closure; expected manual/pip deltas accepted, unrelated deltas rejected |
| AI | Valid/negative/malformed/timeout/oversize responses, prompt injection as untrusted data, bounded sequential requests and the 20-request hardware benchmark |
| State | Every allowed/forbidden transition, PREPARED preflight, RUNNING verification, repeated terminal no-op, cancellation, explicit successor idempotency |
| Durability | Fault after each journal commit, file flush/replace, action intent/result, terminal commit and outbox append; power-loss tests on disposable VM snapshots |
| Projection recovery | Missing/known-stale files reconstructed, unexpected edits blocked, interrupted actions never replayed, duplicated event IDs counted once |
| Lock/processes | Old/new contention, controller termination, surviving command descendants, active action detection and no second executor admission |
| Isolation | Dry-run/shadow path alias/symlink attacks rejected; zero changes to live package/cache/service/container/application state |
| Privileges/secrets | Restricted collector and staging profiles, credential redaction, fixed commands, no AI filesystem/command capability |
| Schedule | Both legacy timers disabled at canary; weekly day-before mapping, 48-hour expiry, 30-minute start rule, DST and missed-run behavior |
| Splunk | Existing dashboards still work, four flow panels work, closure visible within 5 minutes when healthy, outage recovery without maintenance replay |
| Rollback | Pre-action cutover backout and post-action operator recovery rehearsed; old state snapshot never overwrites new history |
| Final observation | Three shadow pairs, supervised APT canary, two legacy-cadence v2 cycles, each applicable handler canary, four final weekly cycles |

The migration is accepted only when every applicable row has linked evidence and unsupported/no-target cases are explicitly recorded. Runtime measurements and operator execution receipts are future evidence requirements, not unresolved architecture choices.
