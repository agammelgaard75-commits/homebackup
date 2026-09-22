# Agent and Worker Responsibilities

“Agent” here means a bounded role or process. It does not necessarily mean an
LLM. Every role has explicit inputs, outputs, permissions, and failure behavior.

## 1. Preparation agent (AI)

**Purpose:** reason about the prepared facts and explain whether the proposed
maintenance is reasonable.

**Inputs:** redacted inspection bundle, deterministic policy findings, available
approved action identifiers, inventory summary, prior unresolved findings, and
schema/policy versions.

**Outputs:** `proceed` boolean, concise reasoning, risk labels, review items, and
references to evidence identifiers.

**Permissions:** no shell, no filesystem mutation, no Splunk writes, no lifecycle
transition, and no direct access to secrets.

**Must not:** invent commands, authorize prohibited work, suppress collector
errors, approve major upgrades/removals, or reinterpret ignored-software policy.

## 2. Change writer (deterministic)

**Purpose:** create the planned change record the day before maintenance.

**Inputs:** validated plan, policy verdict, agent assessment, inspection evidence
references, and planned verification criteria.

**Outputs:** one atomic PREPARED record and its digest/reference.

**Permissions:** write only the assigned change artifact and emit audit events.

**Must not:** change the plan, execute actions, overwrite terminal records, or
append duplicate closure sections.

## 3. Maintenance executor (deterministic)

**Purpose:** run the prepared and revalidated action sequence.

**Inputs:** immutable plan, current policy snapshot, preflight verdict, exact
catalogue version, and active change capability.

**Outputs:** per-action results, bounded/redacted evidence, actual candidates used,
and executor verdict.

**Permissions:** the only mutating role. It may use only the existing approved
APT and explicitly configured container operations.

**Must not:** execute model text, accept arbitrary argv, perform release upgrades,
remove packages, reboot, or autonomously change SSH, firewall, networking, users,
sudo, disks/filesystems, boot configuration, or other availability-sensitive
configuration.

## 4. Verification worker (deterministic)

**Purpose:** independently prove the intended outcome.

**Inputs:** pre-change facts, expected result, action results, and post-change
collector data.

**Outputs:** expected-versus-actual deltas, health verdict, package/container
verification, remaining attention, and evidence references.

**Permissions:** read-only host inspection and audit event emission.

**Must not:** repair findings, retry maintenance, or turn partial success into a
successful verdict.

## 5. Closure agent (optional AI)

**Purpose:** create a useful human-readable closing remark from verified facts.

**Inputs:** immutable plan summary, deterministic verification verdict, action
results, and unresolved findings.

**Outputs:** summary of success/failure, changes, failures, remaining attention,
and overall state.

**Permissions:** no system access and no direct record write.

**Must not:** choose the final status, omit mandatory failures, introduce facts,
or state that a reboot occurred. If unavailable, deterministic closure rendering
is mandatory.

## 6. Finalizer (deterministic)

**Purpose:** apply the terminal state and persist the closure exactly once.

**Inputs:** verification verdict, executor results, optional validated closure
narrative, and current record digest/status.

**Outputs:** CLOSED or FAILED record, closure event, current pointer state, and
completion receipt.

**Permissions:** exclusive write access to lifecycle metadata and the assigned
record.

**Must not:** edit history, close a record twice, or mark success when verification
failed or evidence is incomplete.

## 7. Event writer / Splunk delivery (deterministic)

**Purpose:** make the entire lifecycle auditable and observable.

**Inputs:** typed events from all components.

**Outputs:** locked JSONL streams compatible with the existing Splunk app.

**Permissions:** append-only log access. Splunk continues to ingest files using
the existing monitored inputs.

**Must not:** allow agents to write raw JSONL directly, log secrets, or count
delivery as proof of indexing. Separate integration checks verify Splunk search
visibility.

## 8. Lifecycle orchestrator (deterministic)

**Purpose:** coordinate all roles without inheriting their business logic.

**Inputs:** scheduler command, configuration, current state, and operator retry
authorization when applicable.

**Outputs:** ordered component invocations, valid state transitions, phase events,
and stable exit status.

**Permissions:** lifecycle state and lock ownership; it delegates host mutation
only to the executor.

**Must not:** bypass a failed role, infer approval from prose, automatically retry
a mutating phase, or run preparation and maintenance concurrently.
