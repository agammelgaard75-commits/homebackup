# Codex implementation plan

**Rule:** One phase per Codex task. Never interpret the whole design pack as authorization to build everything at once.

## Phase 1: Foundation
Deliver:
- Django project and apps corresponding to documented module layout.
- Use/review the pinned `requirements.txt` and existing `.env.example`, then implement Django settings and project source.
- Make **existing Dockerfile, compose.yaml, Caddyfile and scripts/** operational without requiring host-side Python or PostgreSQL. Containers: `proxy`, `app`, `db` with persistent named DB and Caddy CA volumes.
- Configure Django WhiteNoise static serving, HTTPS proxy handling, secure cookies and Django health check. Do not publish app/database ports.
- Shared base template/navigation, basic responsive CSS.
- Custom User model, login/logout, staff roles and role initialization mechanism.
- Health endpoint, safe development settings and README startup commands.
- Small test suite for login-required navigation and role checks.

Exit criteria: `./scripts/install.sh portal.home.lab` starts all three healthy containers with an internal TLS certificate; DB connects, committed migrations succeed, create-superuser flow works, anonymous users cannot view the portal, tests pass, `./scripts/backup.sh` creates a dump, and a restore is rehearsed in an isolated test stack. Explicitly report if Docker runtime tests are unavailable.

## Phase 2: Customers
Deliver:
- Customer model, migration, admin registration.
- Customer list, add, edit, archive and detail overview.
- Search/filter/pagination on customer list, role authorization and tests.

Exit criteria: Editor can manage customer data; Viewer only reads; unauthorized POST requests are refused.

## Phase 3: Contacts and contact points
Deliver:
- Contact/ContactPoint models, migrations, forms, customer Contacts tab.
- Multiple emails and phones per contact and company-level contact points.
- Roles, primary flags, normalization/search fields, archive and tests.

Exit criteria: Two distinct phone numbers and emails can be saved to one contact; company-level general addresses work; no mismatched customer/contact relationship is allowed.

## Phase 4: Service catalog and assignments
Deliver:
- Service and CustomerService models, migrations, assignment UI, status/date validation.
- Services tab on customer, catalog listing and admin-only maintenance.
- Tests for duplicate assignments, role restrictions, invalid dates and retired catalog entries.

Exit criteria: A customer can have multiple services; service states display clearly, and ended records are preserved.

## Phase 5: Search, audit, polish
Deliver:
- Global search across customer/contact/contact point/service.
- Audit events on mutation operations and customer Activity tab.
- Responsive polishing, helpful empty states, accessibility/keyboard tests.
- Integration tests of add customer -> add contacts -> assign service -> search -> audit.

Exit criteria: End-to-end core workflow works and passes tests without manual database edits.

## Phase 5B: Service-based contact search and shared contacts
Deliver:
- Dedicated multi-service ANY/ALL search over customer/contact associations, default active filters, pagination and distinct email collection across the full result set.
- Global Contacts directory and contact forms that manage one or more customer associations.
- Additive association backfill before relying on the new relationship, with transactional metadata-only association audit events.
- Dashboard active-contact regression coverage, retained customer-scoped URLs and Docker-only verification.

Exit criteria: Existing contacts and points survive the migration unchanged; all old and new tests pass; Viewer can read/search/copy while Editor and Administrator can manage associations; the isolated Docker stack stays healthy across recreation.

## Phase 6: Production-readiness checkpoint (separate approval)
Deliver:
- Security review, verify Caddy internal TLS trust for managed clients, production settings, firewall and DNS configuration, backup/restore rehearsal, offsite backups, secrets handling, deployment checklist.
- Demonstrate fresh install on another Linux Docker host with documented commands, safe upgrade procedure, and persistence after container recreation.
- Do not put the app on the public internet or import real personal data before this checkpoint is approved.

## First Codex task (copy/paste)
```text
Read README.md, AGENTS.md and all documentation under docs/ before editing.
Implement Phase 1 only from docs/IMPLEMENTATION_PLAN.md.
Use the architecture and module ownership described in docs/ARCHITECTURE.md.
Read docs/DOCKER_OPERATIONS.md and honor the existing Dockerfile, compose.yaml,
deploy/Caddyfile, .env.example and scripts/*.sh as the deployment contract.
Provide a working Docker-only Phase 1, with a healthy app, proxy and DB.
Do not implement customer, contact, or service features yet.
Before coding, summarize your planned file changes and major assumptions.
Then implement them, run migrations, tests and available static checks.
Conclude with: files changed, commands executed, results, limitations, and one recommended next step.
Do not connect to external systems or deploy anything.
```

## Suggested subsequent tasks
- `Implement Phase 2 only, following AGENTS.md and all docs. Verify roles and tests.`
- `Implement Phase 3 only. Emphasize multiple contact points and relationship validation.`
- `Implement Phase 4 only. Allow separate agreements for the same customer/service, enforce valid dates, and test permissions.`
- `Implement Phase 5 only. Add search, audit and end-to-end tests.`

## Verification commands (everything must run in containers)
- Django system check: `docker compose run --rm app python manage.py check`
- Schema migration check: `docker compose run --rm app python manage.py makemigrations --check --dry-run`
- Test suite: `docker compose run --rm app python manage.py test`
- Compose validation: `docker compose config --quiet`
- Initial install (after Phase 1 implementation): `./scripts/install.sh portal.home.lab`
- Maintenance verification: `./scripts/backup.sh` and an isolated test restore.
- Manual browser smoke test with Viewer, Editor, Administrator.
