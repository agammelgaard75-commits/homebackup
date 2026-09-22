# Lifecycle, Contracts, and Persistence

## State and phase

Only the orchestrator authorizes transitions. The finalizer is its persistence function, not a second state authority.

| Persisted record status | Permitted phases | Next status |
| --- | --- | --- |
| No record yet | inspect, assess, build | PREPARED after atomic preparation commit |
| PREPARED | prepared, preflight | RUNNING if gates pass; FAILED on blocking execution validation |
| RUNNING | execute, verify, finalize | CLOSED or FAILED after deterministic verification |
| CLOSED | terminal | None |
| FAILED | terminal | None |

`PREFLIGHT_RUNNING` and `VERIFYING` are not record statuses. The record remains PREPARED during read-only preflight and RUNNING throughout execution and verification. Commit RUNNING and flush its required projections before the first executor action, including APT metadata refresh.

A policy-blocked preparation is stored as PREPARED with immutable `blocked_reasons` and no executable actions. `maintain` records FAILED with the reasons and no mutations. Repeated preparation returns that existing plan without reconsulting AI. Preparation failure before a commit leaves no executable record and emits an error outcome.

## Identity and windows

For new v2 work, `change_id` is `CHG-YYYYMMDD`, using the maintenance window's date in Europe/Copenhagen. Store exact UTC window start/end and timezone alongside that display identity. Existing legacy IDs remain unchanged. `run_id` and `attempt_id` use UUIDs; `action_id` includes the change ID, stable ordinal and target ID. Explicit retries retain the inherited `-R1`, `-R2` suffix pattern and a `parent_change_id`.

The final weekly preparation window starts Saturday 20:00; maintenance starts Sunday 20:00. The preparation plan is at most 48 hours old, matches the intended maintenance window, and may start mutation only between Sunday 20:00 and 20:30. An accepted run may finish after 20:30 within its overall deadline. UTC calculations use timezone-aware conversion and are tested across DST; age is not computed from naive local timestamps.

No plan is automatically carried to a later week's window. A collision with an existing terminal change for a window is a no-op for that identity; a separate authorized recovery window is needed to do more work. Before the separate weekly schedule change, use the captured legacy scheduling and identity semantics in the compatibility mode described in [migration](MIGRATION.md).

On the next scheduled preparation, an older PREPARED change whose window or age has expired is closed FAILED with an explicit expiration reason, but only after the journal and process checks prove no action started. The controller may then prepare the new scheduled window. This is not a retry of the expired change. A RUNNING or uncertain change always blocks that progression and requires operator recovery.

## Storage layout

```text
/var/lib/ai-sysadmin/
  controller.lock                  # same legacy lock inode; never replace/unlink
  lifecycle.sqlite3                # authoritative v2 transactional journal
  current-change                   # compatible projection of active/latest ID
  CHG-YYYYMMDD.plan.json            # plan stays at the legacy root location
  changes/CHG-YYYYMMDD.txt          # one status field; deterministic closure
  evidence/<change-id>/...
  receipts/<change-id>/...
  containers/...                   # preserve legacy layout
  imports/<manifest-id>/...        # reviewed legacy inventory and hashes
  dry-run/...                      # separate DB, lock, pointers and artifacts
/var/log/ai-sysadmin/
  audit.jsonl
  health.jsonl
  anomalies.jsonl
  ignored.jsonl
  dry-run/...
```

Shadow mode uses `/var/lib/ai-sysadmin-multi-agent-shadow` and `/var/log/ai-sysadmin-multi-agent-shadow` with `shadow=true`, dry-run semantics, and its own DB/lock. Canonical-path, owner, mode, symlink and inode checks reject overlap with live paths. Mutating catalogue calls fail in shadow/dry-run even if they reach the executor; existing applications, APT caches, and Docker images must remain untouched. State/scratch evidence writes are allowed only inside the selected isolated roots.

## Versioned contracts

Use a strict `ai-sysadmin/<artifact>/v2` schema for new plans, flow results, execution manifests, and verification. Envelopes require host identity, change/run/attempt identity, flow/component/phase, mode, policy and catalogue versions, generated/observed UTC times, outcome, evidence references, findings and errors. Plans additionally require window identity, expiry, selected actions, deferrals, required checks, and the complete policy fingerprint.

Use canonical UTF-8 JSON with sorted keys, compact separators, no nonfinite numbers, and explicit schema versions. Hash the object excluding its own digest field. An evidence reference names a confined relative path, byte length, digest, media type and collection time. Reject path traversal, unknown fields/versions, wrong IDs/mode/host, unsupported actions, duplicate ordinals, stale evidence and oversized content.

The policy fingerprint covers all effective nonsecret policy/configuration, IGNORE.md semantics, target registrations, approved artifact sources, schedule, handler/catalogue version and code release identity. Credential references are included; secret bytes are excluded. Credential rotation alone does not invalidate authorization. A policy change requires a new plan; supporting a schema version is not equivalent to matching the prepared policy.

APT preparation stores indicative candidates and a bounded-policy authorization. A separate immutable execution manifest records exact refreshed package versions and transaction evidence before installation. Docker/manual/pip target artifacts are exact in the prepared plan. Their drift blocks execution.

Existing v1 terminal records/plans are preserved byte-for-byte, hashed in an import manifest, and indexed as legacy history. Do not claim v1 plans meet v2 envelope requirements. Settle legacy PREPARED/RUNNING work before import and never reinterpret a legacy authorization as v2 approval.

