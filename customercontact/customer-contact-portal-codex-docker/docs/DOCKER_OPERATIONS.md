# On-prem Docker operations

**Design goal:** copy the finished repository to any supported internal Linux server, install Docker Engine + Compose plugin, and manage the entire portal with Docker Compose. No Python, Django, PostgreSQL or web server software is installed directly on the host.

## Architecture

```
Staff browser --HTTPS--> Caddy container --> Django/Gunicorn container --> PostgreSQL container
                           :443                :8000 (private)           :5432 (private)
```

- `proxy`: Caddy terminates TLS and proxies to Django. Only it publishes host ports 80/443.
- `app`: Django + Gunicorn, and WhiteNoise for static assets. Runs as an unprivileged user on a read-only root filesystem. No published host port.
- `db`: PostgreSQL. Dedicated Docker named volume persists contacts/customers/services. No published host port.
- Container networking keeps the application and database off the externally routable network.
- Docker named volumes: `postgres_data`, `caddy_data`, `caddy_config`. All survive `docker compose down`; **never use `docker compose down -v` on a populated deployment.**
- Single stack, one Compose file; feature modules remain Django apps, **not separate containers**.

## First deployment on a clean server

Prerequisites: Linux with recent Docker Engine and Docker Compose v2, free TCP ports 80 and 443 on selected bind IP, and local DNS mapping the chosen hostname (e.g. `portal.home.lab`) to the server. Allow HTTPS traffic only from the intended internal networks/VPN. The server will require internet access for pulling images/packages during install, unless these are prepared offline.

**Phases 1–3 are implemented:** the Django foundation, customer management and contact management run in the existing Docker stack. Services follow a later phase. Production deployment still requires the separate production-readiness approval.

1. Copy/clone the finished repository to your internal server (e.g. `/opt/customer-contact-portal`). Never copy actual customer data in Git.
2. `cd /opt/customer-contact-portal`
3. `./scripts/install.sh portal.home.lab` (replace with the DNS hostname of your deployment).
4. `docker compose exec app python manage.py createsuperuser` (initial account; no public signup).
5. Extract the Caddy public root certificate and distribute/trust it on managed client devices (below).
6. Visit `https://portal.home.lab/`, verify login and perform a test backup/restore in a separate test environment.

The installer safely generates `.env` with a new Django secret and PostgreSQL password on its first run, and retains the existing `.env` on later runs. Review `.env` before going live and restrict it with `chmod 600 .env`. Never store it in source control or in a public archive.

## Internal HTTPS and browser trust

The Caddyfile uses `tls internal`, so the service uses Caddy's *local* CA, not a certificate from a public CA. **This encrypts traffic, but browsers will warn until the CA is trusted.** Export only the public CA certificate:

```bash
docker compose cp proxy:/data/caddy/pki/authorities/local/root.crt ./portal-root-ca.crt
```

Install this certificate in the appropriate trust store of each **managed** client, following your organization's trust policy. Keep Caddy's volume backed up since rotating that CA requires client trust changes. Never export or distribute the CA private key. Alternative: configure `deploy/Caddyfile` to use a corporate-issued TLS certificate, or put the app behind an existing, correctly configured HTTPS reverse proxy. Never expose contact data over plain HTTP.

## Maintenance commands

| Operation | Command |
|---|---|
| View container state | `./scripts/status.sh` |
| View recent logs | `docker compose logs --tail 100 app proxy db` |
| Back up database | `./scripts/backup.sh` |
| Update after pulling reviewed code changes | `./scripts/update.sh` |
| Restore a database dump (destructive) | `./scripts/restore.sh backups/your-backup.dump` |
| Run app tests | `./scripts/test.sh` |
| Create/modify admin account | `docker compose exec app python manage.py createsuperuser` |
| Start existing installation | `docker compose up -d` |
| Stop without deleting data | `docker compose down` |

