# Reuse Map and Open Decisions

## Existing-to-target reuse map

| Existing asset | Future owner | Migration treatment |
| --- | --- | --- |
| `Controller.inspect` and `software_inventory` | Collectors | Extract with behavior-preserving tests; keep command evidence and error semantics. |
| `Controller.blockers` | Policy gate | Preserve deterministic authority; assign stable rule IDs. |
| `Controller.plan` | Plan builder + preparation agent adapter | Separate trusted action construction from untrusted AI assessment. |
| `scripts/litellm_planner.py` | Preparation agent adapter | Reuse API/auth/timeout behavior; add versioned request/response schemas and retain strict output validation. |
| `Controller.prepare` | Orchestrator + change writer | Split lifecycle/state decisions from deterministic record rendering without changing idempotency. |
| `upgrade_candidates` and `approved_upgrade` | APT catalogue handler | Reuse simulation, pinning, and refusal rules; do not rewrite during initial extraction. |
| `Controller.command` | Executor + event writer | Preserve argv-only execution, timeouts, dry-run skipping, output capture, redaction, and auditing. |
| `Controller.verify_software` | Verification worker | Reuse expected-versus-actual checks and expand contract tests. |
| `Controller.close` | Finalizer | Preserve atomic terminal update; separate status calculation from optional AI prose. |
| `ContainerMaintenance.inspect/plan/validate` | Container collector/policy | Extract read-only stages first and preserve all deferral rules. |
| `ContainerMaintenance.apply` | Container catalogue handler | Keep exact digest, backup, single-service replacement, and readiness behavior. |
| `Controller.event` | Event writer | Centralize as append-only structured logging; preserve current files/sourcetypes initially. |
| `atomic_write` and controller lock | State store/orchestrator | Reuse as foundational durability and concurrency controls. |
| `scripts/render_deployment.py` | Deployment renderer | Extend deterministically for new units and dashboards; retain repeatability tests. |
| `scripts/install.sh` | Installer | Adapt only after runtime parity; retain no-auto-enable/no-restart behavior. |
| `systemd/*.service` and `*.timer` | Scheduler | Render new units but never enable alongside old production executor units. |
| `splunk/*.xml` and app assets | Observability | Reuse existing sourcetypes/searches; introduce additive component fields. |
| `tests/` | Regression suite | Run unchanged where possible; layer component, contract, parity, and fault tests on top. |
| `IGNORE.md` contract | Policy input | Preserve strict parsing, digest binding, visibility, and post-prepare drift rejection. |

## Tools to reuse

The future framework should continue using the existing host-native tools rather
than introduce alternate package or container managers:

- APT tools (`apt-get` transaction refresh/simulation/exact upgrade) and
  `dpkg-query` / `dpkg --audit`.
- `systemctl` for inspection and systemd for scheduling/oneshot isolation.
- Filesystem and `/proc`/OS facts currently used for health checks.
- Splunk manifests and the existing local file-monitoring app/dashboard assets.
- Snap and system Flatpak inventory when those managers exist.
- Docker CLI, Buildx image metadata, and Docker Compose for explicitly configured
  container services.
- The authenticated local LiteLLM adapter and configured model, with no model
  download performed by the framework.
- Python standard-library implementation patterns currently used for TOML,
  subprocess control, JSON, hashing, file locks, atomic writes, and HTTP calls.

Exact executable paths, supported versions, and timeout values must come from the
reviewed configuration/catalogue, not AI output.

## Decisions required before implementation

1. **Cadence:** weekly as policy states, or retain the currently configured daily
   cadence? Make this a separate approved operational decision.
2. **Repository and installation names:** choose names that cannot collide with
   `/opt/ai-sysadmin`, `/etc/ai-sysadmin`, existing units, or production state
   during shadowing.
3. **Artifact compatibility:** preserve v1 paths in place at cutover or perform a
   one-time copy/migration with manifest and rollback?
4. **AI roles:** require AI only for preparation, or also use it for closure prose?
   Deterministic closure fallback is required either way.
5. **Approval:** is preparation-agent approval sufficient under current policy,
   or must a human approve certain risk labels before execution?
6. **Privilege model:** retain root oneshots for parity initially, then split
   privileges, or design helper capabilities before shadow testing?
7. **Event schemas:** extend current sourcetypes with additive fields or create
   versioned sourcetypes and transition dashboards?
8. **Retention:** define retention for evidence, action receipts, container
   backups, old framework artifacts, and Splunk indexes. No autonomous deletion
   is included in this plan.
9. **Plan lifetime:** retain the current 48-hour expiry for the chosen schedule?
10. **Container scope:** carry currently configured services into the first
    cutover or defer mutating container support until APT-only parity is proven?
11. **Shadow duration:** define how many consecutive preparation and maintenance
    windows must agree before canary cutover.
12. **Operator ownership:** identify who can approve cutover, review failure,
    create retry successors, and activate Splunk changes.

## Recommended initial answers

- Preserve current behavior during extraction and resolve cadence independently.
- Use local process/file contracts, not a message broker.
- Keep AI required only for preparation at first; make closure AI optional.
- Retain one root executor and keep all other roles read-only.
- Preserve current state/log paths at final cutover, but use completely separate
  shadow paths beforehand.
- Prove APT lifecycle parity first; add mutating container execution only after
  its own shadow and canary gates.
- Extend current Splunk events additively and include `implementation`,
  `component`, `phase`, `schema_version`, and stable `event_id` fields.