## Lock and process lifetime

Retain the global nonblocking `flock` at the existing production lock path for the whole lifecycle invocation. Never recreate its inode as part of deployment. The executor remains in-process, so no separate executor can accept queued work after its controller has exited.

Every external mutating command gets a durable action-start row before launch and inherits the lock file descriptor where supported. Root action children remain in the service's control group; use `KillMode=control-group`, `Restart=no`, and an overall bounded service lifetime. Run operator-triggered mutation through the same systemd service path, not an unmanaged background shell. Read-only `status` may run directly.

Per-command timeout handling must account for descendants, including dpkg children. Do not regard killing the immediate subprocess as proof that mutation has stopped. Wait for action processes to end before verification/closure; if process termination cannot be established, preserve RUNNING and require operator review. On startup also inspect active lifecycle/action units and durable RUNNING records. A free advisory lock alone is not permission to start another change.

## Transaction and projection protocol

Use local SQLite through Python `sqlite3`, `journal_mode=DELETE`, `synchronous=EXTRA`, foreign keys enabled, and explicit transactions. Enforce unique change IDs, unique `(change_id, action_ordinal)`, a single terminal receipt per change, unique event IDs, and guarded PREPARED→RUNNING/terminal updates. Keep transactions short; no transaction stays open while a maintenance command runs.

1. **Prepare:** persist canonical plan bytes, rendered record bytes, evidence references, current pointer and preparation outbox events in one transaction. Evidence files must be durably written first. Commit is the authority; text/JSON files are projections.
2. **Project before execution:** write required plan/record/pointer files with exclusive temporary files, flush the file, atomic replacement on the same filesystem, and flush the containing directory. Track the expected previous and new digest. Reconcile only known older projections or missing files; unexpected edits are tampering and block execution.
3. **Start:** atomically compare PREPARED, persist RUNNING, and enqueue its event. Project and flush before the first executor side effect. For every action, commit STARTED and its exact input/authorization digest before launch. Commit results and independent verification afterward.
4. **Finalize:** in one guarded transaction, persist final status, complete immutable closure text, flow outcomes, action/evidence references, completion receipt, current pointer and closure outbox event. Terminal records cannot be reopened or have their facts edited.
5. **Deliver:** project committed files and append outbox events to the existing JSONL streams. Flush before marking an event delivered. A crash after append but before acknowledgement may deliver the same event twice; replay its original stable ID and payload.

Stable event IDs derive from persisted change/action/event identity and ordinal, not from a new replay timestamp. Consumers deduplicate by event ID. Maintenance has no exactly-once side-effect guarantee across a crash: durable intent and a refusal to replay uncertain actions are the safety mechanism. The bookkeeping transaction is atomic; commands and files outside SQLite are not part of that transaction. SQLite's [atomic-commit explanation](https://www.sqlite.org/atomiccommit.html) describes the database guarantee and its filesystem assumptions.

A damaged partial JSONL tail must not be extended as if it were a complete line. Preserve/quarantine the damaged segment under the log lock, start a valid new active stream, and replay unacknowledged outbox events with their stored IDs. Never remove evidence of the corruption. Existing log rotation must coordinate with the writer and retain segments until delivery/reconciliation is verified.

The journal and its committed outbox are authoritative for v2 lifecycle/audit facts. JSONL is the durable delivery projection consumed by Splunk. This deliberately refines the draft's claim that JSONL alone is the source audit trail. File `fsync` plus rename also needs directory synchronization for the directory entry, as described in the [Linux fsync manual](https://man7.org/linux/man-pages/man2/fsync.2.html).

## Recovery matrix

| Interruption/failure | Required next behavior |
| --- | --- |
| Before preparation commit | Remove no existing records; preserve diagnostic scratch; another preparation may restart collection |
| After preparation commit, before file projection | Reconstruct missing/known-stale projections from committed bytes; return existing plan |
| During preflight, still PREPARED | After proving no action started, repeat read-only preflight if window/age allow |
| Missed window leaves an old PREPARED record | Prove no action started, commit FAILED with expiration reason, then permit preparation for a new scheduled window |
| RUNNING with no completed receipt | No automatic resume or successor; determine whether side effects occurred |
| During verification | Remains RUNNING; no automatic re-execution; operator-authorized recovery inspection |
| Command error with processes confirmed stopped | Verify actual state and commit FAILED; stop later mutations |
| Terminal transaction committed, projections/outbox incomplete | Complete only bookkeeping; never re-run actions or change terminal facts |
| Unexpected record/plan edit or DB corruption | Block execution, preserve bytes, require operator recovery; never rebuild authority from an untrusted text pointer |
| Disk/audit write failure before mutation | Execute nothing |
| Disk/audit write failure after mutation | Stop new actions; retain RUNNING if terminal commit is impossible; surface service/journal failure and require recovery |
| Splunk unavailable with local storage healthy | Finish verified local closure, report indexing lag; do not repeat maintenance |

Operator recovery uses a dedicated inspection/finalization path under the same lock. It records a rationale and actual observed state, confirms no action process remains, and finalizes an interrupted change as FAILED with recovery findings. It does not infer CLOSED from partial evidence. A new `prepare --retry-of <failed-id> --reason <text>` creates one stable successor after inspection; repeating that command returns the same successor.

Human notes are append-only separate annotations linked to a change. They cannot alter machine status fields, prepared policy, terminal content or evidence. A correction to an old factual report is a new linked annotation, not a rewrite of history.
