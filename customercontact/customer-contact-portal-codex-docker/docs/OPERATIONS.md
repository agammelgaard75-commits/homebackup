# Operations and releases

Use `./scripts/compose.sh` for Compose commands; it selects the production overlay
by default. Development commands explicitly set `DEPLOYMENT_MODE=development`.
Keep the same private env, project name and named volumes for the installation.

```bash
./scripts/status.sh
./scripts/compose.sh up -d --wait
./scripts/compose.sh stop                 # retain containers and volumes
./scripts/compose.sh logs --tail 100 app proxy db
./scripts/backup.sh
./scripts/test.sh                         # separate Django test database
```

`status.sh` reports container health, actual running image version/revision,
database connectivity, last known local backup and filesystem space. Missing
backup metadata is reported as unknown, never assumed successful. Monitor an
external trusted-HTTPS `/health/` request too: container health alone does not
prove the proxy, DNS, certificates or Keycloak login work.

## Update

Obtain a reviewed release (Git tag or versioned bundle), preserving `.env`,
backups and `.state`. Review schema compatibility and release notes. Set
`APP_IMAGE` to the new version tag, and use its matching source/configuration.
Do not edit the Compose project name or automatically change PostgreSQL major.

```bash
./scripts/update.sh
./scripts/status.sh
```

The update validates existing health/HTTPS, records the **running** image ID,
version and revision under private `.state/<project>/pre-update-*.json`, makes a
fully read/verified backup, builds/checks the new image while the old app serves,
checks OIDC discovery, stops app writes, applies explicit migrations and roles,
then recreates app/proxy and verifies health. DB containers/images are not
silently upgraded. `BUILD_IMAGE=0` uses a reviewed, preloaded app image instead.

No volumes, backups or previous images are pruned. Locking prevents concurrent
scripted backups/install/update/restore for the same project. Run operations
from one canonical installation directory; do not run competing operators from
multiple checkouts. Direct Docker commands bypass the script lock.

A build or preflight failure leaves the current app running. A migration/restore
failure leaves it stopped; a post-start health failure may leave an unhealthy
container running. Neither case triggers an automatic database restore. Read
the error and logs before any further command. Keep maintenance windows short,
and do authenticated customer/contact/search checks after health succeeds.

For DB/proxy patch-image upgrades, review explicit pinned tags/digests, verify a
backup and rehearse replacement separately. Stop writes, use `compose.sh up -d
--wait db` with the reviewed same-major image, then start app/proxy and verify.
A PostgreSQL major upgrade requires its supported dump/restore or pg_upgrade
procedure, separately planned and rehearsed. Do not blindly pull mutable tags.

## Rollback

An image rollback and a database restore are different operations.

1. Read the pre-update deployment JSON and backup metadata; preserve evidence.
2. If the old application is proven compatible with the current schema, retain
   current data and start its saved image using the matching old release files:
   `APP_IMAGE=<saved-image-ID-or-tag> ./scripts/compose.sh up -d --no-deps --wait app`.
   Confirm HTTPS and authenticated behavior. Do not reverse migrations blindly.
3. If schema compatibility is not established, stop writes and use the matching
   old code/image **and** an explicitly confirmed database restore. All changes
   since that snapshot are lost. Follow [backup/restore](BACKUP_RESTORE.md).
4. Never automatically restore on deployment failure; investigate and obtain the
   operational approval required by your data-loss/retention policy.

## Monitoring and housekeeping

Docker logs rotate at 10 MB x 5 files **per container**. App has 128 PIDs, DB200,
proxy128; CPU/memory limits are configurable. Health checks query the DB and
restart policies recover process exits/host reboot. Docker does **not** restart a
merely unhealthy container automatically: alert and investigate.

Monitor `df -h`, `df -i`, `docker system df`, database growth, OOM/restart counts,
certificate expiry/trust, backup exit status/age and external Keycloak. Alert on
low disk (e.g. <20% free), failed backups and unexpected HTTP 5xx. Capacity and
response-time load testing remain site-specific. Do not use automatic volume or
image pruning. Review retention with `./scripts/backup-retention.sh`; approve
removals individually and retain rollback images/backups required by policy.

Periodically expire old Django sessions using an explicit operator command:
`./scripts/compose.sh exec app python manage.py clearsessions`. This does not
remove business data. There are no host-installed Django tasks/workers.

## Move to another server

Plan downtime; stop source app writes and take/verify a final DB backup. Transfer
it encrypted along with matching source/image version, private `.env`, and the
Caddy data/config volumes using the organization's approved volume-backup tool.
Those volumes include the CA **private** key: protect them as secrets. Install on
the destination with a separate temporary test project, restore and verify there
before DNS cutover. Keep issuer/callback external URLs consistent. Never run two
writable copies as if replication existed. Preserve the old server/volumes until
recovery and cutover are approved; update backup destinations and monitoring.
