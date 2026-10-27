# Security and privacy

## Boundary and controls

This is a single-server internal application, not an Internet-hardened public
service or HA cluster. Restrict access to approved networks and managed clients.
Docker operators and the database owner are highly privileged; audit records are
application-immutable, not tamper-proof against those operators.

Production scripts always include `compose.production.yaml`. Django fails closed
unless OIDC, DEBUG=0, strong secrets, explicit hosts and the exact HTTPS callback
are configured. The base Compose file is development-compatible. Do not bypass
the production overlay or use development mode on a production server.

- Keycloak uses maintained mozilla-django-oidc and PyJWT libraries, Authorization
  Code with state/nonce/PKCE, verified HTTPS discovery and RS256 JWKS validation.
  Stable identity is issuer + subject; no automatic email linking.
- Only recognized **portal client roles** grant access; no generic realm-admin
  elevation, public registration or password fallback in OIDC mode. Legacy local
  API credentials are disabled there. Production administrators are not created
  automatically. Local login is for isolated development only.
- Session authorization expires after 300 seconds and requires fresh OIDC login.
  API access tokens older than 300 seconds are rejected as well as expired,
  malformed, wrong-issuer/audience/signature tokens and ID tokens. Previously
  issued tokens may retain old roles until that bound; local account disablement
  denies access immediately. Cached JWKS does not provide instant revocation.
- Secure HttpOnly/Lax session cookies, CSRF protection, HTTPS redirects, HSTS,
  nosniff and DENY framing remain enabled. No unrestricted CORS. Logout always
  ends the portal session; Keycloak SSO logout may require confirmation or remain
  active if the provider is unavailable. Never put tokens in URLs or logs.
- Business API routes require authentication and role checks; sensitive imports,
  global audit, catalog changes and cleanup require Administrator. No ordinary
  hard DELETE. Session API writes require CSRF. Documentation is Administrator-only.
- API lists cap at 100/page; default user/anonymous throttles are 240/60 per minute
  and imports 10/minute. DRF's cache-based limits are best-effort **per worker**
  with the default in-memory cache, not a distributed DoS defense. Network access
  control and resource limits remain necessary; do not claim an exact global quota.
- Caddy limits bodies to 6 MB; Django/import validation imposes lower limits.
  JSON previews use explicit mapping/import IDs and signed actor-bound tokens;
  commits and audits are transactional. No executable upload/import formats.
- Cleanup requires archived status, dependency checks, signed expiring preview,
  explicit POST confirmation, stale-state recheck and a transaction. Shared active
  contacts and service history are protected; audits retain stable IDs/counts,
  not unnecessary copies of deleted values. Verify a production backup first.
- ORM queries bind values, templates escape user text, and no unsafe rendering,
  raw business SQL, CSRF exemptions or disabled TLS checks were found in review.
  Contact validation/associations and all owning-app service APIs are retained.
- App runs UID10001, read-only, without Linux capabilities or Docker socket; tmpfs
  is bounded. DB has no published port. Only proxy publishes 80/443. Named DB/CA
  volumes persist. CPU, memory/PID limits and rotating logs bound routine usage.
- Django logs allowlisted metadata; Gunicorn omits paths/headers/bodies. Caddy
  strips request/free-form error data. PostgreSQL is configured to omit failing
  SQL statements/parameters and verbose constraint detail. Do not enable debug
  SQL, provider-response or request-body logging against real data.

The existing PostgreSQL bootstrap owner is also the application's DB credential;
its elevated DB privilege is a known trust limitation, not isolation from a
compromised app. It is confined to the private DB network and never given host
Docker access. Separating migration-owner and runtime DB grants requires a
separately reviewed role migration for existing installations; this release does
not silently change database credentials or ownership.

## Dependency review

On 2026-10-25, pip-audit found three advisories in DRF3.17.2. It was upgraded to
3.18.3, which includes fixes for Accept-header CPU exhaustion, unsafe JSON codec
selection and TokenProxy revocation. The portal does not use DRF TokenProxy, but
updates the affected package regardless. See the
[maintainer release notes](https://www.django-rest-framework.org/community/release-notes/).
A repeat scan of all 29 resolved pinned application packages reported zero known
vulnerabilities. The container scan additionally found old pip advisories; the
build uses pip26.2.2, then removes pip and ensurepip from the runtime image.

Python3.12.15, PostgreSQL17.11 and Caddy2.11.7 image tags **and digests** are pinned.
No mutable `latest` tags or automatic image updates are used. Scan again before
future releases; a clean application-package scan is not proof that a base OS has
no vulnerabilities. See [release verification](RELEASE_VERIFICATION.md) for actual
container scan results, remaining findings and release status.

## Operational prerequisites

Protect `.env`, backups, image registry and Caddy private CA, and keep secrets out
of Git/build context. Never publish `docker compose config` output: it resolves
secrets. Use `scripts/compose.sh config --quiet` for validation. Restrict Docker
operator access, enable host patching/time sync/firewall policy, distribute CA
trust and verify live Keycloak roles/MFA/logout/service-account access in staging.

Custom Keycloak CAs must be trusted by both Requests and PyJWT/urllib TLS stacks.
Use an approved derived image containing the CA bundle, setting
`REQUESTS_CA_BUNDLE` and `SSL_CERT_FILE` to its trusted path if needed. Never set
`verify=False`, use curl `-k`, or mix internal issuer names with external callbacks.
No live Keycloak instance was supplied for automated release verification; mocked
cryptographic/login tests do not validate the organization's real realm/client.

Take verified off-server backups and rehearse recovery. Production cleanup and
restores require explicit operational approval. Deleted personal information may
remain in backups until retention expires. No automatic scheduled cleanup exists.
