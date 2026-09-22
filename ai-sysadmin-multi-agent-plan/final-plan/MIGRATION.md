# Implementation, Cutover, and Rollback

Implement in the new repository selected in D02. Preserve the parent planning files and the existing `/home/bot/sysadmin` working tree. Every stage below has a defined exit gate; completing a design stage does not itself deploy services or activate a schedule.

## Stage 0 — capture the actual baseline

Capture source revision plus a manifest of local changes, deployed controller/module hashes, redacted effective configuration, IGNORE.md, installed executable versions, service/drop-in definitions, timer enable/active states and next runs, legacy state/log paths, existing Splunk app assets and searches, and configured Docker/manual/pip targets. Record that a repository example is not evidence of a live registration.

Archive sanitized PREPARED, CLOSED, FAILED, expired, tampered, retry and missing-pointer fixtures. Obtain a consistent backup of production records/configuration and prove it can be read back in an isolated VM. Do not copy secrets into fixtures or this repository.

Run existing tests from an isolated copy containing the captured source changes. Run the complete validation workflow only in the controlled validation environment, since its dry-run path can invoke configured collectors and the AI adapter. Establish gateway/model identity and test performance without changing the model or downloading a replacement.

**Exit:** A timestamped manifest, reproducible baseline tests, known deployed configuration, and a successful isolated no-change repeat run. Measured facts fill the deployment manifest; none are guessed to make a gate pass.

## Stage 1 — extract without changing behavior

Extract the current collector, policy, APT, Docker, writer, verifier, event and CLI code behind internal interfaces. Keep the executor in-process. Freeze time, run identity, command results and AI output in fixtures so byte-level comparisons are meaningful.

| Existing code | Extraction owner |
| --- | --- |
| `Controller.inspect`, `software_inventory` | Host collector and four flow inventories |
| `Controller.blockers`, ignore-file parser | Global/flow policy |
| `Controller.plan`, `scripts/litellm_planner.py` | Trusted plan builder and assessment adapter |
| `upgrade_candidates`, `approved_upgrade` | APT flow and catalogue handler |
| `ContainerMaintenance.inspect/plan/validate/apply` | Docker flow and catalogue handler |
| `Controller.command` | Executor and redacted command evidence |
| `Controller.verify_software` | Verification, initially preserving v1 semantics |
| `Controller.prepare/close`, record parser | Orchestrator and deterministic writer/finalizer |
| `Controller.event`, `atomic_write` | Event and persistence interfaces |
| Renderer, installer, units, Splunk assets | Deterministic deployment package |

**Exit:** Existing tests and frozen-fixture parity pass for plans, records, outcomes, command order, errors, retry behavior and dry-run isolation. This stage retains existing timeouts, v1 storage and schedule semantics. It does not introduce SQLite authority, new field formats, altered candidate approval, or new update handlers under a byte-parity claim.

## Stage 2 — implement explicit v2 changes in isolation

Add the transaction journal/outbox, strict envelopes, complete policy fingerprints, action intents, projection reconciliation, single-record four-flow reporting, AI budgets, target registration and all four handlers. Add final inventory verification against the union of expected changes. Implement the protected collector/AI/staging process profiles, but defer their production activation until the relevant later stage.

Keep v1 history readable without allowing v1 prepared work to execute in v2. Explicitly version/approve fixture differences: additive event fields, deterministic closure sections, non-APT expected deltas, transaction receipts and policy drift checks. APT retains refresh-time exact pinning; there is no silent switch to preparation-time package pinning.

Implement two scheduling modes: captured-legacy compatibility for cutover, and the decided weekly mode. Window/date/DST/missed-run behavior changes activate only in Stage 6.

**Exit:** The contract, crash, path-isolation, package/application safety and integration gates in [operations](OPERATIONS.md) pass in an isolated Ubuntu VM. All handler mutation scenarios are exercised against disposable targets. No production software registration is enabled by discovery.

## Stage 3 — three consecutive shadow pairs

