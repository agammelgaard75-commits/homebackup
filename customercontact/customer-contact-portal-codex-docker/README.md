# Customer Contact Portal

An internal customer directory built with Django, PostgreSQL and Caddy HTTPS.
The modular monolith includes customer management, shared named/general contacts,
service catalog and customer agreements, global and ANY/ALL service search,
deduplicated email collection, JSON imports, transactional audit history, a
versioned REST API and confirmed administrator-only archived-record cleanup.
Keycloak OIDC controls production authentication and Viewer, Editor and
Administrator permissions. Local authentication remains available in development.

## Deployment

Use the standalone **`Production/`** bundle on an authorized internal Ubuntu
server. It contains the application, Docker configuration, maintenance scripts,
JSON examples/schemas and current operating documentation without development
instructions or historical phase files. The repository root remains the source
of truth; update the bundle with `scripts/package-production.sh` after changes.

Read [production installation](docs/PRODUCTION_INSTALL.md), configure a private
`.env` from the example, and verify Keycloak in staging before enabling production.
Docker Engine/Compose and standard host utilities are the only host dependencies.

```bash
./scripts/install.sh
./scripts/status.sh
./scripts/backup.sh
./scripts/update.sh
# Destructive: explicitly confirmed, matching-version snapshot restoration
./scripts/restore.sh path/to/verified.dump
```

The installer does not overwrite configuration or existing database volumes.
Production commands use `compose.yaml` with `compose.production.yaml` through
`scripts/compose.sh`. Do not use bare `docker compose up` for production.
PostgreSQL and Caddy certificate data persist across container recreation.
Backups are verified, private, timestamped and accompanied by version/checksum
metadata. No volumes, backups or old images are automatically deleted.

For isolated local review, use `.env.development.example`, a unique project and
free loopback bind address, and prefix commands with
`DEPLOYMENT_MODE=development`. Never reuse production data for testing.

```bash
DEPLOYMENT_MODE=development ./scripts/install.sh
DEPLOYMENT_MODE=development ./scripts/test.sh
./scripts/tests/operations.sh
```

## Using the portal

Home lists one row per customer with linked contacts and services. Customer,
contact and catalog details support direct edits according to role. Archived
records are hidden by default and available through explicit filters. One contact
can belong to several customers, including general contacts such as Support Desk.
Every contact must have at least one valid email OR phone, including after edits.

Search covers customer names/IDs, contact names/titles/emails/phones and services.
**Search By Service** opens `/search/by-service/` with multiple-service ANY/ALL
matching; Copy All Emails deduplicates active contacts across all filtered pages.
Administrators can preview/confirm repeatable JSON imports from Customers and
Contacts using stable import IDs and explicit mappings. Imports never guess
identity solely from names/emails and preserve associations.

The API lives at `/api/v1/`. Administrators access `/api/v1/docs/` and schema from
Administration, alongside audit history and Data Cleanup. Ordinary operations
archive; permanent deletion requires archived status, dependency preview and
explicit confirmation. Audit records are read-only and business writes/audits
commit together. No billing, external data integrations or additional business
modules have been introduced.

## Documentation and source map

- [Installation/configuration](docs/PRODUCTION_INSTALL.md), [operations/rollback](docs/OPERATIONS.md), [backup/restore](docs/BACKUP_RESTORE.md)
- [Security](docs/SECURITY.md), [troubleshooting](docs/TROUBLESHOOTING.md), [release verification](docs/RELEASE_VERIFICATION.md)
- [Keycloak OIDC](docs/KEYCLOAK_OIDC.md), [REST API](docs/REST_API.md), [JSON import contract](docs/JSON_IMPORT_FORMAT.md)
- [Architecture](docs/ARCHITECTURE.md), [data model](docs/DATA_MODEL.md)

`apps/` owns accounts, customers, contacts, services, search, audit, imports/shared
core, API and cleanup behavior. `config/` owns settings/routes.
`Dockerfile`, `compose*.yaml`, `deploy/` and `scripts/` own deployment.
Historical planning and phase verification remain in repository `docs/`, outside
the clean production bundle. See release verification for actual test results,
remaining limitations and whether the release tag was authorized by acceptance.
