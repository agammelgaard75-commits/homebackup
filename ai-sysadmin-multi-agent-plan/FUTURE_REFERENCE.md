# Plan Review Findings

Review date: 2026-09-14

## Assessment and scope

The plan is a useful foundation, but it needs revisions before implementation.
The review covered all nine existing Markdown documents in this directory and
compared their claims with the current working tree at `/home/bot/sysadmin`.
That working tree contained existing local changes; it was not a frozen baseline
from a clean checkout.

The isolated regression suite passed using:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests -v
```

The command ran from `/home/bot/sysadmin`. The review did not run the full
`scripts/validate.sh` workflow or verify deployed files, active timers, live AI
behavior, or Splunk ingestion. No plan or implementation files were changed
during the review. This document records the findings afterward.

The baseline inventory and the weekly-versus-daily scheduling discrepancy are
supported by the source. The implementation includes plan checksums, separate
dry-run paths, exact-version APT execution, and configured container safety
checks. These findings concern the proposed migration and do not establish
production readiness.

## 1. Requested software flows are missing

**Priority: High**

`IDEAS.md:4` requests separate flows for APT packages, manually installed
software, Docker, and Python pip packages. The architecture separates lifecycle
roles, while `03-agent-responsibilities.md:48` limits the executor to APT and
explicitly configured containers. The requested manual-software and pip flows
are not defined.

Before implementation, define each flow's inventory, planning, policy,
execution or reporting scope, verification, and failure behavior. Explain how
all four contribute to one change record and how mutations remain coordinated
through the single executor. Identify any initially deferred update handlers
explicitly.

## 2. Cutover leaves the old preparation timer ambiguous

**Priority: High**

`05-migration-roadmap.md:86` says to stop/disable only the old maintenance
timers. The old preparation timer could still invoke the legacy controller and
write production plans or the current-change pointer during the canary phase.

The cutover procedure should explicitly name both legacy timers:

- `ai-sysadmin-prepare.timer`
- `ai-sysadmin-maintenance.timer`

Require active lifecycle processes to finish and verify their state before
transferring production ownership. Preserve a common exclusion mechanism while
old and new installations coexist. Distinguish stopping from disabling:
disabling a systemd unit alone does not stop an active unit, as documented in
the [systemd systemctl manual source](https://raw.githubusercontent.com/systemd/systemd/main/man/systemctl.xml).

## 3. Lifecycle validation and recovery rules are inconsistent

**Priority: High**

The diagram in `04-lifecycle-and-contracts.md:5` introduces
`PREFLIGHT_RUNNING`, but the validation rules at line 103 require the record
status to be exactly `PREPARED` immediately before mutation. The intended order
is ambiguous unless internal phases and persisted record states are distinct.

Recovery rules cover interrupted `RUNNING` changes but do not define behavior
for interrupted `VERIFYING` changes, when maintenance actions have already
occurred. The existing controller's record parser also accepts only
`PREPARED`, `RUNNING`, `CLOSED`, and `FAILED`.

Define persisted versus internal states, allowed transitions, and recovery
behavior for every nonterminal state. Ensure interruption after mutation cannot
permit automatic re-execution or unsafe rollback through the old controller.

## 4. Proposed contract changes conflict with the compatibility gate

**Priority: Medium**

`04-lifecycle-and-contracts.md:98` proposes storing approved package versions
in the prepared plan. The current implementation selects and pins the exact
transaction during maintenance after refreshing package metadata; see
`/home/bot/sysadmin/src/ai_sysadmin.py:630` and its maintenance call site.

The proposed `plans/` subdirectory also differs from the current plan location
directly under the state directory. Persisting the newly proposed lifecycle
states would change the existing record format.

These changes cannot simultaneously satisfy the byte-level artifact and
decision parity gate in `05-migration-roadmap.md:43`. Separate behavior-preserving
extraction from approved schema, storage, and package-approval changes. Specify
when each change occurs, how existing artifacts remain readable, and how package
candidate drift between preparation and maintenance is handled.

## 5. Crash-safe finalization needs a concrete protocol

**Priority: Medium**

The atomic-write rules in `04-lifecycle-and-contracts.md:115` protect individual
files, but do not make updates to the record, receipt, pointer, and closure event
one transaction. A crash between those writes can leave a terminal record
without its expected receipt or closure event.

Define the authoritative commit point and a reconciliation procedure that can
complete missing bookkeeping without repeating maintenance or rewriting
terminal history. Test interruption between each persistence step.

The reused `atomic_write` helper at
`/home/bot/sysadmin/src/ai_sysadmin.py:112` flushes the temporary file and replaces
the destination, but does not flush the containing directory afterward. File
`fsync` alone does not guarantee persistence of the directory entry; see the
[Linux fsync manual](https://man7.org/linux/man-pages/man2/fsync.2.html). Account
for directory durability in the future state-store contract.

## 6. Small-model constraints and the orchestration decision remain unspecified

**Priority: Medium**

`IDEAS.md:3` specifies a small hardware platform with a maximum model of
`qwen3.5:9b` and asks for short, simple AI tasks. The plan describes bounded
inputs and timeouts in general terms, but does not specify input/output budgets,
inference concurrency, or runtime limits suited to that constraint.

Define those limits and validate them on the intended hardware. Keep each AI
assessment narrowly scoped and document failure behavior when a budget or
timeout is exceeded.

`IDEAS.md:1` also invites an n8n implementation if it is the better solution.
The plan selects systemd without documenting that evaluation. Record the
orchestration decision and its rationale. The existing architecture drawing
shows the lifecycle, but should be extended to show the four requested software
flows, their shared execution controls, and their combined verification and
closure.

## Use of this reference

Resolve these findings in the relevant plan documents before treating the plan
as implementation-ready. Source line numbers refer to the files as reviewed on
2026-09-14 and may move as the plan or implementation changes.
