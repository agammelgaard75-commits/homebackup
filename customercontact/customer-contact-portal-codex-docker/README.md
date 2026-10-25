# Customer Contact Portal

An internal staff portal built as a Django modular monolith with PostgreSQL and Caddy HTTPS. **Phases 1–5 and the Phase 5B extension are implemented.** Customer, contact and service management, global search, transactional audit history and a unified customer directory are available.

The foundation includes staff login/logout, a responsive home page, a custom User model, Viewer/Editor/Administrator groups, restricted Django user administration, database-aware health checks, and Docker installation/maintenance scripts. There is no public registration.

Customer management includes a searchable, paginated directory, company identifiers, optional addresses and internal notes, detail/create/edit pages, and reversible archiving. Viewer can read; Editor and Administrator can maintain customers. Open `/customers/` after signing in.

Administrators can import UTF-8 JSON at **Customers → Import JSON** (`/customers/import/`) and **Contacts → Import JSON** (`/contacts/import/`). Import customers first, because contact files refer to customer `import_id` values. Each screen provides a fake-data example, JSON Schema and [format guide](docs/JSON_IMPORT_FORMAT.md). Upload a file, review create/update/unchanged/reject rows, explicitly map possible existing records by UUID when needed, then confirm the entire file. Repeat imports use stable keys; omitted fields and existing contact methods/associations are retained. Imports are transactional and audited. Do not upload real data to a public or unapproved environment.

The versioned [REST API](docs/REST_API.md) exposes portal records, search, imports and audit at `/api/v1/`. Administrators can open its OpenAPI/Swagger documentation and the two-stage **Data Cleanup** screen from Administration. Cleanup permanently deletes only selected archived records after dependency preview and confirmation; verify a database backup first.

Optional [Keycloak OIDC integration](docs/KEYCLOAK_OIDC.md) supports browser SSO and Keycloak bearer access tokens while `AUTH_MODE=local` remains the default. OIDC links users by issuer and subject, maps portal client roles to existing permissions, and requires a separately tested Keycloak setup before activation.

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
- `apps/contacts/`: named people and general contacts, multiple email/phone details, validation, primary selection, search and archive/restore.
- `apps/services/`: central catalog, customer service agreements, status/date validation, permissions and retained history.
- `apps/search/`: permission-scoped global search and grouped pagination.
- `apps/audit/`: transactional metadata-only history, global audit and customer Activity.
- `apps/api/`: versioned JSON endpoints, scoped credentials, pagination and OpenAPI definitions.
- `apps/cleanup/`: administrator-only preview and explicit permanent deletion of eligible archived records.
- `compose.yaml`, `Dockerfile`, `deploy/Caddyfile`, `scripts/`: the three-container deployment and operational contract.
- [Architecture](docs/ARCHITECTURE.md), [product specification](docs/PROJECT_SPEC.md), [data model](docs/DATA_MODEL.md), [implementation plan](docs/IMPLEMENTATION_PLAN.md), [Docker operations](docs/DOCKER_OPERATIONS.md).

Review Phase 5 before separately requesting the Phase 6 production-readiness checkpoint. Production readiness, offsite backups, network restrictions and managed TLS trust remain the separately approved Phase 6 checkpoint. Do not import real personal data or expose this portal publicly before that review.

## Updating an existing Phase 1–4 installation

Run `./scripts/update.sh` (with `sudo` if needed). It backs up the database, builds the application, explicitly applies the additive customer, contact, service and audit migrations, reconciles group permissions, checks deployment settings, and restarts the stack. Existing accounts, memberships and credentials remain intact. Run `./scripts/test.sh` to verify all implemented phases.

Customers default to Active in the directory. Select Archived or All statuses to find archived records. A name is required; the CVR / company ID is optional and unique when supplied. Use the detail page's Archive action to retain a record, or edit its status to reactivate it. Contacts and Services are available from each customer. See [customer data rules](docs/DATA_MODEL.md#phase-2-customer-implementation) and the [module service API](docs/ARCHITECTURE.md#customer-module-write-api-phase-2).

Verification evidence: [Phase 1](docs/PHASE1_VERIFICATION.md), [Phase 2](docs/PHASE2_VERIFICATION.md), [Phase 3](docs/PHASE3_VERIFICATION.md), [Phase 4](docs/PHASE4_VERIFICATION.md), [Phase 5](docs/PHASE5_VERIFICATION.md), [Phase 5B](docs/PHASE5B_VERIFICATION.md), and the [contact-unification correction](docs/CONTACT_UNIFICATION_VERIFICATION.md).

## Working with contacts

Open a customer and choose **Contacts**. A new named or general contact needs a name and at least one valid email address or phone number. Name and Email are the first fields on the create form; Email may be blank when a phone number is entered below. Contact type defaults to Technical. The create and edit form supports multiple labeled details in one save; blank rows are ignored, and **Archive this detail** removes an existing detail from the active set. Job title, department, type and notes are optional. Use the same pages to edit, archive or restore people and details. Selecting Primary replaces the current primary of that kind for the same owner; email and phone have separate primary choices. The last active email or phone cannot be archived until another method is added.