Run the new system in its separate shadow state/log roots alongside the old production controller. Explicit manual shadow invocations are sufficient; do not add another production maintenance timer. Shadow is read-only with respect to installed software, services, live APT caches, and the live Docker daemon.

For each of three consecutive legacy preparation/maintenance pairs:

1. Capture comparable before-state and input evidence with collection times.
2. Compare selected candidates, deterministic denials, deferrals, prepared content and AI outcomes. Compare against the actual legacy refreshed APT transaction after maintenance; do not treat a candidate that appeared after preparation as a parity bug.
3. After the legacy run ends, verify the observed outcome and generate only shadow closure/events.
4. Explain intended v2 differences and investigate all unexplained differences. A false success, hidden collector error, unexpected mutation, or identity error resets the consecutive-pair count after correction.

Use captured AI responses for deterministic regression comparisons. Live model calls are performance/quality evidence, not a requirement for identical prose. Shadow Splunk testing uses isolated test assets/searches; it does not install duplicate production file monitors.

**Exit:** Three reviewed pairs with no unexplained safety differences; all new verifiers detect the injected failure fixtures; gateway and resource budgets pass on the intended hardware.

## Stage 4 — supervised APT cutover

The operator executes this as one framework-cutover change. Preserve the measured legacy cadence; do not switch to weekly yet.

1. Stage the reviewed new code/configuration and disabled `ai-sysadmin-v2-prepare` / `ai-sysadmin-v2-maintenance` units. The installer must not enable timers or restart Splunk.
2. Capture timer/service state, config hashes, state backup and a manifest of legacy artifacts. Settle existing legacy PREPARED work through the legacy workflow or an explicit cancellation procedure. Any RUNNING/interrupted change requires review before cutover continues.
3. Stop and disable **both** `ai-sysadmin-prepare.timer` and `ai-sysadmin-maintenance.timer`. A runbook may use `systemctl disable --now` for these exact timer names. This is a future deployment operation, not a command to run while reading this plan.
4. Allow already running legacy prepare/maintenance services to finish. Verify neither service nor its action children has an active or queued job; acquire the shared legacy lock. Do not terminate a package transaction to make cutover faster.
5. Add a reviewed legacy service drop-in with `ConditionPathExists=!/var/lib/ai-sysadmin/v2-owner`, reload unit definitions, and durably create that ownership marker under the lock before new execution. It prevents normal legacy service activation while v2 owns the host. Retain the shared lock. Direct invocation of legacy mutating binaries during v2 ownership is prohibited by the operator runbook; the marker is not represented as a defense against an administrator bypassing the service.
6. Import only settled terminal history into the new journal; verify hashes without editing legacy records/plans. Project the current pointer and prove legacy/v2 lock contention with read-only probes. Abort on unrecognized active artifacts.
7. Run one supervised preparation and the corresponding maintenance window through the new services, with APT mutation enabled and Docker/manual/pip updates held. Plan the two invocations on the configured preparation and maintenance days. Keep all new timers disabled during this canary.
8. Verify package versions, health, record/receipt/outbox consistency, Splunk indexing, unchanged held targets, and a second `maintain` invocation that performs no mutation. Verify both legacy timers remain inactive/disabled and the ownership marker is present.

**Exit:** One locally and observably successful APT change, a verified no-op repeat, no unresolved RUNNING state, and a usable rollback manifest.

## Stage 5 — two scheduled cycles at legacy cadence

Enable only the two new timers, retaining the captured schedule and missed-run behavior for these two compatibility cycles. Check the rendered definitions and next run times. Keep both legacy timers disabled, the service guard in place, and all legacy code/artifacts retained.

**Exit:** Two consecutive successful scheduled cycles, healthy audit delivery and no duplicate records/actions. Investigate a blocked/failed cycle and restart this count after correction. Do not classify a safely blocked cycle as unsafe behavior, but do not use it as evidence of successful operation.

## Stage 6 — separate weekly schedule change

With no active lifecycle process, no pending package action, and no PREPARED plan waiting for the old cadence, install these reviewed timer settings:

