# Production installation

The portal runs on one internal Ubuntu server as three Docker Compose services:
Django/Gunicorn, PostgreSQL 17 and Caddy HTTPS. Keycloak is external. No host
Python, PostgreSQL or web server is required. Use the clean `Production/` bundle
(or the repository root), not both against the same server/project.

## 1. Prepare a new server

Use a supported Ubuntu LTS (24.04 or 26.04), initially 2 CPUs, 4 GiB RAM and at
least 20 GiB free disk **plus measured database, image and backup growth**. Size
limits are starting points, not capacity guarantees. Set time synchronization.
Create internal DNS for the portal and Keycloak; both browsers and application
containers must resolve/reach the same HTTPS issuer and external callback.

Install Docker Engine, CLI, containerd, Buildx and the Compose plugin from the
[official Ubuntu repository instructions](https://docs.docker.com/engine/install/ubuntu/).
Follow their repository/key setup and select organization-approved package
versions. Review conflicts before removing any pre-existing host packages.
Then install the portal's host utilities:

```bash
sudo apt-get install ca-certificates curl jq bash coreutils util-linux iproute2
sudo systemctl enable --now docker
sudo docker info
sudo docker compose version
```

Compose must support `--wait` and JSON config output (v2.20+; tested with v5.5.1).
Docker administration grants host-root-equivalent access. Use sudo or an
approved Docker operator account, not a public web account. Limit inbound 80/443
to internal LAN/VPN; review Docker firewall rules, not only UFW. No app, database
or Caddy administration port is published. Never mount a Docker socket into app.

## 2. Stage configuration and authentication

Copy the reviewed release into `/opt/customer-contact-portal` and work there.
Keep the previous release/image and private configuration separately. No real
customer data belongs in the source bundle.

```bash
umask 077
cp .env.example .env
chmod 600 .env
# Edit .env privately using your approved editor/secret-management process.
```

Use independently generated random secrets (Django >=50 characters, database
>=32). For example, capture `od -An -tx1 -N 48 /dev/urandom | tr -d ' \n'` directly
into private configuration. Do not send secrets to shared logs or terminal
recordings. The installer does not generate/overwrite configuration.

| Variable | Production purpose |
| --- | --- |
| `PORTAL_DOMAIN` | External DNS name only, e.g. `portal.example.internal`. |
| `COMPOSE_PROJECT_NAME` | Stable installation/volume namespace. Never change it for an existing installation. |
| `PORT_BIND_IP` | Server bind address; default `0.0.0.0`. Use loopback for isolated tests. |
| `APP_IMAGE` | Reviewed application image/tag, e.g. `customer-contact-portal-app:1.0.0`. |
| `PROXY_IMAGE` | Optional reviewed proxy image/tag; default `<project>-proxy:2.11.7-portal.1`. Built from the pinned security rebuild, not the vulnerable upstream binary. |
| `DJANGO_SECRET_KEY` | Private random signing key, stable across container replacement. |
| `DJANGO_ALLOWED_HOSTS` | Exact hostname plus `localhost,127.0.0.1` for health checks. No wildcard. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Exact `https://<PORTAL_DOMAIN>`. |
| `DJANGO_DEBUG` | Must be `0`. |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Stable private database settings. Changing the env password does not rotate an existing DB password. |
| `AUTH_MODE` | Must be `oidc` in production. |
| `OIDC_ISSUER_URL` | Exact HTTPS Keycloak realm issuer. |
| `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` | Confidential portal client credentials. |
| `OIDC_API_AUDIENCE` | Required access-token audience, normally portal client ID. |
| `OIDC_REDIRECT_URI` | Exactly `https://<PORTAL_DOMAIN>/oidc/callback/`. |
| `OIDC_VERIFIED` | Set `1` only after successful staging browser/API/role verification. Acknowledgment, not a security bypass or substitute for testing. |
| `TZ` | Display timezone; timestamps remain timezone-aware. |
| `BACKUP_DIR` | Optional absolute host backup directory, default `backups/<project>/`. |
| `BACKUP_RETENTION_DAYS` | Review threshold, default 30; 0 keeps indefinitely. No automatic deletion. |
| `APP_MEMORY_LIMIT`, `DB_MEMORY_LIMIT`, `PROXY_MEMORY_LIMIT` | Defaults 1g, 1g, 256m. |
| `APP_CPU_LIMIT`, `DB_CPU_LIMIT`, `PROXY_CPU_LIMIT` | Defaults 2.0, 1.0, 0.5. |
| `JSON_IMPORT_MAX_BYTES`, `JSON_IMPORT_MAX_RECORDS` | Defaults 1 MiB / 500; maximum 5 MiB / 1000. |

Operator environment switches: `PORTAL_ENV_FILE=/absolute/private/file`,
`DEPLOYMENT_MODE=production` (default), `BUILD_IMAGE=0` to use preloaded app and proxy images,
`APP_VERSION`/`GIT_REVISION` for image build provenance. Archive users without Git
should set `GIT_REVISION` to the release's recorded commit when building.
`PORTAL_ENV=production` is enforced by the production Compose overlay; it rejects
local auth, DEBUG, weak secrets and incorrect callback configuration.

Follow [Keycloak setup](KEYCLOAK_OIDC.md): confidential client, Authorization
Code + PKCE, no implicit/direct-password flow, exact redirect/logout URIs, and
portal **client** roles `portal-viewer`, `portal-editor`, `portal-admin`. Add the
portal audience/client-role mapper to access tokens. Set access-token lifespan
<=5 minutes. Service accounts receive only their required portal role.

Test login, role denial/removal, MFA if enabled, logout, access-token audience and
service accounts in staging first. No automatic local administrator or fallback
is created. `.env.example` is deliberately incomplete until those steps pass.

## 3. Install

On the authorized new server with free selected ports:

```bash
./scripts/install.sh
./scripts/status.sh
```

Use `sudo` if required. The installer validates prerequisites, private env,
production mode and ports, builds/checks app and patched proxy images, verifies OIDC discovery/JWKS,
starts/waits for DB, explicitly migrates/reconciles roles, starts app/proxy and
checks HTTPS with certificate verification. Static files are collected during
the database-free image build. A healthy repeat invocation is a read-only check;
existing/orphaned DB volumes are never overwritten. Use update for changes.

For offline deployment, build on a compatible staging platform, export the
versioned app, patched proxy and pinned DB images with `docker image save`, transfer and
`docker image load -i release-images.tar`; then `BUILD_IMAGE=0 ./scripts/install.sh`.
Preserve the same release files/Caddyfile. Keycloak must still be reachable.

Caddy uses its persistent internal CA. Export **only its public certificate**:

```bash
./scripts/compose.sh cp proxy:/data/caddy/pki/authorities/local/root.crt ./portal-root-ca.crt
```

Distribute/trust it on managed clients through your organization's process. Never
share its private key. Visit `https://<PORTAL_DOMAIN>/`; sign in via Keycloak.
Establish verified off-server backups before importing real records.

## Development and existing installations

Use a separate project, env file, loopback address and volumes. Copy
`.env.development.example`, fill synthetic secrets, then run:

```bash
DEPLOYMENT_MODE=development ./scripts/install.sh
DEPLOYMENT_MODE=development ./scripts/compose.sh exec app python manage.py createsuperuser
DEPLOYMENT_MODE=development ./scripts/test.sh
```

Never enable local auth on a production server. The base `compose.yaml` retains
development compatibility; **production always uses both files** through
`scripts/compose.sh` (equivalent to `docker compose -f compose.yaml -f
compose.production.yaml`). Do not use bare `docker compose up` for production.
Existing local-auth installations need a controlled Keycloak staging/migration
before production enablement; their private env is never changed automatically.
