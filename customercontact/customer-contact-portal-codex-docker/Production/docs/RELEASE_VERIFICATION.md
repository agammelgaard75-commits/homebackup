# Production readiness verification — candidate 1.0.0

Verification date: **2026-10-25**. Starting verified source:
`dd6ce97fd1bb8421192425348162d32ec447cc32`. The historical `stable-baseline` tag
remains unchanged. The final candidate is recorded by the production-hardening
checkpoint commit (`git log -1`); **no `v1.0.0` release tag is approved** while the
runtime-image findings below remain unresolved. A candidate image/version label
is not production deployment approval.

Final checkpoint review on **2026-10-27** confirmed the official Caddy release
and image digest were unchanged, bundle checksums still passed, and both stacks
remained healthy. The disposable release stack was then stopped, preserving its
containers, volumes and backups; the original working portal remained running.

No production server was accessed. The original working review installation was
not updated: its three containers stayed healthy, and read-only counts remained
19 customers, 23 contacts, 14 catalog services, 31 assignments and 26 users. Its
private configuration, customer data, backups and named volumes were preserved.

## Delivered changes

- Explicit production overlay requiring OIDC, secure settings and exact callback;
  separate development configuration and a safe Compose wrapper.
- Fixed Python/PostgreSQL/Caddy versions and image digests, rotating logs, bounded
  CPU/memory/PIDs, non-root/read-only/capability-free app, private DB networking,
  request-size bound and reduced database error detail.
- Installer prerequisite/config/port/OIDC checks, explicit migrations and
  database-free build-time static collection, readiness and verified HTTPS checks.
- Verified atomic backup sets with timestamps, SHA-256 and running-image version
  metadata; configurable destination and non-deleting retention review.
- Explicit project-name restore confirmation, validation before writes, single
  transaction, schema/constraint checks and HTTPS health afterward. Legacy dump
  support remains available with explicit `--legacy` acknowledgment.
- Backup-first updates, retained old image/version records, build before downtime,
  no automatic DB downgrade/restore or volume/image/backup pruning.
- Status/version/DB/backup reporting, safe generic API500 errors, patched DRF,
  removed runtime pip/ensurepip, operating/security/recovery guides and clean
  allowlisted Production bundle with checksum manifest.

No business model or schema migration was added. Fresh installation applied all
existing committed migrations. Restore and update checked schema compatibility;
existing application data was not transformed.

## Software

| Component | Verified version |
| --- | --- |
| Docker Engine / Compose plugin | 29.8.0 / 5.5.1 |
| Python image | `python:3.12.15-slim` + pinned SHA-256 in Dockerfile (Debian13.7) |
| PostgreSQL image | `postgres:17.11-alpine` + pinned SHA-256 in Compose |
| Caddy image | `caddy:2.11.7-alpine` + pinned SHA-256 in Compose |
| Django / Gunicorn / WhiteNoise | 5.2.18 / 26.2.0 / 6.12.0 |
| Django REST Framework / drf-spectacular | 3.18.3 / 0.30.0 |
| mozilla-django-oidc / PyJWT | 5.0.2 / 2.15.1 |

All application/transitive pins are in `requirements.txt`. Build tooling uses
pip26.2.2 and removes pip/ensurepip from the runtime image. No added runtime service.

## Actual verification

The new disposable project `portal-release-verify` used separate named volumes,
synthetic data, `127.0.0.3:80/443`, and `https://portal.release.localhost/`. The
existing portal occupied `127.0.0.1:80/443`; a real conflict test refused that bind
address without stopping/replacing it. Every HTTPS test trusted the exported
public Caddy certificate; TLS verification was never disabled.