For a shared address or reception number, add a normal contact such as **Support Desk** or **Reception** and select **General contact**. Enter its email addresses and phone numbers on the contact form or add more from its detail page. The customer Overview and Contacts tab show these same records; there is no separate company email/phone editor. Search a customer's contacts by name, email or phone; switch to Archived or All statuses to include archived records. Archive preserves records and relationships. Older contacts with no active method remain viewable; add a valid email or phone before saving an edit.

Use **Contacts** in the main navigation for a global directory. It searches people by name, job title, email, phone or associated customer, with status and type filters. Editors can create a contact with one or more customers and edit its customer selections later. Customer selections show active customers by default; choose **Include archived customers** to load older records. Removing a selection archives only that association; the person, notes and contact details stay intact. Existing customer-scoped URLs continue to work for active associations.

The contact-unification migration attaches older personless company email/phone entries to one general contact per affected customer, retaining each detail's ID, value, status and timestamps. Apply it through the existing backup-first `./scripts/update.sh` flow. Old general-detail GET links redirect to the resulting contact detail actions; new email/phone entries require a contact.

## Working with services

Open **Services** in the main navigation to browse the central catalog. Administrators can create/edit services and archive/restore them. Names are unique ignoring case and surrounding spaces, including archived names. Description and category are optional. The catalog shows active services by default and supports search, status/category filtering and pagination. Open a service to see its customers and agreement history; inactive agreements and archived customers require an explicit filter.

Open a customer's **Services** tab to add or edit an agreement. Editors and Administrators can assign active catalog services, including multiple agreements for the same service/customer. Each agreement has its own UUID, optional dates/notes, and Active, Suspended, Expired or Terminated status. End date cannot precede start date. Customer and service links are fixed after creation; create another agreement to change them. Terminate retains the record, and editing status can reactivate it.

Status is maintained manually; dates never trigger automatic changes. Archiving a catalog service blocks new assignments while retaining existing agreements and their statuses. Customer Overview counts active agreements, including those referencing archived catalog entries. Viewer has read-only access. No service names are seeded or hardcoded; no billing or external integrations are included.

## Search, activity and customer directory

Use **Search** in the main navigation for partial, case-insensitive customer names/company IDs, contact names/job titles/emails/phones, catalog names/descriptions and customer service agreements. General contacts appear in the Contacts group. Results are grouped by Customers, Contacts and Services with independent pagination. Active records are the default; choose **Include archived records and inactive agreements** to search history. Only records allowed by your existing read permissions are searched. Formatting is removed for phone comparison without guessing country codes.

Use **Search By Service** in the main navigation to open `/search/by-service/` and select one or more catalog entries. ANY finds customers with at least one selected service; ALL requires every selected service. Active catalog services, assignments, customers and contacts are the defaults; separate checkboxes expand each scope. The paginated table includes each matching customer/contact association and customers without contacts. **Copy All Emails** collects distinct addresses from active named and general contacts of all matching active customers across every result page. It excludes archived contacts/customers even when those are displayed. If browser clipboard access fails, a selectable field appears.

Home shows one row per active customer with direct links to all associated current contacts and active assigned catalog services. Search separately by customer name, contact name/email or service name; select multiple services, sort by customer name and page through the results. Archived customers, archived contacts and inactive agreements/catalog services require explicit filters. The home table is scoped to each user's read permissions. The old dashboard counters and recently updated lists have been removed from Home. Customer tabs consistently expose **Overview**, **Contacts**, **Services** and **Activity** according to read permissions. The customer Overview links directly to every associated current contact and every current service, without a preview limit. Its two filters can show archived contacts and all assigned services, including historical agreements and archived catalog entries.

Customer, contact and catalog service details now include editable sections for staff with the relevant permission. Customer details also let authorized staff add contacts, edit an associated contact's emails, phones and customer links, assign services and update existing service agreements. The older edit URLs remain available for saved links. Invalid inline edits retain their entered values and display errors on a detail page; all writes continue through the existing validated, audited handlers.

List selections such as status, type, sort order and service choices are remembered per page in the existing secure session cookie. Reset clears the page's choices. Free-text searches, contact details and notes are not stored as preferences. Direct links to archived records remain usable for authorized staff, and the read-only audit history remains complete.

Customer **Activity** is read-only for authorized customer readers. Administrators can open **Audit history** from Search. Filter by UTC dates, responsible user and action. Events contain action metadata, object IDs and changed field names, not copied contact values or notes. The audit event and business change are saved in one transaction; an audit failure prevents the change. History starts with Phase 5 and does not reconstruct earlier actions. Archive retains records and events; no audit-edit/delete controls exist.
