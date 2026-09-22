# Final AI Sysadmin Migration Plan

Decision date: 2026-09-14. Finalized: 2026-09-15. Status: design decisions complete; implementation and production validation remain future work.

This package is the implementation specification for dividing `/home/bot/sysadmin` into four software maintenance flows under one deterministic lifecycle controller. It supersedes conflicting proposals in the parent planning documents. Creating this package does not deploy the design or change the host.

The selected design uses systemd, modular Python, short preparation assessments through the existing LiteLLM gateway, a single executor, and one ITIL change record per maintenance window. APT, manually installed software, Docker, and pip each own their inventory, planning, policy, and verification. All host changes run in sequence through the shared executor.

## Reading order

1. [Decisions](DECISIONS.md) resolves every previously open question and records the reasons.
2. [Architecture and flow](ARCHITECTURE.md) explains the complete lifecycle and component ownership.
3. [Software flows](SOFTWARE_FLOWS.md) specifies exactly what each flow can manage.
4. [Lifecycle and persistence](LIFECYCLE.md) defines state, contracts, locking, and crash recovery.
5. [Migration and cutover](MIGRATION.md) gives ordered implementation stages and rollback procedures.
6. [Operations and acceptance](OPERATIONS.md) defines limits, runbooks, retention, and measurable completion gates.

The [standalone flow drawing](flow.svg) can be opened in a browser. The architecture document also includes Mermaid and a plain-language walkthrough.

## Selected outcome

| Area | Final decision |
| --- | --- |
| Orchestration | systemd timers and local Python components; no n8n dependency |
| Final schedule | Prepare Saturday 20:00; maintain Sunday 20:00, Europe/Copenhagen |
| Schedule transition | Preserve the captured legacy cadence at framework cutover; switch to weekly in a separate change after two successful scheduled cycles |
| Software coverage | Four separate flows; all inspect and report, with narrowly registered update handlers for each |
| AI | Existing `qwen3.5:9b`, preparation only, one request at a time; deterministic closure |
| Execution | One host-mutating executor; APT, Docker, manual software, then pip |
| Records | One change; PREPARED, RUNNING, CLOSED, FAILED remain the only record statuses |
| Persistence | Local SQLite transaction journal plus durable text/JSON projections and an event outbox |
| Production paths | Preserve `/var/lib/ai-sysadmin` and `/var/log/ai-sysadmin`; separate code, config, and shadow paths |
| Failure | Stop later mutations, verify actual state, preserve evidence, require explicit recovery for interrupted work |

## Evidence and limits

The parent [review record](../FUTURE_REFERENCE.md) documents source inspection and a passing isolated regression suite on 2026-09-14. The source tree contained local changes. No live timer, installed-version, gateway-performance, or Splunk-ingestion baseline was established by that review.

The choices here are final design decisions, not claims that those unmeasured conditions already pass. Stage 0 captures actual deployment facts; later gates prove the implementation. A failed gate stops rollout and requires correction, not a guessed value or a relaxed invariant. No remaining design question requires an answer before implementation can begin.

## Definition of completion

Migration is complete when the new controller has passed its cutover, each of the four flows and its supported update handler has passed isolated integration and recovery tests, the weekly schedule has completed four successful consecutive cycles, and the acceptance matrix in [operations](OPERATIONS.md) passes. A flow with no eligible production target is verified in the isolated VM and reports `NO_TARGET` on the host. Unsupported software remains visible with an explicit reason; it is never silently counted as maintained.
