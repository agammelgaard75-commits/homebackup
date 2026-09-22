# Multi-Agent AI Sysadmin Migration Plan

## Purpose

This directory describes a future migration of `/home/bot/sysadmin` from its
current monolithic Python controller to a coordinated, multi-component
framework. It is planning material only. It does not install software, change
the current controller, create users or services, alter timers, contact the AI
gateway, or write to Splunk.

The existing sysadmin remains the production implementation until a separate,
explicitly approved cutover change is prepared, tested, and executed.

## Design position

The new framework uses agents only where judgment adds value. Deterministic
code remains responsible for scheduling, lifecycle state, policy enforcement,
approved command execution, verification calculations, record persistence, and
Splunk delivery.

There is one lifecycle orchestrator and only one mutating executor. Preparation
and review roles are read-only. No agent can submit arbitrary shell commands for
execution.

## Documents

- `01-current-system.md` inventories the reusable implementation and identifies
  current concerns that the migration must preserve or resolve.
- `02-target-architecture.md` defines components, trust boundaries, and data
  flow.
- `03-agent-responsibilities.md` defines each agent or deterministic worker,
  including permissions and prohibited behavior.
- `04-lifecycle-and-contracts.md` defines lifecycle states, artifacts, handoff
  contracts, locking, idempotency, and failure behavior.
- `05-migration-roadmap.md` gives a staged path from monolith to the new
  framework without allowing two executors to maintain the host.
- `06-safety-verification-and-operations.md` defines safety controls, test and
  acceptance gates, observability, rollback, and operator procedures.
- `07-reuse-map-and-decisions.md` maps existing files/functions to the future
  components and records decisions that must be made before implementation.

## Non-goals for this planning package

- No implementation or proof of concept.
- No modification of `/home/bot/sysadmin`.
- No systemd, Splunk, package, container, account, permission, or network
  changes.
- No Ubuntu release upgrade, reboot, package removal, or major version upgrade.
- No decision to decommission the existing controller.

## Proposed future repository name

The implementation can eventually live in a separate repository such as
`/home/bot/ai-sysadmin-multi-agent`. This planning directory must not be treated
as that implementation or installed directly.
