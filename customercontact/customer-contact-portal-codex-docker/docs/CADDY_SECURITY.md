# Caddy security rebuild

The portal keeps Caddy **2.11.7** and its standard modules, but builds a patched
binary instead of deploying the affected upstream precompiled binary. This uses
Caddy's [documented custom-build entry point](https://github.com/caddyserver/caddy/blob/v2.11.7/cmd/caddy/main.go)
without changing Caddy's implementation or introducing plugins/runtime services.
All compilation runs in Docker; the host does not need Go.

## Pinned inputs

- `deploy/caddy/Dockerfile` pins Go **1.26.10** and the official Caddy base image
  by exact version **and SHA-256**. The runtime retains the upstream paths,
  entrypoint, CA trust, `/data` and `/config` behavior.
- `deploy/caddy/go.mod` and `go.sum` lock the complete module graph and checksums.
  Builds verify downloaded modules and use `-mod=readonly` with `GOTOOLCHAIN=local`;
  they cannot silently resolve newer dependencies or auto-download another compiler.
- `golang.org/x/net` is **0.60.0**; `github.com/go-chi/chi/v5` is **5.4.0**.
- Alpine `brotli-libs` is upgraded to exactly **1.2.1-r0**, and `curl`/`libcurl`
  to **8.23.0-r0**, using the upstream
  signed package repository. If this exact revision becomes unavailable, the
  build fails; review a new pin rather than substituting an unreviewed version.
- Runtime build metadata and the compiled-package list are available at
  `/usr/share/caddy-build/build-info.txt` and `/usr/share/caddy-build/packages.txt`.
  The compiler and module cache do not enter the runtime image.

Go1.26.10 includes the October TLS/HTTP security corrections and certificate
validation fix; see the [Go release history](https://go.dev/doc/devel/release).
The rebuild addresses the previously reported Go HTTP/2 SETTINGS, Range, TLS ECH
and certificate-validation findings, the x/net findings, the chi finding and the
Alpine Brotli out-of-bounds write. The fresh scan also identified curl/libcurl
advisories, so those packages are patched in the same runtime image.
It does not disable HTTP/2 or TLS validation.

## Build and update

The proxy image defaults to `<COMPOSE_PROJECT_NAME>-proxy:2.11.7-portal.1`.
`PROXY_IMAGE` can select a reviewed registry tag/digest. Build with:

```bash
./scripts/compose.sh build proxy
```

The ordinary install/update flow builds **both app and proxy** and validates the
Caddy configuration before stopping the current app. `BUILD_IMAGE=0` requires
both reviewed images to be loaded already. Pre-update/deployed JSON records now
include the running proxy image ID/tag/version as well as the app metadata.

For an approved deployment after reviewing the other release prerequisites:

```bash
./scripts/update.sh
./scripts/tests/proxy.sh
```

This source change is not an authorization to modify a production server.
There is no database migration. Existing Caddy certificate/CA/config volumes and
all customer data remain in place. Never delete them to install a proxy patch.
The read-only proxy regression script requires a curl build with HTTP/2 support
and verifies TLS using the exported **public** Caddy root certificate.

To restore a previously reviewed compatible proxy image, use its saved image ID
and matching configuration with `PROXY_IMAGE=<saved-image-ID-or-tag>
./scripts/compose.sh up -d --no-deps --wait proxy`. Returning to the old vulnerable
binary reintroduces the security exposure; do so only under an explicit incident
response decision. No database restore is needed for this proxy-only change.

## Maintenance

This is a maintained security build until an upstream image contains the fixes.
For later upgrades, review Go and Caddy advisories, update pinned versions in a
container, regenerate/review go.mod/go.sum, rebuild and rescan the **final image**.
Compare the standard module set and test HTTPS, HTTP/2, redirects, static files,
Range requests, authentication/CSRF and the portal workflows before deployment.
Keep a versioned proxy artifact for offline installation and rollback; never use
an unversioned mutable tag or add plugins merely to fix a toolchain vulnerability.

See [release verification](RELEASE_VERIFICATION.md) for measured results and the
remaining non-Caddy production-readiness items.

The final scan on2026-10-27 has no critical/high/medium/low findings. One
module-level UNKNOWN advisory remains for x/crypto/OpenPGP; the affected packages
are absent from the compiled dependency graph and a build guard prevents their
introduction. No findings are hidden with a scanner ignore file.

Verified Linux/amd64 Caddy binary SHA-256:
`0a0b68b5061f39347dd601a0d2b1c88453933a9941cae0d9eb756806d4d31115`.
The repository and standalone Production build produced identical binary and
build/package metadata hashes. Their exact runtime images were both scanned.
