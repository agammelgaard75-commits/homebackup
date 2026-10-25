# Customer Contact Portal

This directory is the standalone Docker deployment source for the internal
Customer Contact Portal. It contains the application, migrations, static assets,
JSON import schemas and examples, Docker configuration, maintenance scripts,
tests, and current operating documentation. It contains no customer data or
deployment secrets.

## What the portal provides

- One customer directory with linked contacts and assigned services.
- Customer, contact and service management with archive/restore history.
- Shared contacts, multiple email addresses and phone numbers, and service
  search with distinct email collection.
- Administrator JSON imports, audit history, archived-data cleanup and a
  versioned REST API at `/api/v1/`.
- Viewer, Editor and Administrator permissions. Local login is the default;
  optional Keycloak OIDC is configured separately.

## Fresh installation

Install Docker Engine, the Docker Compose plugin and standard host utilities.
Choose an internal DNS hostname, restrict access to the intended network, and
confirm ports 80 and 443 are free. From **this directory**:

```bash
./scripts/install.sh portal.example.internal
docker compose exec app python manage.py createsuperuser
docker compose cp proxy:/data/caddy/pki/authorities/local/root.crt ./portal-root-ca.crt
```

The installer creates a private `.env` with generated Django and PostgreSQL
secrets. Review it and keep mode `0600`. Trust only the exported **public** Caddy
CA certificate on managed browsers, then open
`https://portal.example.internal/`. Do not commit `.env` or the certificate
authority's private key. The application and database have no published ports.

For an existing installation, preserve its `.env`, PostgreSQL volume and Caddy
volumes. Use the backup-first update procedure in
[Docker operations](docs/DOCKER_OPERATIONS.md); do not run the fresh installer as
an upgrade shortcut.

## Documentation

- [Docker installation, updates, backups and restore](docs/DOCKER_OPERATIONS.md)
- [Application architecture and data ownership](docs/ARCHITECTURE.md)
- [REST API endpoints and permissions](docs/REST_API.md)
- [Customer and contact JSON import format](docs/JSON_IMPORT_FORMAT.md)
- [Optional Keycloak OIDC configuration](docs/KEYCLOAK_OIDC.md)

`./scripts/test.sh` runs Django checks, migration-drift detection and the full
automated suite inside Docker. `./scripts/status.sh` shows container state and
recent safe application logs. Database backups and Caddy's CA volume require
separate, protected retention; source control is not a data backup.
