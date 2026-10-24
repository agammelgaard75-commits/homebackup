# Customer Contact Portal

An internal staff portal built as a Django modular monolith with PostgreSQL and Caddy HTTPS. **Phases 1–3 are implemented.** Customer and contact management are available. Services, global search and audit remain future phases; their Django apps are registered without business models or routes.

The foundation includes staff login/logout, a responsive home page, a custom User model, Viewer/Editor/Administrator groups, restricted Django user administration, database-aware health checks, and Docker installation/maintenance scripts. There is no public registration.

Customer management includes a searchable, paginated directory, company identifiers, optional addresses and internal notes, detail/create/edit pages, and reversible archiving. Viewer can read; Editor and Administrator can maintain customers. Open `/customers/` after signing in.

## Run with Docker

Only Docker Engine, Docker Compose v2 or later, Bash and standard Linux utilities are required on the host. No host Python, PostgreSQL or web server is needed. Use a Docker-authorized account (or `sudo` for these commands). Review [Docker operations](docs/DOCKER_OPERATIONS.md) before installation.

On a **clean, authorized internal test host**, configure DNS and ensure ports 80/443 on the selected bind address are free:

```bash
./scripts/install.sh portal.home.lab
docker compose exec app python manage.py createsuperuser
docker compose cp proxy:/data/caddy/pki/authorities/local/root.crt ./portal-root-ca.crt
```

Trust the exported **public** Caddy root certificate on managed clients, then visit `https://portal.home.lab/`. Do not distribute the CA private key. In Administration, create staff accounts and assign one of the three groups. Initial superusers can bootstrap access; ordinary Administrators cannot grant superuser privileges or modify superuser accounts. A role alone enables the appropriate portal access; `is_staff` alone does not.

The installer generates private `.env` secrets and retains them on reruns. It runs migrations and `setup_roles` explicitly. Normal container startup never generates or applies migrations. Use `update.sh` for later code/schema changes so a backup precedes migrations. Do not deploy existing installations using the installer as an update shortcut.

## Isolated local review

In a separate checkout with **no existing `.env`**, choose a unique project name and loopback binding:

```bash
COMPOSE_PROJECT_NAME=portal-phase1-review PORT_BIND_IP=127.0.0.1 \
  ./scripts/install.sh portal.phase1.localhost
```

These values are saved in `.env`; subsequent commands target the same project and its own named volumes. With sudo, use `sudo env COMPOSE_PROJECT_NAME=portal-phase1-review PORT_BIND_IP=127.0.0.1 ./scripts/install.sh portal.phase1.localhost` on first installation. Map `portal.phase1.localhost` to `127.0.0.1` if your local resolver does not support `.localhost`. Trust the exported CA and open `https://portal.phase1.localhost/`. Only proxy ports 80/443 are published, on loopback. If occupied, report/resolve the conflict without stopping another application.

Development uses the same Docker/PostgreSQL/HTTPS stack and production security settings. Rebuild after source changes; no host development server is required. Never use real customer data in this environment.

```bash
./scripts/test.sh                    # Django checks, migration drift, tests
./scripts/tests/operations.sh        # shell failure paths with a fake Docker command
./scripts/backup.sh                  # private PostgreSQL dump under backups/
./scripts/status.sh
# Destructive: rehearse ONLY against disposable data in the isolated test stack.
./scripts/restore.sh backups/<chosen-backup>.dump
# Existing installation; preserves database, configuration, and Caddy CA:
docker compose up -d --wait
# Stop without deleting volumes:
docker compose down
```

`/health/` returns only `{"status":"ok"}` (200) or `{"status":"unavailable"}` (503), depending on database connectivity. Anonymous requests to the home page redirect to login; authenticated accounts without access receive 403. Customer views and writes enforce model permissions as well as the existing role gates.

## Project map

- `config/`: environment settings, URLs, WSGI/ASGI.
- `apps/accounts/`: custom user, roles, restricted user administration, login/logout and tests.
- `apps/core/`: shared layout, home page, health endpoint, safe logging and tests.
- `apps/customers/`: customer model, forms, service API, directory, detail/edit/archive pages, read-only admin, migration and tests.
- `apps/contacts/`: people, multiple email/phone details, general customer details, validation, primary selection, search and archive/restore.
- `apps/services/`, `search/`, `audit/`: future feature app registrations.
- `compose.yaml`, `Dockerfile`, `deploy/Caddyfile`, `scripts/`: the three-container deployment and operational contract.
- [Architecture](docs/ARCHITECTURE.md), [product specification](docs/PROJECT_SPEC.md), [data model](docs/DATA_MODEL.md), [implementation plan](docs/IMPLEMENTATION_PLAN.md), [Docker operations](docs/DOCKER_OPERATIONS.md).

Review Phase 3 before requesting Phase 4 (Service catalog and assignments). Production readiness, offsite backups, network restrictions and managed TLS trust remain the separately approved Phase 6 checkpoint. Do not import real personal data or expose this portal publicly before that review.

## Updating an existing Phase 1 or 2 installation

Run `./scripts/update.sh` (with `sudo` if needed). It backs up the database, builds the application, explicitly applies the additive customer and contact migrations, reconciles group permissions, checks deployment settings, and restarts the stack. Existing accounts, memberships and credentials remain intact. Run `./scripts/test.sh` to verify all implemented phases.

Customers default to Active in the directory. Select Archived or All statuses to find archived records. A name is required; the CVR / company ID is optional and unique when supplied. Use the detail page's Archive action to retain a record, or edit its status to reactivate it. Contacts are available from each customer; services are not yet available. See [customer data rules](docs/DATA_MODEL.md#phase-2-customer-implementation) and the [module service API](docs/ARCHITECTURE.md#customer-module-write-api-phase-2).

Verification evidence: [Phase 1](docs/PHASE1_VERIFICATION.md), [Phase 2](docs/PHASE2_VERIFICATION.md), and [Phase 3](docs/PHASE3_VERIFICATION.md).

## Working with contacts

Open a customer and choose **Contacts**. Add a person with only a name, then add as many labeled email addresses and phone numbers as needed from that person's page. Job title, department, type and notes are optional. Use the same pages to edit, archive or restore people and details. Selecting Primary replaces the current primary of that kind for the same owner; email and phone have separate primary choices.

Use **Add general detail** on the customer Overview or Contacts page for a company address or reception number with no person attached. Search a customer's contacts by name, email or phone; switch to Archived or All statuses to include archived people and general details. Archive preserves records and relationships. These features use the existing Viewer/Editor/Administrator permissions and require no JavaScript or new runtime dependency.