| Check | Result |
| --- | --- |
| Original baseline `scripts/test.sh` | 252 passed, 0 failed, 88.645s. |
| Updated root `scripts/test.sh` | 259 passed, 0 failed, 101.119s. |
| Standalone Production image `scripts/test.sh` | 259 passed, 0 failed, 96.635s; system/deploy checks and migration drift passed. |
| New production security tests | Configuration denial/secure settings, mocked OIDC preflight/outage, all business API routes/methods reject anonymous requests, safe JSON500 and throttling. Included in 259. |
| Script failure harness | 22 passed, 0 failed. Includes failed/empty/corrupt dumps, checksums, cancellation, restore rollback/schema failure, update backup/build/migration failures, existing volume refusal, port conflicts, production auth gate, one-off-container exclusion and concurrent-operation locking. |
| Compose config, shell syntax, Git whitespace | Passed. |
| Fresh isolated install | Build, DB readiness, all existing migrations, role setup, static build, app/proxy health and verified HTTPS passed. |
| Repeated install | Returned existing healthy installation; no migration/config overwrite. |
| Real authenticated HTTPS workflows | 44 checks passed: customer/contact/service lifecycle, shared/general contact with email/phone, required-method rejection, ANY/ALL search and all-email export, imports, role restrictions, audit, explicit disposable cleanup, session/CSRF login and main GUI/API docs. |
| Backup-first isolated update | Verified pre-update backup and image record, rebuilt/migrated/restarted; HTTPS healthy. |
| Preloaded-image update | BUILD_IMAGE=0 selected the final standalone runtime image; update and repeated 44-check HTTPS workflow passed. |
| Full backup/restore | Verified dump/metadata; inserted a synthetic later record; explicitly restored only disposable project. Every model row count and SHA-256 matched the pre-backup snapshot afterward. |
| Full container recreation | All three containers recreated with retained volumes. Every model row count/hash still matched. |
| OpenAPI `spectacular --validate --fail-on-warn` | Passed without warnings. |
| Existing data | Original working installation counts/health unchanged; no write/restore against it. |
| Production overlay | Deployment checks with synthetic OIDC configuration; local-auth rejection tested. Live identity provider not contacted by that settings check. |
| Actual running container controls | Inspected UID10001, read-only app, dropped capabilities, CPU/memory/PID limits, log rotation and restart policies. Only proxy80/443 published. |
| Production bundle | Standalone build, 227-file checksum manifest and absence of private env/dumps/logs/keys/development-agent prompts verified. |

The first updated suite reported two failures because tests expected raw exceptions
instead of the new generic API500 response. Assertions were corrected and retained
the original database rollback checks. The first HTTPS test invocation needed its
container Python import path corrected. Real concurrent test containers exposed a
Compose service-discovery ambiguity; filtering out one-off containers fixed backup
and post-restore health checks, and recovery was repeated successfully. A sudo Git
provenance check initially refreshed index ownership; ownership was restored and
optional Git index writes disabled. No business data was affected by these fixes.

## Original security scanning and release hold

The Caddy findings in this original scan were subsequently fixed; see the
**Caddy security fix** section below. Application/DB findings remain separate.

