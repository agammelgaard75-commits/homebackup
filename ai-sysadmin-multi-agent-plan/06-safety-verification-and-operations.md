# Safety, Verification, and Operations

## Invariant safety boundaries

The new design inherits the current restrictions:

- Permit normal Ubuntu package updates, including security updates.
- Do not perform Ubuntu release upgrades, major/unclassified software upgrades,
  downgrades, package removals, or new package installations without explicit
  permission and a separately designed workflow.
- Never reboot automatically.
- Do not autonomously change SSH access, firewall rules, network configuration,
  users, sudo, disks/filesystems, boot configuration, or similarly availability-
  sensitive controls.
- Normal permitted APT maintainer scripts may restart services only when current
  policy permits service restarts.
- Non-APT software remains inventory/report-only unless an explicit, tested
  catalogue handler exists. Configured Compose services retain the current
  narrow update workflow.

## Defense in depth

- Strict, versioned schemas at every boundary.
- Fixed action catalogue with normalized parameters; no shell interpreter.
- Plan checksum plus evidence, policy, ignore-file, and catalogue fingerprints.
- Global lock and terminal-state immutability.
- Filesystem permissions and systemd sandboxing appropriate to each role.
- Bounded input/output sizes, timeouts, redaction, and credential isolation.
- Preflight revalidation immediately before mutation.
- Independent postflight checks and expected-versus-actual comparison.
- No automatic continuation after an interrupted mutating phase.

## Required test layers

### Unit and contract tests

Cover schema rejection, lifecycle transitions, plan integrity, stable identity,
atomic writes, event redaction/routing, closure fallback, catalogue validation,
package version classification, ignored policy, and container policy.

### Compatibility tests

Feed identical fixtures to the monolith and extracted components. Compare plans,
blockers, action sequences, exit classifications, package deltas, container
decisions, records, and Splunk event fields. Text may change only where an
approved schema/version change documents it.

### Failure and recovery tests

Inject collector failures, AI timeout/malformed/negative results, policy drift,
tampered/expired plans, missing pointers, malformed records, lock contention,
APT timeouts, partial executor results, unhealthy postflight, disk pressure,
Splunk outage, process termination, and corrupted handoff files.

### Idempotency tests

Run preparation, rendering, installation staging, finalization, and complete
dry-run lifecycles twice. Confirm the second invocation creates no duplicate
record, closure, service, timer, input, dashboard, user, job, configuration line,
container restart, or package action.

### Integration tests

Use an isolated Ubuntu VM snapshot. Exercise no-update, permitted security update,
refused major upgrade, refused removal/new dependency, failed service, reboot-
required, non-APT inventory, ignored software, and configured container scenarios.
Never manufacture these scenarios on the production VM merely for testing.

## Production acceptance checklist

- All legacy and new tests pass from a clean checkout.
- Dry-run paths cannot resolve or mutate live artifacts.
- AI outputs never reach an execution API as argv or shell text.
- Only the executor has the mutating interface.
- A plan prepared under changed policy/configuration is rejected.
- Successful commands plus failed verification close FAILED.
- Interrupted RUNNING changes require operator review.
- Repeated invocations are no-ops where the lifecycle is already complete.
- No automatic reboot occurs; reboot-required is recorded prominently.
- Existing and new Splunk searches return expected unique events.
- Dashboards show server health, anomalies, ignored software, change status,
  component/phase duration, failures, and log/indexing freshness.
- Old and new production executors are never enabled simultaneously.

## Auditing requirements

For every component invocation, record:

- What was requested and why.
- What evidence was inspected and its digest/time.
- Findings and distinction between facts, recommendations, and policy verdicts.
- The decision and policy/rule identifiers supporting it.
- Approved action identifier and normalized parameters.
- Start, result, duration, bounded output or redacted-output digest, and error.
- Verification criteria, observations, and expected-versus-actual outcome.
- State transition before/after.
- Final status and closing remark.

Local JSONL is the source audit trail. Splunk indexing is an observable copy and
must be verified by search; writing a file does not prove ingestion.

## Operator runbooks required before cutover

1. Inspect current lifecycle state and identify the active change.
2. Disable future scheduling without interrupting a RUNNING action.
3. Review a FAILED or interrupted change.
4. Create an explicit successor retry with rationale.
5. Diagnose AI, collector, APT, container, verification, and Splunk failures.
6. Confirm reboot-required without rebooting.
7. Roll back the framework cutover while preserving records and logs.
8. Restore Splunk ingestion/dashboard assets without duplicating inputs.

## Metrics and dashboards

Reuse the current dashboards first, then add panels for lifecycle state, phase
duration, component errors, blocked preparations, plan expiry, verification
failures, interrupted changes, executor action counts, event lag, and shadow/old/
new implementation identity. Anomaly history must not be presented as the number
of currently open incidents unless explicit resolution correlation exists.
