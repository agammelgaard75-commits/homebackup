#!/usr/bin/env bash
# No Docker daemon/data used: exercise orchestration failures with controlled stubs.
set -euo pipefail
source_dir="$(cd "$(dirname "$0")/../.." && pwd)"
fixture="$(mktemp -d)"
trap 'rm -rf "$fixture"' EXIT
mkdir -p "$fixture/scripts" "$fixture/bin"
cp "$source_dir"/scripts/*.sh "$fixture/scripts/"
cp "$source_dir/VERSION" "$fixture/"
export DOCKER_CALLS="$fixture/calls" STUB_CONFIG="$fixture/config.json"
export DEPLOYMENT_MODE=development
export PORTAL_ENV_FILE="$fixture/.env"
export PATH="$fixture/bin:$PATH"
printf 'synthetic fixture\n' > "$PORTAL_ENV_FILE"
chmod 600 "$PORTAL_ENV_FILE"
cat > "$STUB_CONFIG" <<'JSON'
{"name":"fixture","services":{"app":{"image":"fixture-app:1.0.0","environment":{"PORTAL_DOMAIN":"fixture.localhost","DJANGO_DEBUG":"0","DJANGO_SECRET_KEY":"synthetic-secret-not-used-outside-tests-12345678901234567890","POSTGRES_PASSWORD":"synthetic-password-not-used-outside-tests-1234567890","AUTH_MODE":"local"}},"proxy":{"ports":[{"target":443,"host_ip":"127.0.0.9"}]}},"volumes":{"postgres_data":{"name":"fixture_postgres_data"}}}
JSON
cat > "$fixture/bin/docker" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$DOCKER_CALLS"
if [[ -n "${FAIL_ON:-}" && "$*" == *"$FAIL_ON"* ]]; then exit 1; fi
case "$*" in
  *'config --format json'*) cat "$STUB_CONFIG" ;;
  'ps -aq '*) [[ "${FRESH:-0}" == 1 ]] || printf 'fake-container\n' ;;
  'volume inspect '*) [[ "${OLD_VOLUME:-0}" == 1 ]] ;;
  'inspect --format '*) echo healthy ;;
  'inspect '*) printf '[{"Image":"sha256:fixture","Config":{"Image":"fixture:1.0.0","Labels":{"org.opencontainers.image.version":"1.0.0","org.opencontainers.image.revision":"fixture"}}}]' ;;
  *pg_dump*) [[ "${EMPTY_DUMP:-0}" == 1 ]] || printf 'synthetic-dump' ;;
  *pg_restore*) cat >/dev/null ;;
  *'SELECT 1'*) echo 1 ;;
  *'FROM pg_constraint'*) echo 0 ;;
  *' cp proxy:'*) printf 'synthetic-certificate' > "${!#}" ;;
esac
exit 0
STUB
cat > "$fixture/bin/curl" <<'STUB'
#!/usr/bin/env bash
printf '{"status": "ok"}'
STUB
cat > "$fixture/bin/ss" <<'STUB'
#!/usr/bin/env bash
[[ "${PORT_CONFLICT:-0}" != 1 ]] || echo 'LISTEN 0 128 127.0.0.9:443 0.0.0.0:*'
exit 0
STUB
chmod +x "$fixture/bin/"*
cd "$fixture"
count=0
passed() { count=$((count + 1)); }
expect_failure() {
  if "$@" > "$fixture/output" 2>&1; then echo "Expected failure: $*" >&2; cat "$fixture/output"; exit 1; fi
}
reset_case() { : > "$DOCKER_CALLS"; unset FAIL_ON EMPTY_DUMP FRESH OLD_VOLUME PORT_CONFLICT; }
reset_case
export FAIL_ON=pg_dump
expect_failure ./scripts/backup.sh
[[ -z "$(find backups -type f -print -quit)" ]]; passed
reset_case
export EMPTY_DUMP=1
expect_failure ./scripts/backup.sh
[[ -z "$(find backups -type f -print -quit)" ]]; passed
reset_case
export FAIL_ON='pg_restore --file='
expect_failure ./scripts/backup.sh
[[ -z "$(find backups -type f -print -quit)" ]]; passed
reset_case
./scripts/backup.sh >/dev/null
file="$(cat .state/fixture/last-backup)"
[[ -s "$file" && -s "$file.json" ]]
[[ "$(jq -r .sha256 "$file.json")" == "$(sha256sum "$file" | cut -d ' ' -f1)" ]]
[[ "$(stat -c %a "$file")" == 600 && "$(stat -c %a "$file.json")" == 600 ]]; passed
grep -q 'label=com.docker.compose.oneoff=False' "$DOCKER_CALLS"; passed
./scripts/backup.sh >/dev/null
[[ "$(find backups -name '*.dump' | wc -l)" == 2 ]]; passed
reset_case
expect_failure ./scripts/restore.sh missing.dump
! grep -q 'stop app' "$DOCKER_CALLS"; passed
reset_case
expect_failure ./scripts/restore.sh "$file" <<< CANCEL
! grep -q 'stop app' "$DOCKER_CALLS"; passed
reset_case
cp "$file" damaged.dump; cp "$file.json" damaged.dump.json; printf damaged >> damaged.dump
expect_failure ./scripts/restore.sh damaged.dump <<< 'RESTORE fixture'
! grep -q 'stop app' "$DOCKER_CALLS"; passed
reset_case
export FAIL_ON='pg_restore --file='
expect_failure ./scripts/restore.sh "$file" <<< 'RESTORE fixture'
! grep -q 'stop app' "$DOCKER_CALLS"; passed
reset_case
export FAIL_ON='pg_restore --clean'
expect_failure ./scripts/restore.sh "$file" <<< 'RESTORE fixture'
grep -q 'stop app' "$DOCKER_CALLS"
! grep -q 'up .*app proxy' "$DOCKER_CALLS"; passed
reset_case
export FAIL_ON='migrate --check'
expect_failure ./scripts/restore.sh "$file" <<< 'RESTORE fixture'
! grep -q 'up .*app proxy' "$DOCKER_CALLS"; passed
reset_case
./scripts/restore.sh "$file" <<< 'RESTORE fixture' >/dev/null
grep -q -- '--single-transaction' "$DOCKER_CALLS"; passed
reset_case
export FAIL_ON=pg_dump
expect_failure ./scripts/update.sh
! grep -q 'stop app' "$DOCKER_CALLS"; passed
reset_case
export FAIL_ON='build app'
expect_failure ./scripts/update.sh
! grep -q 'stop app' "$DOCKER_CALLS"; passed
reset_case
export FAIL_ON='migrate --noinput'
expect_failure ./scripts/update.sh
grep -q 'stop app' "$DOCKER_CALLS"
! grep -q 'up .*app proxy' "$DOCKER_CALLS"; passed
reset_case
before="$(sha256sum .env)"
./scripts/install.sh >/dev/null
[[ "$before" == "$(sha256sum .env)" ]]
! grep -q 'migrate --noinput' "$DOCKER_CALLS"; passed
reset_case
export FRESH=1 OLD_VOLUME=1
expect_failure ./scripts/install.sh
! grep -q 'build app' "$DOCKER_CALLS"; passed
reset_case
export FRESH=1 PORT_CONFLICT=1
expect_failure ./scripts/install.sh
! grep -q 'build app' "$DOCKER_CALLS"; passed
reset_case
expect_failure env DEPLOYMENT_MODE=production ./scripts/install.sh
! grep -q 'build app' "$DOCKER_CALLS"; passed
reset_case
./scripts/status.sh >/dev/null
./scripts/backup-retention.sh >/dev/null
! grep -qE 'rm |down |prune|stop ' "$DOCKER_CALLS"; passed
reset_case
(
  flock -x 9
  expect_failure ./scripts/backup.sh
) 9>.state/fixture/operation.lock
! grep -q pg_dump "$DOCKER_CALLS"; passed
printf 'Operational script tests: %s passed, 0 failed.\n' "$count"