`pip-audit2.10.1` initially found three DRF3.17.2 advisories. Updating to3.18.3
removed them; the repeat scan of 29 resolved pinned application packages reported
**0 known vulnerabilities**. These fixes are documented in the
[DRF maintainer release notes](https://www.django-rest-framework.org/community/release-notes/).
Trivy0.76.0 then scanned actual image archives/registry digests, without mounting
the Docker socket, private configuration or runtime data.

| Final image scan | Critical | High | Medium | Low | Unknown |
| --- | ---: | ---: | ---: | ---: | ---: |
| App runtime, after removing build tooling | 0 | 44 | 58 | 61 | 1 |
| PostgreSQL pinned official image | 1 | 25 | 31 | 3 | 1 |
| Caddy pinned official image | 0 | 6 | 14 | 1 | 1 |

Counts are package/advisory occurrences, not independently exploitable paths.
No Python-package findings remain in the final app runtime. Its remaining Debian
findings have **no fixed version listed by the scan**. The eight distinct high
IDs are CVE-2025-69720 (ncurses), CVE-2026-16742 (systemd-homed), CVE-2026-54369
(ACL), CVE-2026-76642 / 78408 / 78409 / 78410 (util-linux), and CVE-2026-9538
(Perl archive handling). The app does not expose these tools through its request
path, runs non-root with no capabilities on read-only storage, and imports JSON
only. This reduces applicability but is not a claim of formal exploit exclusion.
Track patched base images and obtain security review; do not blindly remove
essential OS libraries or switch image families to silence a scan.

PostgreSQL's critical CVE-2025-68121 and high Go findings are reported against
`/usr/local/bin/gosu`, not the PostgreSQL network daemon. The
[gosu helper](https://github.com/tianon/gosu) changes identity and execs a process;
TLS-server/client advisories are not obviously reachable there. Its privilege
helper dependencies still need reviewed applicability evidence or a patched
upstream build; the scan is not silently waived.

**Original Caddy blocker (subsequently resolved below).** Its binary contained
Go1.26.8 and x/net0.59.0. Reported high findings include CVE-2026-78669 (HTTP/2
SETTINGS denial of service), CVE-2026-78667 (HTTP Range handling),
CVE-2026-97031 (TLS ECH parsing), and CVE-2026-111943 (certificate validation).
The Alpine image also flags brotli CVE-2026-111497. Fixed library/toolchain
versions are listed, but the reviewed official [Caddy2.11.7 release](https://github.com/caddyserver/caddy/releases/tag/v2.11.7)
was still the current upstream release at verification time. The initial readiness
checkpoint withheld release rather than silently waiving these findings. The
separately requested Caddy fix below supplies and verifies a locked security build.

## Caddy security fix — 2026-10-27

Starting checkpoint: `fe25acfac3db4627fb18738c0b72d687b8fb9f1b` (clean working
tree). Caddy stays at2.11.7, with the exact same standard module set. Its Docker
build now uses Go1.26.10, x/net0.60.0, chi5.4.0 and checksum-locked transitive
dependencies. The upstream runtime base is retained with Brotli1.2.1-r0 and
curl/libcurl8.23.0-r0. All compilation occurs in a temporary Docker build stage;
no compiler, module cache or new runtime service is added to deployment.

The final Trivy0.76.0 scan reported **0 critical, 0 high, 0 medium and 0 low**
findings. It reports one UNKNOWN module-level advisory, GO-2026-5932, for
unmaintained x/crypto/OpenPGP. The [Go advisory](https://pkg.go.dev/vuln/GO-2026-5932)
specifically affects OpenPGP packages. None is in Caddy's compiled dependency
graph, and the build now fails if one enters that graph. No scanner suppression
or TLS/HTTP2 feature disabling was used. Metadata/package evidence is retained
inside the proxy image; see [Caddy security build](CADDY_SECURITY.md).

The fresh scan first exposed curl/libcurl findings absent from the October25
scan; these were fixed before the final scan. The original Go/TLS/HTTP2, chi,
Brotli and newly reported curl findings are all removed from the final image.

Install/update now build/check both application and proxy before downtime.
Offline mode checks that both images exist. Deployment records include the
running proxy image ID/tag/version for rollback. The clean Production bundle
includes the Dockerfile, go.mod/go.sum, standard entry point and operating guide.
No business model, Django behavior, database schema or production configuration
was changed. The original running portal was not updated.

Verification: **259 Django regression tests passed** (148.249s); **26 shell
operation checks passed**; **44 authenticated HTTPS workflow checks passed**;
**10 HTTPS/HTTP2 checks passed**, covering redirects,
TLS trust, HSTS, API authentication, login, static files, valid/invalid Range and
oversized input. The initial oversized-request test hit the earlier CSRF gate;
it was corrected to use a valid CSRF cookie/referer before testing size rejection.
The patched proxy's module names exactly match the upstream binary. Isolated
backup-first updates succeeded; all database model hashes/counts and the Caddy
public CA certificate matched the pre-update values. Standalone bundle build
and checksum verification passed; its Caddy binary and build/package metadata
are byte-identical to the tested source build (image metadata can differ).

**The Caddy-specific release hold is resolved.** This does not waive the
separate application/DB image findings, privilege limitations or live Keycloak
verification below, and does not authorize production deployment or a release tag.

## Remaining verification and acceptance

- **Do not deploy this candidate to production or tag v1.0.0** until the image
  security hold is resolved with patched images or an explicit reviewed security
  disposition and fresh testing.
- No live Keycloak test realm was supplied. Mocked cryptographic/session/role/API
  tests passed; real DNS/CA/client-secret/audience/MFA/logout and service-account
  integration must pass in staging before `OIDC_VERIFIED=1` and production enablement.
- The existing single PostgreSQL owner credential is used by runtime and migrations;
  least-privilege DB role separation remains a documented limitation.
- DRF throttles are best-effort per worker; no distributed rate-limit service is
  added. HA, PITR, site capacity/load tests, off-server backup transport/retention
  policy and graphical/mobile/clipboard inspection remain site responsibilities.
- No backups, Git stashes, source rollback snapshots or Docker volumes were deleted.

Installation, update and backup/restore commands and the full environment-variable
list are in [production installation](PRODUCTION_INSTALL.md),
[operations](OPERATIONS.md) and [backup/restore](BACKUP_RESTORE.md).
The next action is security/release review of this candidate, not a new business phase.
