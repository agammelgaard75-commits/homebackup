# Application architecture

The portal is one Django application with separate `accounts`, `core`,
`customers`, `contacts`, `services`, `search`, `audit`, `cleanup` and `api` apps.
PostgreSQL stores business records; Caddy handles HTTPS. Docker Compose runs
these as one app container, one database container and one proxy container.
There are no workers, external search services or separate feature services.

## Data ownership

- `customers.Customer` owns customer names, company IDs, status and notes.
- `contacts.Contact` owns named and general contacts. `ContactCustomer` links
  one contact to one or more customers. `ContactPoint` owns every contact email
  and phone number; customer pages use those same contact records. A contact
  must have an active email or phone before it can be saved.
- `services.Service` owns the catalog. `CustomerService` owns each customer
  agreement, including its status, dates and history. Separate agreements may
  refer to the same customer and catalog service.
- `audit.AuditEvent` stores metadata-only change history. Business writes and
  audit writes occur in the same transaction.
- `cleanup` provides preview and confirmed permanent deletion for eligible
  archived records. It checks dependencies before deleting; ordinary business
  pages only archive and restore.

The web interface and REST API use the owning modules' validation and write
services. The JSON import formats and stable `import_id` rules are described in
[JSON import format](JSON_IMPORT_FORMAT.md). Database migrations are committed
with source and applied explicitly during installation or update.

## Access control

Viewer can read; Editor can maintain customers, contacts, relationships and
customer service assignments; Administrator can also manage the service
catalog, imports, audit and cleanup. Permission checks run on the server for
web and API requests. Production requires Keycloak; local Django login is
development-only. Keycloak OIDC maps `portal-viewer`, `portal-editor` and `portal-admin` client roles to
these same permissions; identity uses issuer and subject rather than email.

REST API routes are under `/api/v1/`, with schema at `/api/v1/schema/` and
interactive documentation at `/api/v1/docs/`. See [REST API](REST_API.md).
