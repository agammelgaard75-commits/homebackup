# Docker operations contract

The complete runtime remains in Docker Compose: Caddy HTTPS -> Django/Gunicorn
with WhiteNoise -> PostgreSQL. Modules remain Django apps in one image. No host
Python/database/web server, worker service or Docker socket in the app is needed.
Only proxy ports80/443 are published. App outbound HTTPS supports external
Keycloak; DB and application traffic otherwise use private networks.

Production uses `compose.yaml` **plus** `compose.production.yaml`; all maintenance
scripts and `scripts/compose.sh` select these by default. Development explicitly
uses `DEPLOYMENT_MODE=development` with separate env, project, loopback binding
and volumes. Never run the development-only base file alone in production.

- [New Ubuntu server installation and full configuration](PRODUCTION_INSTALL.md)
- [Starting, monitoring, updates and rollback](OPERATIONS.md)
- [Verified backups, explicit restore and retention](BACKUP_RESTORE.md)
- [Security controls and limitations](SECURITY.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Keycloak client, roles, migration and token examples](KEYCLOAK_OIDC.md)
- [Release verification results](RELEASE_VERIFICATION.md)

```bash
./scripts/install.sh
./scripts/status.sh
./scripts/backup.sh
./scripts/update.sh
./scripts/restore.sh path/to/verified.dump
./scripts/test.sh
./scripts/tests/operations.sh
```

Named `postgres_data`, `caddy_data` and `caddy_config` volumes survive recreation.
Never delete/prune them as routine maintenance. Keep project name stable. Static
collection happens at image build without DB access; explicit install/update
steps apply migrations and reconcile roles. Application startup never creates
migrations. Back up before schema changes. Restore tests use separate disposable
data; production cleanup/restore requires explicit approval.

Database snapshots do not protect source, `.env` or Caddy private keys. Protect
and transfer each through the approved operational process. Historical phase
verification documents describe earlier script versions; this guide and the
linked production procedures supersede their operational commands.
