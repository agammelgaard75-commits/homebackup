# Database backup and restore

Database backups include customers, shared contacts/methods/associations,
services/history, accounts/OIDC links, imports, sessions and audit/cleanup data.
They contain personal data and credentials/session material: restrict and encrypt
them, including off-server transport/storage. Backups do not contain `.env`,
source/images or Caddy's private CA. Protect those separately for disaster recovery.

## Backup

```bash
./scripts/backup.sh
BACKUP_DIR=/srv/private-portal-backups ./scripts/backup.sh
./scripts/backup-retention.sh
```

PostgreSQL `pg_dump --format=custom` takes a consistent snapshot while ordinary
writes continue. Dumps are mode 600 in a mode 700 directory. A timestamp and
random suffix avoid collisions. Each dump is read/decompressed completely by
`pg_restore --file=/dev/null` before publication; SHA-256 and a private JSON
sidecar record time, project, actual deployed image ID, version and revision.
Only a `.dump` **with its `.dump.json` sidecar** counts as completed. Partial files
are removed on handled failures; interrupted incomplete sets must not be used as
successful backups. Checksums detect corruption, not malicious replacement.

`BACKUP_DIR` and `BACKUP_RETENTION_DAYS` may be set in `.env` or the operator
environment. The default review age is 30 days (0 = indefinite). The retention
script lists old metadata; it never deletes backups. Review off-server copies,
legal/data-retention obligations and restore history, then obtain approval for
specific removals. Existing backups/snapshots are preserved.

Schedule the host **backup orchestration script**, not host-side Django, using
your existing scheduler or root crontab, for example:

```cron
15 2 * * * cd /opt/customer-contact-portal && ./scripts/backup.sh >> /var/log/portal-backup.log 2>&1
```

Protect/rotate that log, alert on nonzero exit or missing recent successful
metadata, and configure encrypted off-server copying only after successful
completion. The script never prints database passwords. Keep both dump/sidecar;
verify their checksum after transfer. Restrict scheduler access to the canonical
installation and Docker. Choose frequency from your recovery-point objective.

## Restore (destructive, explicit approval required)

Rehearse first in a **separate disposable project/database/volumes**. Never use
real working data as a restore-test target. Select the matching application
version and PostgreSQL major, start the target DB, and preserve a fresh backup of
the current target before proceeding.

```bash
./scripts/restore.sh /srv/private-portal-backups/portal-TIMESTAMP-SUFFIX.dump
# Prompt requires exactly: RESTORE <configured-compose-project>
```

The script checks metadata/checksum and fully reads the archive **before**
stopping writes. It reports the target project and overwrite/data-loss warning.
After explicit confirmation it stops the app, uses supported `pg_restore
--clean --if-exists --exit-on-error --single-transaction`, verifies migration
compatibility and validated DB constraints, restarts app/proxy and checks actual
HTTPS readiness. No automatic migration or automatic fallback restore occurs.
On failure after stopping writes, the app remains stopped for investigation.
Database restore errors roll back the transaction. A later schema/health failure
requires operator inspection; do not assume the restored data was rolled back.

Older portal dumps have no metadata. After independently reviewing provenance
and matching code, `./scripts/restore.sh --legacy old.dump` explicitly permits
that format while still fully validating the archive and requiring confirmation.
Do not create fake metadata to bypass a failed checksum.

`pg_restore --clean` replaces objects included in the dump; it does not purge
unrelated/newer tables. Use a fresh isolated target for disaster-recovery
rehearsals or unknown schema differences. Do not restore older snapshots into an
arbitrary newer schema. A database owner/superuser is needed by the existing
single-database operational architecture; the application has no Docker socket
or host backup-script access. Protect its DB network and credentials.

This is snapshot recovery, **not point-in-time recovery**. Writes after snapshot
start are absent after restore, including writes during the build before an
update stops the app. No WAL archiving/PITR is configured. Determine acceptable
loss and downtime before approving restore. Verify record counts/relationships,
audit events, authenticated workflows and backup restart afterward.

Before production permanent cleanup, a verified current backup is an operational
prerequisite. Deleted information can remain in backups until retention expires;
portal cleanup is not deletion from off-server backups.
