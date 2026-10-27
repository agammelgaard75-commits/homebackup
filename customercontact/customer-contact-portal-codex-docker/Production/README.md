# Customer Contact Portal — deployment bundle

A Django customer directory with shared contacts, service agreements, search and
email collection, administrator JSON imports, audit history, a versioned REST
API, confirmed archived-data cleanup and Keycloak OIDC authentication.

This directory is a standalone deployment bundle. No development-agent prompts,
historical phase instructions, credentials or customer data belong here.
Release status and remaining security findings are recorded in
[release verification](docs/RELEASE_VERIFICATION.md). An untagged candidate is not
an approved production release.

Read [installation](docs/PRODUCTION_INSTALL.md), configure `.env` privately from
`.env.example`, and verify your Keycloak realm/client in staging. Then on the
authorized Ubuntu server:

```bash
./scripts/install.sh
./scripts/status.sh
./scripts/backup.sh
./scripts/update.sh
```

`./scripts/restore.sh path/to/verified.dump` requires explicit confirmation and
replaces current database contents. Rehearse with disposable data first.

Use `./scripts/compose.sh` for all production Compose commands: it includes the
production security overlay. Base `compose.yaml` alone is development-compatible
and must not be used alone for production. All application runtime stays in Docker;
only Caddy publishes80/443. DB/certificate volumes persist across recreation.

- [Installation/configuration](docs/PRODUCTION_INSTALL.md)
- [Operations, updates and rollback](docs/OPERATIONS.md)
- [Backup/restore and retention](docs/BACKUP_RESTORE.md)
- [Security](docs/SECURITY.md) and [troubleshooting](docs/TROUBLESHOOTING.md)
- [Keycloak OIDC](docs/KEYCLOAK_OIDC.md)
- [REST API](docs/REST_API.md), `/api/v1/docs/` (Administrator)
- [JSON import guide](docs/JSON_IMPORT_FORMAT.md), [examples](examples/), [schemas](schemas/)
- [Architecture](docs/ARCHITECTURE.md)

Use `sha256sum -c FILES.sha256` to check bundle integrity against the supplied
manifest (the manifest itself must come from a trusted release). Tests run with
`./scripts/test.sh`; script failure tests use `./scripts/tests/operations.sh`.
Development uses a separate `.env.development.example` copy and explicit
`DEPLOYMENT_MODE=development`, never a production database.