```ini
# ai-sysadmin-v2-prepare.timer
[Timer]
OnCalendar=Sat *-*-* 20:00:00 Europe/Copenhagen
Persistent=false
AccuracySec=1min
RandomizedDelaySec=0
```

```ini
# ai-sysadmin-v2-maintenance.timer
[Timer]
OnCalendar=Sun *-*-* 20:00:00 Europe/Copenhagen
Persistent=false
AccuracySec=1min
RandomizedDelaySec=0
```

Activate weekly window identities, the 30-minute start allowance and the 48-hour age limit together. A missed preparation or maintenance trigger emits attention on the next status/observability check and waits for an explicitly planned window; it does not run maintenance immediately on reboot. `Persistent=true` would catch up missed calendar triggers when a timer is activated, as documented by [systemd timer semantics](https://raw.githubusercontent.com/systemd/systemd/main/man/systemd.timer.xml).

Validate the next four preparation/maintenance pairs with `systemd-analyze calendar`, including a timezone/DST fixture. Align service descriptions and rendered documentation with weekly operation.

**Exit:** The first weekly pair completes successfully and no legacy-cadence job remains queued.

## Stage 7 — enable the remaining flows in order

Activate the collector/AI/staging privilege profiles as a separately verified step before new manual/pip handlers are enabled. Profiles must preserve expected inventory visibility, redact credentials and prohibit writes to unrelated installations.

At this stage also activate the final 150-minute maintenance budget, including its 10-minute final verification reserve, and the three-hour outer service limit. The earlier APT-only canary and compatibility cycles retain their 90-minute budget and two-hour outer limit. Verify admission using complete target-group time estimates before enabling additional mutations.

Enable Docker first, then manual software, then pip. For each flow:

- Confirm the isolated update, failure, backup/recovery, wrong-version, policy-drift and repeat-run tests pass.
- Review actual target registrations and readiness checks; retain holds on unsupported targets.
- For an eligible production target, execute one supervised update under the shared change lifecycle and verify both its result and the unaffected flows.
- If the host has no eligible target, record `NO_TARGET`, complete the disposable-VM canary, and retain disabled production registration. Do not invent an application or install one on production solely to satisfy the gate.

These are required implementation stages, not optional future projects. A particular unsupported product can remain report-only after its flow and supported handler are complete.

## Stage 8 — complete observation and handoff

Observe four consecutive successful weekly cycles after the final applicable handler activation. Confirm operator status, retry/recovery, indexing checks and emergency scheduling disablement are documented and exercised in the isolated environment. Retain the disabled legacy installation for at least 90 days after completion. Its removal is a separate operator change, not part of this migration.

**Exit:** Every acceptance row passes; all four flows are visible; supported handlers are proven; no unresolved action or unaccounted delta remains; the owner records operational acceptance.

## Rollback

First stop/disable both new timers and prevent additional invocation. Wait for active lifecycle/action processes to finish, inspect the journal and artifact state, and acquire the shared lock. Never restore a whole old state snapshot over new history.

**Before any executor action:** Mark any new pending v2 change FAILED through the explicit cancellation path with a cutover-backout reason. Preserve its journal and artifacts. Restore a known terminal legacy pointer from the manifest, verify legacy code/configuration hashes, remove the v2 ownership marker only after v2 is quiescent, and restore the captured legacy timer enable/active state. Do not expose a v2 prepared plan to the legacy executor.

**After any executor action, including metadata refresh:** Do not replay the change through the legacy controller. Verify current packages, applications, backups and action processes; finalize or preserve the failed/interrupted change with operator review. Prepare a separate recovery change if necessary. Framework rollback can then restore legacy scheduling for a future window only after legacy health/policy checks pass and all v2 work is terminal.

Application recovery uses the rules in [software flows](SOFTWARE_FLOWS.md). There is no automatic APT downgrade, database restore, reboot, or controller-driven reinstall. Splunk delivery repair replays committed outbox events with the same IDs and never reruns maintenance.
