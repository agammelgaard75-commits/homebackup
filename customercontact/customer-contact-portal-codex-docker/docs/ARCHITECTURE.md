# Technical architecture

## Why a modular monolith?
Each business area has its own source, database models, URLs, forms, templates, and tests, but deployment stays simple: one Django web app + one PostgreSQL database + one HTTPS entry-point container. There is no benefit to splitting a small internal directory into microservices.

## Technology
- Python supported by the selected, maintained Django release; lock dependency versions.
- Django framework, Django template rendering, plain CSS, and small amounts of JavaScript only where clearly useful.
- PostgreSQL for persistent records.
- pytest + pytest-django (or Django's built-in test runner, consistently across project).
- Docker Compose services: `proxy` (Caddy, HTTPS), `app` (Django+Gunicorn/WhiteNoise), `db` (PostgreSQL). Private networks and named database/TLS volumes; configuration via `.env` generated during install.
- Both development/verification and production MUST be Docker-based. Production WSGI process is Gunicorn served through the included Caddy container with `tls internal`. No additional host nginx required.

## Suggested repository layout
```text
customer-contact-portal/
├── AGENTS.md
├── README.md
├── requirements.txt              # pinned baseline, kept current intentionally
├── .env.example
├── .gitignore
├── Dockerfile
├── compose.yaml
├── deploy/Caddyfile
├── scripts/                      # install, backup, update, restore, test, status
├── manage.py
├── config/                       # Django settings, root URLs, WSGI/ASGI
├── apps/
│   ├── core/                     # base layout, shared components, health check
│   ├── accounts/                 # custom User model, role helpers
│   ├── customers/                # customer entity and customer pages
│   ├── contacts/                 # people and contact details
│   ├── services/                 # service catalog and customer assignments
│   ├── search/                   # read-only cross-module search
│   └── audit/                    # business change history
├── static/                       # shared CSS/icons
├── docs/
└── tests/                        # cross-module/integration tests
```

Each feature app owns a similar internal layout:
```text
apps/contacts/
├── apps.py
├── models.py
├── forms.py
├── views.py
├── urls.py
├── services.py                  # write operations/business rules
├── selectors.py                 # reusable queries, optional if justified
├── admin.py
├── migrations/
├── templates/contacts/
└── tests/
```

Do **not** generate empty modules just for symmetry. Add `services.py` or `selectors.py` when needed.

## Module boundaries
- `customers` owns Customer lifecycle and customer detail shell.
- `contacts` owns Contact, ContactPoint, and their forms/actions.
- `services` owns Service and CustomerService assignments, including dates/status.
- `accounts` owns app user model, role setup and permission helpers; use built-in authentication.
- `search` may *read* other apps' models; should not edit their data.
- `audit` accepts structured events from mutations but does not own business records.
- `core` provides shared UI and infrastructure; must not become a dumping ground for business logic.
- Cross-module writes go through the owning app's public service functions; no surprise cross-app callbacks/signals.
- Cross-module database foreign keys are allowed in this modular monolith; avoid circular imports.

## HTTP / UI architecture
- Server-rendered HTML. Use Django forms for create/edit.
- URL patterns grouped by app, namespaced, no invented REST API until one is needed.
- Customer detail shell renders contact/services data via documented queries and includes module-owned partial templates.
- List pages are paginated, with server-side filters and permission checks.

## Authorization and data protection
- Custom application User model extending Django's standard AbstractUser, declared before first migration. Groups: Viewer, Editor, Administrator.
- View permissions separate from change permissions. Check access in views/actions and use safe form validation.
- No public route to customer data; login required, including search and autocomplete.
- Store only needed personal information. Mask sensitive values in application logs; audit metadata rather than full value snapshots.
- Escape rendered user data using templates; maintain CSRF defenses.
- Use environment secrets, secure sessions/cookies, HTTPS in production, and sensible password handling.
- Apply retention/deletion policy before rollout; use archive first in the UI.

## Observability
- Structured application logs without email/phone values by default.
- `/health/` health endpoint that exposes no sensitive data.
- Audit event fields: actor, action, object type/id, customer, UTC timestamp, safe description and changed field names.

## Deployment
- Self-contained `compose.yaml` deployment contract: **3 containers**, only ports 80 and 443 published via Caddy; persistent PostgreSQL and TLS CA volumes.
- Codex Phase 1 must implement the Django code expected by the provided Dockerfile and the health endpoint expected by Compose.
- `scripts/install.sh` produces secrets, builds images, migrates explicitly and starts the stack. `scripts/update.sh` backs up then migrates; backup/restore scripts handle the persistent database safely.
- No migration on web container startup; no database major-version upgrades on a routine image pull.
- HTTPS is terminated by included Caddy's internal certificate authority; internal client browsers need to trust its public CA. See `docs/DOCKER_OPERATIONS.md`.
- Do not expose PostgreSQL/WSGI ports on the server. Restrict port 443 to internal/VPN networks.

## Customer module write API (Phase 2)

All application customer writes use `apps.customers.services`:

- `create_customer(*, actor, name, reference_code="", status="active", address="", notes="")`
- `update_customer(*, actor, customer_id, name, reference_code, status, address, notes)`
- `archive_customer(*, actor, customer_id)`

These functions require an active actor with `accounts.access_portal`, `accounts.edit_portal`, `customers.view_customer`, and `customers.add_customer` or `customers.change_customer` as appropriate. They enforce validation and transactions, lock rows during updates/archive, and translate an identifier uniqueness race into a validation error. Repeated archive calls do not delete data or change an already archived record's timestamp. They do not log input values. Phase 5 adds transactional metadata-only audit events as described below.

The customer UI owns forms and mutations; its read-only Django admin registration links to the customer pages. Viewer receives `view_customer`; Editor and Administrator also receive `add_customer` and `change_customer`. Managed roles never receive `delete_customer`. All customer routes enforce portal access and model permissions on the server, including direct POST requests. Customer responses disable caching.

`/customers/` defaults to active records, supports name/identifier search, Active/Archived/All status filters, name/recent-update sorting, and 25 records per page. Query parameters survive page navigation. Global cross-module search remains Phase 5.

## Contacts module (Phase 3)

`apps.contacts.services` is the public write boundary:

- `create_contact(actor, customer_id, full_name, job_title="", department="", contact_type="other", notes="")`
- `update_contact(actor, customer_id, contact_id, full_name, ...)`
- `set_contact_active(actor, customer_id, contact_id, is_active)`
- `save_contact_point(actor, customer_id, kind, value, contact_id=None, point_id=None, label="other", is_primary=False)`
- `set_point_active(actor, customer_id, point_id, is_active, contact_id=None)`

Arguments are keyword-only. Services require an active actor, portal access, customer-view and both contact-view permissions. Mutations additionally require portal-edit and the relevant add/change model permission. Replacing another primary also requires change-contactpoint permission. Managed Viewer has read grants; Editor and Administrator have add/change grants; no managed role gets delete grants. Admin inspection is read-only.

Services lock the owning customer row first to serialize writes/primary selection, but never modify customer records. They validate ownership on every call and preserve immutable owners; point updates cannot move a detail to another person or turn it into a general detail. Validation precedes primary demotion; all changes are atomic, and database uniqueness provides a final safeguard. No business rules run through signals.

Customer-scoped routes live under `/customers/<customer_uuid>/contacts/` and check the full customer/person/detail relationship before rendering or mutating. Contacts templates own both the standalone pages and the general-details partial included in customer overview. The customer view uses read-only selectors and hides contact information from users missing contact permissions. No reverse app-to-app writes are needed.

The customer Contacts page offers name/email/phone search, Active/Archived/All filters, and 25-person pagination with filter preservation. Email/phone search matches active details only; archived people can be found with the Archived filter, and archived individual details remain on the person's details page. General details use the same status/search filters. Cross-module global search remains Phase 5; services are implemented in Phase 4 below.

## Services module (Phase 4)

The keyword-only public write API in `apps.services.services` owns all catalog/assignment mutations:

- `create_service(actor, name, description="", category="")`
- `update_service(actor, service_id, name, description="", category="")`
- `set_service_active(actor, service_id, is_active)`
- `create_assignment(actor, customer_id, service_id, status="active", start_date=None, end_date=None, notes="")`
- `update_assignment(actor, customer_id, assignment_id, status, start_date=None, end_date=None, notes="")`
- `terminate_assignment(actor, customer_id, assignment_id)`

Catalog reads require portal access and `services.view_service`. Catalog writes additionally require portal-edit, portal-administration, and the relevant catalog add/change permission. Assignment reads require portal access, customer-view and both service model view permissions; mutations additionally require portal-edit and the relevant assignment add/change permission. Viewer reads; Editor manages assignments; Administrator also manages the catalog. No managed role receives delete permissions. Admin model registrations are read-only; GUI writes use the same public API.

All writes are transactional. Catalog writes lock catalog rows; assignment creation uses the same lock to serialize against catalog archive. Catalog uniqueness races become validation errors. Assignment updates/termination lock the assignment and scope lookup by customer ID. Neither writes to customer/contact records. Forms and model validation enforce content, immutable links and dates, with database constraints for name uniqueness, dates/status and protected foreign keys. A new agreement uses a separate UUID; no pair-uniqueness constraint exists.

Catalog routes are `/services/`; assignment routes are `/customers/<customer_uuid>/services/`. Lists and catalog customer usage use 25-row pagination. Catalog supports name/description/category search and status/exact-category filters; customer agreements support status filtering. Catalog detail includes historical customer agreements only when the user has all assignment read permissions. Read-only selectors supply the customer Overview's active agreement count. The contacts change is limited to adding a Services navigation link. No runtime architecture/dependency changes or JavaScript were introduced in Phase 4. Phase 5 adds search and transactional audit below.

## Search, audit and dashboard (Phase 5)

`apps.search` owns `/search/`, its form, selectors, view and template. Queries use parameterized Django ORM PostgreSQL case-insensitive substring comparisons and existing phone normalization. Results are grouped as Customers, Contacts (people and general details), and Services (catalog and agreements). PostgreSQL UNION queries paginate mixed groups in the database, ten results per group with independent page parameters. A person matching several details appears once. Archived records remain searchable; general detail links include a row anchor and the Contacts all-statuses filter. No external search engine, new extension, denormalized customer store or search write API is introduced. For this directory, substring search supports partial emails/phone numbers better than word-token full-text search; revisit indexing only after measuring real volume.

Read permissions are checked before adding each search query, including counts. Customer queries require customer-view. People/general details require the full contacts read gate. Catalog queries require service-view; agreements additionally require customer-view and assignment-view. Missing permissions omit a group or entity type. Search inputs are bounded, escaped on output and absent from application logs.

`apps.audit.services.record_change(actor, instance, before=None)` is the synchronous, keyword-only write boundary. Owning business services call `snapshot(instance)` before mutation and `record_change` after save, inside their existing atomic transactions. Snapshots are ephemeral. Only allowlisted changed field **names**, fixed descriptions, IDs, action, actor, related customer and UTC timestamp are persisted. No names, email/phone values, notes, before/after values, passwords or session data are copied into events. New records emit Created (Assigned for agreements); status changes emit Archived/Restored or Activated/Suspended/Expired/Terminated; other meaningful changes emit Updated. No-op operations do not emit events. Primary-detail replacement records both the demotion and new/changed primary. Audit failures propagate and roll back all business/audit writes in the same transaction; no deferred callbacks or signals are used.

All managed roles receive `audit.view_customer_activity`; that grant plus portal/customer-view permits `/customers/<uuid>/activity/`. Events are further filtered by the underlying contact/service model permissions, including actor-filter choices. Global `/audit/` requires portal access, portal-administration and `audit.view_auditevent`, assigned only to Administrators. It also respects underlying business read permissions. Both pages filter by inclusive UTC date range, user and action, sort newest first and paginate 25 events per page. There are no mutation routes. Admin inspection is read-only and uses the same visibility query. The ORM model/queryset blocks ordinary updates/deletion and inserts cannot overwrite an existing UUID. These application protections do not claim tamper-proof storage against an operator with database-owner access.

`apps.core.selectors.dashboard_data` supplies permission-scoped active customer/contact/agreement counts and five recently updated customers/recently created contacts. Counts use each record's own explicit status, independent of the customer's or catalog's archive status. `core` owns shared customer-tab/pagination templates and responsive CSS; existing feature templates include them. Customer editing now confirms Active-to-Archived transitions before saving. Other archive/terminate pages retain their existing POST confirmation flow.

## Shared contacts and service search (Phase 5B)

`contacts.ContactCustomer` owns the mutable person/customer association. The `contacts.services` write boundary accepts optional `customer_ids` in `create_contact`/`update_contact` and exposes `set_contact_customers(actor, customer_id, contact_id, customer_ids)`. It locks the contact, validates selected customers, archives unselected links, restores previously archived links and records each changed link through `audit.services.record_change` in the same transaction. The original `Contact.customer` and `ContactPoint.customer` remain stable to preserve the existing composite detail constraint and historical data. Person/detail change events are attributed to every currently associated customer; audit stores no contact values. The global `/contacts/` directory, customer-scoped pages and dashboard use read selectors. Old original-customer GET URLs redirect after that link is removed; POST actions require an active association.

`search` owns `/search/by-service/` and its email-export endpoint. It reads service assignments, contact associations, contacts and points through ORM queries. Distinct service IDs implement ANY/ALL so repeated agreements cannot duplicate customers. PostgreSQL combines association rows with customers having no qualifying contacts, sorts and paginates that result. The view fetches only visible-page contacts, points and matching service names in batches. The separate email query uses the entire filtered customer set, restricts collection to active customers, active associated contacts and active email details, and deduplicates by normalized email. It enforces both contact and service read grants on the page and export. Addresses are returned only to the authenticated browser on an uncached response when Copy All Emails is pressed; the page initially shows only the unique count. A small plain-JavaScript handler copies to the clipboard or exposes a selectable field.

No new runtime service, dependency, published port or production setting is needed. Apply the explicit Phase 5B migrations with the backup-first `update.sh` flow before starting new application code.

## Unified customer contact records (subsequent correction)

The older Phase 3 and Phase 5B paragraphs above describe the historical personless general-detail path. The current write boundary requires a Contact for every `ContactPoint`. Editors create a named person or a general team/shared Contact using the same `ContactForm`, then add its email and phone points. `Contact.is_general` is a presentation/filter flag; it does not create another storage path. `ContactCustomer` remains the authoritative customer association, including for general contacts, and the original `Contact.customer_id` plus point `customer_id` retain the Phase 3 composite ownership constraint.

`contacts.0004_unify_general_contact_points` attaches legacy null-contact points to one associated general Contact per affected customer. `contacts.0005_require_contact_for_details` separately enforces non-null `ContactPoint.contact_id` after that transaction commits. This separation allows PostgreSQL foreign-key triggers to complete before changing the table. The data move preserves point IDs and all existing values/status/timestamps. Migration does not write audit events because no staff actor performed it; new application writes remain transactionally audited. It aborts if any point cannot be attached and should be applied through backup-first `update.sh`.

The customer Overview and Contacts tab read associated contacts through contact-owned selectors. The global Contacts page writes the same Contact and ContactPoint records. General-detail GET URLs redirect to the resulting contact actions, while POST to those legacy URLs is refused. Global and service search read contact-linked points only; service email export includes addresses of active general contacts and still deduplicates over all matched customers/pages. Viewer/Editor/Administrator gates and Docker architecture are unchanged.
