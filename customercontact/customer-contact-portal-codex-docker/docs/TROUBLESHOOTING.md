# Troubleshooting

Use the canonical installation directory and its private env/project. Start with
`./scripts/status.sh`, `./scripts/compose.sh ps -a` and `./scripts/compose.sh logs
--tail 100 app proxy db`. Do not print resolved Compose config or secrets.

| Symptom | Check / safe response |
| --- | --- |
| Docker permission denied / unavailable | Verify Docker service and approved operator access; use sudo if authorized. Do not chmod the socket world-writable. |
| Missing env or mode error | Copy the correct example privately, chmod600, fill required values. Production requires tested OIDC; do not bypass using local auth. |
| Port conflict | Inspect `ss -ltnp` and other container mappings. Choose a free server/address or arrange a separate approved migration; scripts never stop the conflicting service. |
| Existing DB volume on fresh install | Installer refuses to overwrite it. Identify the project and matching old release first. For a stopped verified existing stack use `compose.sh up -d --wait`; then use backup-first update. |
| Interrupted initial install | Preserve volumes/env. Inspect logs and migration state. With reviewed matching image, explicitly resume `compose.sh run --rm --no-deps app python manage.py migrate --noinput`, then `setup_roles`, then `up -d --wait app proxy`. Take a backup first if any data already exists. Do not delete the volume to make installation succeed. |
| DB unhealthy | Inspect disk/inodes, permissions, DB logs and image major compatibility. Never expect changing POSTGRES_PASSWORD in env to rotate an existing DB password. |
| App unhealthy / HTTP503 | Check DB readiness, migrations, allowed loopback host, image/env compatibility and resource/OOM limits. Health returns no secret diagnostics by design. |
| HTTP502 during update | App may be stopped deliberately. Inspect the recorded pre-update image and migration logs; no automatic rollback is performed. |
| TLS browser warning | Distribute the public Caddy CA certificate to managed clients; verify hostname/DNS and preserved CA volume. Never distribute the CA private key. |
| OIDC login503 | Run `compose.sh run --rm --no-deps app python manage.py check_oidc`; check issuer discovery, container DNS/egress and CA trust. No local fallback is available. |
| Redirect mismatch | Exact `https://<PORTAL_DOMAIN>/oidc/callback/`, client redirect URI and Django forwarded HTTPS must agree. SSH forwarding must preserve the browser-visible hostname. |
| API401 | Verify access-token signature, exact issuer/audience, Bearer type, expiry and <=300-second age; ID tokens/local credentials are rejected in OIDC mode. Never paste tokens into logs or tickets. |
| API403 / login Access Denied | Assign a recognized portal client role, not a generic Keycloak admin role. Check inactive local account and endpoint permission. |
| Frequent five-minute login / token renewal | This is the documented authorization refresh bound. Reauthenticate through existing SSO; automation obtains a new short-lived client-credentials token. |
| API429 | Respect Retry-After and reduce request rate. Import limit is stricter. |
| Backup failure / disk full | Check DB health and destination permissions/capacity. `.partial` or a dump without its metadata is not a completed new backup. Never remove old backups/volumes without review. |
| Restore fails before confirmation | Check archive, checksum/metadata, matching version and target DB health. Nothing has been overwritten. |
| Restore fails after confirmation | App stays stopped. The pg_restore transaction rolls back on SQL errors; later compatibility/health errors need investigation. Preserve all evidence and backups. |
| Update migration fails | Keep app stopped, preserve recorded image and pre-update backup, diagnose migration. Do not automatically restore DB or downgrade code across incompatible schema. |

Stop/restart only the selected project. Do not use `down -v`, `volume prune`,
`reset --hard` or bulk backup deletion as troubleshooting. If detailed error
reproduction is necessary, use synthetic data in an isolated environment rather
than enabling sensitive logging on the working installation.
