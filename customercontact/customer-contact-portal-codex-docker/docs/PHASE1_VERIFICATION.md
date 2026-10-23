# Phase 1 verification — 23 October 2026

Scope: foundation and Docker infrastructure only. No customer/contact/service models or CRUD, search, or business audit features were implemented. The corresponding Django apps are registered for later phases.

## Environment and isolation

- Docker Engine 29.8.0 and Compose 5.5.1; commands ran through `sudo` because the workspace account cannot access the Docker socket directly.
- Review project: `portal-phase1-review`, proxy bound only to `127.0.0.1:80/443`, hostname `portal.phase1.localhost`.
- Restore project: `portal-phase1-restore`, separate networks/volumes, proxy bound to `127.0.0.2:80/443` during the rehearsal. Stopped and removed afterward with `docker compose down`, preserving all named volumes.
- Existing applications and services were not modified. No production server was accessed. No host Python/PostgreSQL/web-server software was installed. No volumes were deleted.
- `.env`, generated certificates, test harnesses, and dumps are ignored by Git and excluded from application image builds. Only disposable staff accounts were used.

## Executed checks and observed results

| Command or rehearsal | Observed result |
|---|---|
| `docker compose config --quiet` | Passed. Only proxy ports are published. |
| `docker compose build app` / installer build | Passed using the pinned requirements, including transitive dependencies. Static collection produced 128 files without database access. |
| `scripts/install.sh portal.phase1.localhost` | Passed after adding the initial custom User migration. All three containers became healthy; migrations and role initialization succeeded. |
| `scripts/test.sh` | Passed: standard system check, deployment checks, migration drift check, and **20 Django tests**. |
| `manage.py check --deploy --fail-level WARNING` | Passed with two documented internal-HSTS checks silenced (W005/W021); no other warnings/errors. |
| `manage.py makemigrations --check --dry-run` | No changes detected. |
| `python -m pip check` inside app image | No broken requirements. |
| `caddy validate --config /etc/caddy/Caddyfile` | Valid configuration. |
| `bash -n` for every maintenance/test shell script | Passed. |
| `scripts/tests/operations.sh` | Passed backup failure/empty-output cleanup, unique private dumps, restore cancellation/failure/schema-check failure, update backup/migration failure, and installer validation/configuration retention checks. |
| Actual HTTPS requests using exported Caddy public CA | Health 200, HTTP→HTTPS 308, anonymous home→login 302, static CSS 200. TLS verification was enabled. |
| HTTPS authentication smoke | Viewer, Editor, Administrator, and a generated bootstrap superuser logged in/out successfully. Navigation and admin access matched permissions; missing CSRF was rejected. Createsuperuser flow succeeded. |
| Unauthorized/invalid input tests | Unassigned and staff-only users denied; Viewer/Editor admin writes denied; external login redirect rejected; inactive users rejected; invalid groups rejected; administrators could not grant raw/superuser permissions or change superuser passwords. |
| Database outage | Stopped only the review DB. HTTPS health returned 503 with exactly `{"status":"unavailable"}`. Restoring DB service restored health. |
| `scripts/backup.sh` and isolated `scripts/restore.sh` | Real custom-format dumps created with mode 0600. Restored four disposable users; hashes of user rows, password hashes, flags and group relationships matched the source. Restored stack became healthy over verified HTTPS. |
| Corrupt real restore | Returned failure and left the restore app stopped. Subsequent valid restore recovered the stack. |
| Proxy error privacy | A request with a synthetic query marker during app downtime returned 502; the marker was absent from proxy logs. |
| `scripts/update.sh` | Backup occurred before app stop/migrations; build, role reconciliation, checks, and restart succeeded. Final script also recreates the proxy to activate Caddyfile changes. |
| `docker compose up -d --force-recreate --wait` | All three containers recreated and returned healthy. User/password/group digest, `.env` digest, and Caddy public CA digest were unchanged. HTTPS still validated with the original CA. |
| Container hardening | App UID/GID 10001; `/app` not writable; `/tmp` writable. No `.env`, backups, or Git directory in the image. App/database have no host port bindings. |

The initial test run contained two fixture errors (missing HTTPS Origin in a CSRF test and the wrong name for Django's admin password-change URL). Both were corrected; the complete suite then passed. Initial migration scaffolding and intentionally inapplicable HSTS warnings were also resolved before successful installation.

## Review and limitations

Phase 1 is ready for code and UI review. The local review stack is left running with three healthy services. Create a personal review administrator with `sudo docker compose exec app python manage.py createsuperuser`; rehearsal accounts have randomly generated passwords, and are deactivated after testing. Export/trust the public Caddy CA as described in README before browsing locally.

HTTP behavior and rendered pages were checked programmatically; a graphical browser/mobile visual inspection was not performed. Client trust-store installation, internal DNS/firewall policy, offsite backup configuration, and production rollout are outside this isolated rehearsal and remain part of the separately approved production-readiness phase. Two private test volume sets and disposable dumps are intentionally retained.

Next phase, after review: **Phase 2 — Customers**. No Phase 2 work has begun.
