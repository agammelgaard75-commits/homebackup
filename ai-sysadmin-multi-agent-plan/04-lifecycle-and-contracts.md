# Lifecycle and Handoff Contracts

## State model

```text
NEW -> INSPECTING -> ASSESSED -> PREPARED
                                  |
                                  v
                           PREFLIGHT_RUNNING
                                  |
                    +-------------+-------------+
                    |                           |
                    v                           v
                 RUNNING                    FAILED
                    |
                    v
                VERIFYING
                    |
              +-----+-----+
              |           |
              v           v
            CLOSED      FAILED
```

`BLOCKED` can be stored as a preparation outcome if desired, but it is not an
executable state. Existing compatibility may continue representing blocked work
as a PREPARED plan with blockers until a schema migration is approved.

Only the orchestrator may transition state. Terminal records are immutable. A
reviewed failure is followed by an explicit successor such as `CHG-YYYYMMDD-R1`;
it is never reopened.

## Stable identity and correlation

- `change_id` identifies the planned change and all its artifacts.
- `run_id` identifies one process invocation.
- `attempt_id` identifies a component attempt within a run, without changing the
  change identity.
- `parent_change_id` identifies an explicitly authorized retry/successor.
- Every artifact contains hostname, generated time, schema version, policy
  version, catalogue version, dry-run flag, and content digest.

The production cadence decision determines base change IDs. Repeated preparation
for the same window resolves to the existing artifact rather than creating a
duplicate.

## Proposed artifacts

```text
state/
  controller.lock
  current-change
  changes/CHG-....txt
  plans/CHG-....plan.json
  evidence/CHG-..../inspection-....json
  evidence/CHG-..../preflight-....json
  evidence/CHG-..../execution-....json
  evidence/CHG-..../verification-....json
  receipts/CHG-..../component-....json
  containers/...                         # preserve current layout initially
logs/
  audit.jsonl
  health.jsonl
  anomalies.jsonl
  ignored.jsonl
```

Dry-run retains the existing complete separation under `state/dry-run` and
`logs/dry-run`.

## Contract envelope

All role messages use a versioned JSON envelope similar to:

```json
{
  "schema": "ai-sysadmin/component-result/v1",
  "change_id": "CHG-YYYYMMDD",
  "run_id": "YYYYMMDDThhmmssZ-pid",
  "component": "verifier",
  "phase": "postflight",
  "dry_run": false,
  "started_at": "RFC3339 timestamp",
  "completed_at": "RFC3339 timestamp",
  "outcome": "pass",
  "evidence": [],
  "findings": [],
  "errors": []
}
```

Schemas must reject unknown command fields in AI responses, missing identity,
invalid status, mismatched dry-run mode, excessive payload size, stale evidence,
and unknown schema or catalogue versions.

## Plan rules

The plan contains only catalogue action IDs and normalized parameters generated
by trusted code. It stores the exact expected order, preparation facts and
digest, ignore-policy digest, approved package versions, exact container digest,
verification criteria, blockers, AI assessment, expiry, and plan checksum.

Immediately before mutation, deterministic code verifies:

1. The pointer and record identity are valid.
2. Record status is exactly PREPARED.
3. The plan exists, is within its lifetime, and its digest matches.
4. The plan schema, policy, and action catalogue versions are supported.
5. Dry-run/live mode matches every artifact.
6. The ignore policy and configured container policies have not drifted.
7. Fresh preflight health is acceptable.
8. The exact package transaction remains permitted after index refresh.
9. The expected action sequence contains no unknown or reordered actions.

## Idempotency and concurrency

- Retain one global nonblocking lifecycle lock initially.
- Add an atomic receipt per completed deterministic action. A receipt is useful
  for diagnosis but never causes an interrupted RUNNING change to resume
  automatically.
- Writes use temporary files, `fsync`, and atomic replacement; event writes use
  append mode, file locks, and `fsync`.
- Change writing is create-or-verify: identical content is a no-op; different
  content for an existing immutable identity is an error.
- Finalization uses compare-current-status semantics and writes one closure.
- Splunk events have a stable `event_id` so searches can identify retransmission,
  while source logs remain append-only.
- Repeated install/render operations must produce byte-equivalent assets and
  must not duplicate inputs, units, users, jobs, dashboards, or configuration.

## Failure behavior

- Collector error: preparation is blocked; no incomplete facts are approved.
- AI unavailable/malformed during preparation: block when AI is required.
- AI unavailable/malformed during closure: use deterministic closure fallback.
- Policy denial: record the specific reason; execute nothing.
- Executor error or timeout: stop later mutating actions, verify current state,
  close FAILED, and require operator review.
- Verifier error or unhealthy result: close FAILED even when all commands returned
  zero.
- Splunk unavailable: preserve local audit files, report delivery/indexing status
  separately, and never rerun maintenance solely to reproduce logs.
- Interrupted RUNNING state: do not resume or supersede automatically.
