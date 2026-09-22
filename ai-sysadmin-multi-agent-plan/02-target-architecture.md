# Target Architecture

## High-level flow

```text
systemd timers
      |
      v
deterministic lifecycle orchestrator + global lock
      |
      +-- D-1: collectors -> preparation agent -> policy gate
      |                              |
      |                              v
      |                     deterministic change writer
      |
      +-- maintenance day: preflight collectors -> policy gate
                                      |
                                      v
                            deterministic executor
                                      |
                                      v
                              verification worker
                                      |
                                      v
                        closure agent / fallback renderer
                                      |
                                      v
                   record store + append-only event writer
                                      |
                                      v
                              Splunk file monitor
```

## Architectural rules

1. The orchestrator is the sole authority for lifecycle transitions.
2. The executor is the sole component allowed to mutate the managed host.
3. Agents exchange versioned structured artifacts, not prose instructions or
   shell fragments.
4. Hard policy is deterministic and evaluated both during preparation and
   immediately before execution.
5. The action catalogue is code-owned. An AI may select or recommend only
   identifiers already present in the catalogue.
6. Execution never consumes a plan unless its schema, checksum, identity,
   status, age, policy snapshot, and expected sequence validate.
7. Observations are facts; recommendations are clearly labeled; authorization
   is a separate policy result.
8. Every event includes `change_id`, `run_id`, component, phase, schema version,
   host, timestamp, dry-run flag, outcome, and correlation fields.
9. Component communication starts as local files and local process invocation.
   A message broker is unnecessary until operational evidence justifies it.
10. Failures are fail-closed. No component attempts creative recovery of a
    RUNNING or FAILED maintenance change.

## Components

### Scheduler

Existing systemd timers invoke the orchestrator for `prepare` and `maintain`.
Timer rendering remains deterministic. The new timers must not be enabled while
the current production timers are enabled.

### Lifecycle orchestrator

Owns locking, run identity, state transitions, artifact paths, timeout budgets,
component invocation, and terminal exit codes. It contains no package or
container business logic and performs no direct maintenance command.

### Collectors

Read-only, deterministic collectors produce host health, APT inventory,
available package transactions, non-APT software inventory, Splunk inventory,
ignored-software evaluation, and configured container inventory. Each result
includes collection errors and evidence timestamps.

### Preparation agent

An AI reasoning role receives a bounded, redacted collector summary and the
policy result. It explains risk, identifies review items, and recommends whether
to proceed. Its response is schema validated and cannot add commands.

### Policy gate

Deterministic code applies immutable safety rules. It has final authority over
allow/deny decisions. AI approval never changes a denial into an approval.

### Change writer

Deterministically renders the ITIL-style record from the verified plan and
evidence. It creates or updates exactly one record for a stable change identity,
using atomic writes. It is not an AI role.

### Maintenance executor

Executes only a validated action catalogue entry with orchestrator-issued
capability data for the active change. Package and container tooling is reused.
The first version should be deterministic rather than AI-driven.

### Verification worker

Re-runs independent collectors, compares expected and actual state, and returns
a structured verdict. A successful command alone never produces success.

### Closure agent and deterministic fallback

An optional AI role can turn verified facts into a concise closing narrative and
separate attention items. Deterministic code sets the terminal status and renders
a complete fallback closure if the AI is unavailable or malformed. The AI cannot
alter facts, severity, or status.

### Event writer and Splunk

A deterministic, append-only writer owns JSONL formatting, file locking,
redaction, and routing to audit, health, anomaly, and ignored streams. Existing
Splunk file monitoring and dashboards are reused first. Schema changes must be
additive or introduced under new sourcetypes with migration dashboards.

## Trust boundaries

- AI input excludes credentials, full rendered Compose configuration, sensitive
  command output, and unbounded logs.
- AI output is untrusted data until schema and policy validation succeed.
- Only the executor gets mutating capability, and only for the current approved
  action sequence.
- Collectors, planners, writer, verifier, and reporter should run without a
  general-purpose mutation interface.
- Initial deployment may retain root-owned oneshots for compatibility, but the
  design should prepare for systemd sandboxing and least-privilege separation
  after parity is proven. Privilege reduction is a later, separately tested
  change, not part of the first refactor cutover.
