# Docker operations

## Deployment layout

Docker Compose runs three services: Caddy (`proxy`), Django/Gunicorn (`app`)
and PostgreSQL (`db`). Caddy alone publishes ports 80 and 443. The app and
database communicate on private networks; the app also has outbound HTTPS
access for optional Keycloak OIDC. Named volumes `postgres_data`, `caddy_data`
and `caddy_config` survive container recreation. Never use `docker compose
down -v` or prune these volumes on a populated installation.

Run all commands from the directory containing `compose.yaml`. The host needs
Docker Engine, Compose v2, Bash and standard utilities, but no Python,
PostgreSQL or web server installation.

## New installation

1. Set internal DNS for the portal hostname and restrict inbound HTTPS to
   approved networks. Confirm the chosen bind address has free ports 80/443.
2. Run `./scripts/install.sh portal.example.internal`. It creates `.env` once,
   generates private secrets, builds the image, applies migrations explicitly,
   creates role groups and waits for healthy containers.
3. Run `docker compose exec app python manage.py createsuperuser` to create
   the first local administrator. Assign Viewer, Editor or Administrator groups
   to further staff accounts. No public registration exists.
4. Export **only** Caddy's public CA certificate with
   `docker compose cp proxy:/data/caddy/pki/authorities/local/root.crt
   ./portal-root-ca.crt`, and trust it on managed clients. Protect the Caddy
   volume and never distribute the CA private key.
5. Open `https://portal.example.internal/` and verify login, roles and
   `https://portal.example.internal/health/`.

The default `AUTH_MODE=local` does not require Keycloak. To use Keycloak,
complete the separate [OIDC setup](KEYCLOAK_OIDC.md) in a test environment
before switching modes. The callback is
`https://<PORTAL_DOMAIN>/oidc/callback/`.

## Routine commands

| Task | Command |
| --- | --- |
| Validate Compose | `docker compose config --quiet` |
| Check status and recent logs | `./scripts/status.sh` |
| Run checks and tests | `./scripts/test.sh` |
| Back up database | `./scripts/backup.sh` |
| Update reviewed source | `./scripts/update.sh` |
| Start existing stack | `docker compose up -d --wait` |
| Stop without deleting volumes | `docker compose down` |

`update.sh` first takes a database backup, stops the app to prevent writes,
pulls the configured DB/proxy images, builds the application, applies committed
migrations, reconciles role permissions and recreates app/proxy. Review image
changes, migrations and a matching rollback revision before an update. Expect
brief downtime. Do not change the Compose project name for an existing
installation: it selects the named data volumes.

## Backups and recovery

`backup.sh` writes a mode-`0600` PostgreSQL custom-format dump under
`backups/`. Dumps contain personal data. Keep encrypted off-server copies and
test restores in an isolated environment. Retain the matching application
revision and a protected copy of `.env`, especially `DJANGO_SECRET_KEY`.
Preserve and protect the Caddy CA volume separately if using internal TLS.

`./scripts/restore.sh backups/selected.dump` **replaces the configured
database** only after an explicit `RESTORE` prompt. It stops the app, restores
inside a single database transaction, verifies migration compatibility and
restarts on success. If it fails, the app remains stopped for investigation.
Use it only with a dump from a compatible portal and PostgreSQL version.
Never rehearse restore against live customer data.

Permanent archived-record cleanup in the Administration interface requires a
verified database backup first. Old backups may retain deleted personal
information until their retention period expires.

## Health and security

- `/health/` returns 200 only while the database is reachable; otherwise 503.
  Check it through HTTPS with a trusted CA, not by disabling certificate checks.
- Keep `.env` private and out of source control. The app runs as an
  unprivileged user with a read-only root filesystem.
- Caddy handles HTTPS. Trust its public CA on clients or configure a managed
  certificate. Keep the app and PostgreSQL ports private.
- Session writes use CSRF protection. API bearer credentials and OIDC tokens
  must never appear in URLs, logs or deployment archives.
- Container recreation does not run migrations automatically. Apply them via
  install/update with a backup first.