`update.sh` first backs up the database, stops the application during schema changes, rebuilds the app, runs migrations and starts the stack, recreating app and proxy so updated Caddy configuration takes effect. There is deliberate brief downtime. Do **not** auto-update the image tags or schema changes without review. Only change PostgreSQL **major** version using its supported upgrade procedure, not a normal `pull`/`up`.

### Backups and disaster recovery

`backup.sh` creates a PostgreSQL custom-format dump in local `backups/` with mode `0600`. Dumps contain personal information. Move/copy them to encrypted **off-server** storage, retain multiple versions according to your policy, and periodically validate restores on a separate isolated test server. Keep the application revision and `.env` (especially Django's SECRET_KEY) in your disaster recovery records. Restore with a compatible PostgreSQL/portal version. Data in PostgreSQL is backed up by script; also back up Caddy CA *securely* if you use internal TLS.

For a full restore rehearsal, restore the dump on a fresh non-production stack with an isolated network and validated application version. `restore.sh` requires an explicit `RESTORE` confirmation and stops the app. If it fails, it leaves the app stopped.

**Avoid `down -v`, `docker volume prune`, and deleting volumes.** Backups do not make reckless commands clever.

### Deployment contract for Codex

During Phase 1 Codex must ensure:
- Django settings read `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, and database credentials/host from the environment. Fail closed when production secrets are missing.
- Django sets `SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')`, `SECURE_SSL_REDIRECT=True`, and secure session/CSRF cookies when DEBUG=0. The application is **never** published directly, so trusting the Docker reverse proxy is safe in this topology.
- WhiteNoise configured correctly and `STATIC_ROOT=/app/staticfiles`, so the image-build `collectstatic` command works without a running database and static files are served without host volumes.
- The unauthenticated `/health/` endpoint returns a non-sensitive 200 only if the DB is reachable, otherwise 503. It must work on `127.0.0.1:8000` when the reverse-proxy protocol header signals HTTPS.
- The process writes logs to stdout/stderr and does not require write access to the image filesystem. Do not log query strings, email addresses, telephone numbers or secrets.
- `config.wsgi:application` exists and the three-role authorization model is covered by tests.
- `python manage.py migrate`, `python manage.py check`, `python manage.py makemigrations --check --dry-run`, and `python manage.py test` work inside the `app` container.
- The migrations for the custom User model are committed to the repository before deployment; never run `makemigrations` automatically on the internal server.
- `docker compose build`, `docker compose config --quiet`, `docker compose up`, backup and restore are tested on a fresh *test* deployment before release.

## Limitations / future choices

- This MVP has **no** customer uploads; if document attachment functionality is added, add a persistent `media` volume and extend backup/restore to include it.
- `.env` permissions protect against ordinary mistakes, not root-level compromise. Protect Docker administrative access.
- Docker Compose is suitable for one server, not an HA cluster.
- Restrict host access via LAN/VPN firewall rules and use managed authentication. No public registration. Do not publish port 5432 or 8000.
- For scheduled backups, use host systemd timer/cron calling `./scripts/backup.sh` or a dedicated backup container; define retention and offsite transfer before storing real personal data. All portal runtime components stay in Docker.

## Phase 1 operation details

- `COMPOSE_PROJECT_NAME` in `.env` selects the named volumes, networks and application image. Do not change it on an existing installation expecting the same data. For isolated review, the first install accepts `COMPOSE_PROJECT_NAME=portal-phase1-review PORT_BIND_IP=127.0.0.1`; these values are persisted in `.env`. Do not use the same project name for independent installations.
- `setup_roles` runs explicitly after migrations during installation/update. It reconciles the three managed groups and preserves memberships. Run `docker compose exec app python manage.py setup_roles` to restore the documented grants. Manual permission changes to these managed groups are overwritten on the next reconciliation.
- Viewer has `accounts.access_portal`; Editor also has `accounts.edit_portal`; Administrator also has `accounts.administer_portal` and add/change/view user permissions. The initial superuser bypasses these grants. An active Administrator can use the portal admin without `is_staff`. Staff status alone grants no admin access. Ordinary Administrators can assign managed groups and deactivate staff; only superusers manage raw permissions/groups or superuser accounts. User deletion is disabled in the portal admin.
- Future feature phases must add explicit model permissions to the managed group mapping and check permissions on every read/mutation. Phase 1 contains no business models, schemas or business CRUD.
- Proxy health checks its private Caddy configuration endpoint; application health performs a database query. Probe `https://<hostname>/health/` with the trusted public CA to verify the full HTTPS path. The database has its own `pg_isready` health check. Caddy's admin endpoint is loopback-only inside its container.
- The application runs as UID 10001 with a read-only root filesystem; only `/tmp` is writable. Static assets are baked into the image, and `.env`, dumps, certificates and Git metadata are excluded from its build context. There are no runtime migrations or role-setup signals.
- Django logs allowlisted JSON fields (level, logger, HTTP status and exception class), omitting free-form messages, paths, query strings and traceback values. Gunicorn access logs contain status, method and duration only. Caddy access logging is disabled; runtime error logs filter request details and free-form messages. Investigate failures with checks and isolated reproduction; never enable input/query logging on real data.
- `backup.sh` writes unique custom-format dumps atomically with mode 0600. It removes incomplete or empty files. `restore.sh` requires `RESTORE`, uses a single transaction, checks migration compatibility, and leaves the app stopped on failure. Restore into a matching code revision and an otherwise compatible database; `pg_restore --clean` replaces objects in the dump but does not remove unrelated tables. A failed update after stopping the app also leaves it stopped. No script deletes named volumes.
- Before any data import, establish encrypted offsite backups for the database, `.env`, and the private Caddy CA volume. The database backup script does not back up the CA or `.env`. Preserve both Caddy named volumes during host migration and recovery; protect private CA material as a secret.
- Test commands: `./scripts/test.sh`, `./scripts/tests/operations.sh`. The latter uses temporary files and a fake Docker command to validate failure behavior without changing any real stack.
- HSTS applies to this hostname. Checks `security.W005` (all descendants) and `security.W021` (public browser preload) are deliberately silenced: neither policy is appropriate for an internal hostname without separately managed child sites. All other deployment checks remain active.
- Caddy runtime log filtering uses the documented [global log option](https://caddyserver.com/docs/caddyfile/options#log) and [filter encoder](https://caddyserver.com/docs/caddyfile/directives/log#filter), including proxy failures where access logging being disabled alone would not remove request data.

## Phase 2 customer upgrade

Use the existing `./scripts/update.sh`; no Compose, Dockerfile, proxy, image-major, volume, or port changes are required. It backs up before applying `customers.0001_initial` and runs `setup_roles` to add customer permissions. Existing staff credentials, group memberships and sessions remain intact. The migration is additive and does not transform existing Phase 1 records. The customer module requires no additional runtime service or dependency.

Customer access is available at `/customers/`. Viewer can read; Editor and Administrator can create, change, archive and reactivate records. The admin customer registration is read-only and links to the main customer UI so writes consistently use the owning app's validated services. Do not manually drop the customer table as a rollback: it contains the new data. Retain the pre-update backup and use the documented matching-code restore procedure if a rollback is needed.

## Phase 3 contact upgrade

Use the unchanged `./scripts/update.sh` to back up, build, explicitly apply the two additive contact migrations and reconcile contact permissions. `contacts.0001_initial` adds people and email/phone detail tables, indexes and primary constraints. `contacts.0002_contact_point_customer_integrity` adds a composite PostgreSQL foreign key protecting customer/person consistency. Neither migration rewrites existing customer or account data. All application writes use the ORM services in the contacts app.

The same three containers, image major versions, published ports, volumes, dependencies and production configuration remain in place. Contact pages are available from each customer's **Contacts** link, with general details also shown on Overview. Details are archived rather than deleted. Viewer can read; Editor and Administrator can add/change/archive/restore. Admin contact inspection is read-only. Review [Phase 3 verification](PHASE3_VERIFICATION.md) before requesting Phase 4.
