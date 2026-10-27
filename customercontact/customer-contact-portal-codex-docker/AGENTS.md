# Codex agent instructions

## Mission and scope
Build a maintainable, secure **internal customer contact portal** according to README.md and docs/*.md. This is a modular monolith, not a suite of microservices. Work on only the phase requested by the user. Do not silently implement future phases.

## Before editing
1. Read README.md and docs/*.md relevant to the task.
2. Inspect existing code and tests.
3. State the intended files/areas to change and important assumptions.
4. Preserve existing behavior unless task explicitly changes it.

## Git checkpoints
- Use Git commits as source-code checkpoints. Inspect status and recent commits before starting a phase; reuse an existing verified commit or tag as the rollback point instead of copying the source tree.
- After each completed and verified phase, commit its source, migrations, tests, and documentation with a descriptive message. Keep the working tree clean between phases.
- Do not accumulate backup copies of source files or create redundant rollback directories when Git already provides a suitable checkpoint. Never rewrite history or delete backups, stashes, or snapshots without explicit review and approval.
- Check `git rev-parse --show-toplevel`: the Git root may be above this portal directory. Stage only portal paths and inspect the staged names before committing so sibling projects stay untouched. Never commit passwords, secrets, `.env` files, database contents or dumps, Docker volume data, logs, or other runtime data, even if a Git ignore rule is missing.
- Git protects source history, not PostgreSQL data or the Caddy private CA. Preserve named volumes and use the documented backup-first update process for database changes.

## Coding conventions
- Keep each feature's models, forms, views, URLs, templates, and tests in its own Django app.
- Use Django ORM and migrations; do not invent raw SQL CRUD infrastructure.
- Prefer small, readable functions/classes to abstraction frameworks.
- App-to-app writes must go through owning app's documented service layer functions.
- JSON imports belong to `customers.imports` and `contacts.imports`; `core.json_import` owns only upload, signed preview and reference download mechanics. Confirmed imports must use owning-app write services and keep audit writes inside the same transaction.
- Do not move unrelated code or refactor modules not required by the current task.
- Avoid new dependencies unless justified and locked.
- Do not create placeholder code or empty files merely to look architectural.
- Use type hints when useful; descriptive names; no hidden business rules in signals.

## Security and privacy
- Every data-facing view requires authentication. Check Viewer/Editor/Administrator permissions server-side.
- Never log credentials, contact emails, contact phone numbers, or customer notes.
- Never commit production secrets, real customer data, `.env`, or database dumps.
- Keep protection against CSRF, injection, unsafe rendering and overly broad administration privileges.
- Ensure customer/contact relationship consistency across inputs, service functions and tests.
- No outbound API calls or external AI processing of customer data without explicit approval.
- Do not expose Docker PostgreSQL ports publicly.

## Data and schema
- Business changes must use migrations and include tests of integrity constraints/validation.
- Preserve historical assignments; archive instead of destructive deletes in main UI.
- Avoid changing existing schemas without documenting how current data will migrate.

## Docker-first contract
- **Everything running in production MUST run through `compose.yaml`**: Caddy HTTPS proxy, Django/Gunicorn app, and PostgreSQL; feature modules remain separate Django apps in the single application image, NOT separate microservices.
- Read `docs/DOCKER_OPERATIONS.md` before editing deployment files. Keep `scripts/install.sh`, `update.sh`, `backup.sh`, `restore.sh`, `test.sh` working.
- No software installation on the production host except Docker Engine, Compose plugin and required host utilities. Do not introduce separate host-side cron jobs for Django tasks; use explicit Compose commands or job containers.
- Keep only proxy ports 80/443 published. App/database are private; production HTTPS is mandatory.
- Database data and internal CA data must survive container replacement via named volumes. NEVER invoke `docker compose down -v` or `docker volume prune` as a routine action.
- Never automatically generate migrations or run unsafe/destructive data migration on every app start. Migrate explicitly in install/update flow with backup-before-update.
- Keep build-time static collection free of database access, and running image free of unnecessary filesystem writes.
- For backup, update, and restore changes, validate shell scripts and failure behavior. Test restore in an isolated environment.
- Do not silently add runtime services, change pinned image major versions or auto-update on server.

## Verification
- Run all affected tests and available system checks after changes.
- If Docker is unavailable, report that explicitly and test locally as far as possible.
- Include tests for unauthenticated access, insufficient privileges, valid forms, invalid inputs, and model relationships.
- Do not claim tests passed unless they ran.

## Final report after each task
Provide: (1) what changed, (2) key files, (3) commands/tests and observed results, (4) known limitations, (5) a single suggested next phase. Do not claim deployment occurred unless verified.

## Production maintenance
- Preserve the verified Git checkpoint and existing private configuration before changes. Make a final commit after tests; create a release tag only when its documented critical acceptance checks pass. Never claim live Keycloak or production deployment was tested without evidence.
- Production commands must use scripts/compose.sh (compose.yaml plus compose.production.yaml); local-auth development uses a separate project/env/volumes and DEPLOYMENT_MODE=development. Never downgrade production authentication to make a test pass.
- Keep application and base-image versions/digests explicit. Review dependency/container advisories on every release; document unfixed findings and applicability. Do not auto-upgrade database majors.
- Rehearse install, update, persistent restart, backup and restore on disposable isolated data. Keep shell failure tests and all Django regressions passing. Never use the working database as a restore target.
- Keep scripts non-destructive by default. No volume/image/backup pruning, implicit database rollback or source-copy rollback directories. Backups and versioned Git/images have separate recovery roles.
- Update permanent operating guides and regenerate Production/ using scripts/package-production.sh. Production must contain only allowlisted source/configuration and current documentation, never AGENTS, planning prompts, secrets, runtime files or historical phase notes. Verify bundle/source parity and its standalone build.
