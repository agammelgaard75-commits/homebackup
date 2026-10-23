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
- Audit event fields: actor, verb, entity type/id, customer, timestamp, safe summary.

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

These functions require an active actor with `accounts.access_portal`, `accounts.edit_portal`, `customers.view_customer`, and `customers.add_customer` or `customers.change_customer` as appropriate. They enforce validation and transactions, lock rows during updates/archive, and translate an identifier uniqueness race into a validation error. Repeated archive calls do not delete data or change an already archived record's timestamp. They do not log input values or write future-phase audit events.

The customer UI owns forms and mutations; its read-only Django admin registration links to the customer pages. Viewer receives `view_customer`; Editor and Administrator also receive `add_customer` and `change_customer`. Managed roles never receive `delete_customer`. All customer routes enforce portal access and model permissions on the server, including direct POST requests. Customer responses disable caching.

`/customers/` defaults to active records, supports name/identifier search, Active/Archived/All status filters, name/recent-update sorting, and 25 records per page. Query parameters survive page navigation. Global cross-module search remains Phase 5.
