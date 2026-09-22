# Migration Roadmap

Each phase is a separately reviewable change. The current controller remains the
only production executor until the cutover phase. Passing a phase permits planning
the next phase; it does not automatically deploy it.

## Phase 0 — decisions and frozen baseline

- Resolve, document, and approve the intended cadence: weekly policy versus the
  current daily timer configuration.
- Capture the evidence listed in `01-current-system.md`.
- Freeze the v1 event and artifact examples used for compatibility tests.
- Record all current external dependencies and versions: Python, Ubuntu/APT,
  Docker/Compose when enabled, Splunk, LiteLLM, and the configured model.
- Define owners for approval, failure review, retry creation, Splunk operations,
  and emergency disablement.

**Exit gate:** baseline tests pass and the cadence decision exists. No production
behavior has changed.

## Phase 1 — characterize and extract contracts

- Add golden tests around current plans, records, closure text, JSONL events,
  package transaction parsing, and container artifacts.
- Define versioned schemas for inspection, policy, plan, action result,
  verification, and closure.
- Extract pure data models and validators without changing CLI behavior.
- Preserve existing paths, exit codes, lock behavior, dry-run separation, and
  Splunk sourcetypes.

**Exit gate:** old tests plus contract/golden tests pass; deployed behavior is
unchanged.

## Phase 2 — extract deterministic workers in-process

- Separate collector, policy, record writer, executor, verifier, finalizer, and
  event writer behind internal interfaces.
- Reuse existing functions rather than reimplementing package and container
  safety logic.
- Keep the current `ai-sysadmin` CLI as a compatibility facade and keep all
  components in one process initially.

**Exit gate:** byte-level artifacts and decisions match the baseline for the
same fixtures, including failures and repeated runs.

## Phase 3 — introduce the orchestrator and process boundaries

- Move lifecycle state transitions and component invocation into the new
  deterministic orchestrator.
- Invoke read-only components as bounded local processes using JSON stdin/stdout
  or artifact references.
- Keep one lock and one state store; do not introduce a queue or distributed
  scheduler.
- Keep the mutating executor internal until read-only boundaries prove stable.

**Exit gate:** fault-injection proves timeouts, malformed results, wrong IDs,
stale output, partial writes, and duplicate invocation fail closed.

## Phase 4 — shadow preparation

- Run the new collectors, preparation agent, policy gate, and change renderer in
  dry-run/shadow paths only.
- The old controller still prepares and executes production maintenance.
- Compare candidate actions, blockers, inventory, AI verdicts, record content,
  event schema, timing, and resource use over multiple maintenance windows.
- Do not create a second production change record or send shadow events into the
  production Splunk sourcetypes without a clear `shadow=true` marker and separate
  searches.

**Exit gate:** reviewed parity across agreed consecutive windows, with all
differences explained.

## Phase 5 — shadow verification and closure

- After the old controller maintains the host, let the new verifier read the
  resulting host state and produce shadow evidence.
- Generate a shadow closure but never alter the production record.
- Validate deterministic closure fallback by making the closure AI unavailable.

**Exit gate:** the new verifier never claims success where existing controls or
operator review identify failure; Splunk schema/search compatibility passes.

## Phase 6 — manual canary cutover

- Create a formal ITIL change specifically for cutover.
- Stop/disable only the old maintenance timers as part of the approved change;
  retain old code and artifacts for rollback.
- Do not enable new timers yet. Run one manually supervised preparation and one
  manually supervised maintenance window with the new framework.
- Verify packages, containers if configured, host health, record closure, logs,
  Splunk indexing, dashboards, lock behavior, and repeat-run no-op behavior.

**Exit gate:** supervised change closes successfully and rollback remains viable.

## Phase 7 — scheduled operation

- Render reviewed timers for the approved cadence.
- Prove only one preparation timer and one maintenance timer can target the host.
- Enable the new timers explicitly and observe the first scheduled cycle.
- Keep the old installation disabled but available for a defined observation
  period. Never run old and new executors against the same window.

**Exit gate:** agreed stable scheduled cycles and operational sign-off.

## Phase 8 — later cleanup

- Plan removal of the disabled legacy installation as a separate change.
- Retain historical change records and audit logs according to policy.
- Remove legacy services or files only with explicit permission; package removal
  remains out of scope unless separately approved.

## Rollback principle

Before any production mutation by the new framework, rollback means disabling
the new schedule and re-enabling the unchanged old schedule after confirming no
RUNNING change exists. Once a maintenance action has executed, do not blindly
rerun it through the old controller. Verify state, close or preserve the failed
change, obtain operator review, and prepare a separate recovery change.
