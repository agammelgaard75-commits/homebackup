# Current System Baseline

## What exists today

The current repository at `/home/bot/sysadmin` is already conservative and
contains many of the controls the future framework needs:

- `src/ai_sysadmin.py` provides the lifecycle controller, host and software
  inspection, package planning, policy gates, fixed action catalogue, execution,
  post-change verification, record closure, locking, event output, and CLI.
- `src/container_maintenance.py` inventories explicitly configured Compose
  services, resolves pinned image digests, validates policy and drift, creates
  backups, replaces one service, and verifies readiness.
- `scripts/litellm_planner.py` is the bounded AI adapter. It receives structured
  inspection data and returns only `proceed` plus reasoning; it cannot supply
  executable commands.
- `scripts/render_deployment.py` deterministically renders timers and Splunk
  application assets.
- `scripts/install.sh` performs idempotent deployment and deliberately does not
  enable timers or restart Splunk.
- `scripts/validate.sh` and the `tests/` suite cover dry-run separation,
  lifecycle integrity, repeated execution, package safety, software inventory,
  container safety, credential handling, deployment rendering, and Splunk
  assets.
- `systemd/` contains separate preparation and maintenance oneshot services and
  timers.
- `splunk/` contains health, anomaly, and ignored-software dashboards and
  deployment documentation.
- Runtime artifacts are currently designed for `/var/lib/ai-sysadmin`, with
  JSON Lines logs under `/var/log/ai-sysadmin` and policy under
  `/etc/ai-sysadmin`.

## Controls that must not regress

- A controller-wide nonblocking lock prevents overlapping lifecycle processes.
- Plans are immutable and protected by a checksum.
- The record header has exactly one machine-readable status.
- Closed and failed changes are not automatically executed again.
- Retries create explicit successor changes and retain history.
- Plans expire, preflight health gates execution, and postflight verifies real
  state rather than trusting command return codes.
- Dry runs use separate state and log trees and cannot consume a live change.
- AI output cannot add commands or override hard safety policy.
- Package transactions are simulated and fail closed on removal, new installs,
  downgrades, epoch/major changes, and ambiguous transitions.
- Container changes are opt-in, digest-pinned, backup-first, drift checked, and
  limited to one configured Compose service at a time.
- Sensitive command output is hashed/redacted before ordinary audit logging.
- Audit, health, anomaly, and ignored-software events are separate Splunk
  sourcetypes.

## Baseline inconsistencies to resolve before cutover

The governing instructions describe weekly maintenance, but the tracked
configuration and rendered examples currently use daily timers. The systemd
service descriptions also say weekly while their timers are daily. The migration
must not quietly choose one. Cadence must be documented and approved as a
separate operating-policy decision. Refactoring and schedule changes should not
occur in the same production change.

The monolith currently owns multiple concerns through one `Controller` object.
This is not itself unsafe, but component extraction must preserve ordering,
atomic writes, locks, exact plan validation, event correlation, and failure
semantics.

## Baseline evidence required before implementation

Before changing code, capture and retain:

1. Current source revision and hashes of deployed files.
2. Current effective config with credentials redacted.
3. Active timer definitions and next-run times.
4. Installed component versions, including Splunk and the AI gateway/model.
5. A passing result for all existing tests and validation scripts.
6. One successful no-change repeat-run test in an isolated environment.
7. Current Splunk event counts, sourcetypes, dashboard definitions, and saved
   search behavior.
8. Representative PREPARED, CLOSED, FAILED, expired, tampered, and retry change
   artifacts with sensitive content removed.

These form the compatibility baseline for every migration phase.
