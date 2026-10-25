#!/usr/bin/env bash
# Host-utility-only failure tests; Docker is stubbed and no real stack is touched.
set -euo pipefail
source_dir="$(cd "$(dirname "$0")/../.." && pwd)"
fixture="$(mktemp -d)"
trap 'rm -rf "$fixture"' EXIT
mkdir -p "$fixture/scripts" "$fixture/bin"
cp "$source_dir"/scripts/*.sh "$fixture/scripts/"
cp "$source_dir/.env.example" "$fixture/.env.example"
touch "$fixture/manage.py"
export DOCKER_CALLS="$fixture/calls"
export PATH="$fixture/bin:$PATH"
cat > "$fixture/bin/docker" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$DOCKER_CALLS"
if [[ -n "${FAIL_ON:-}" && "$*" == *"$FAIL_ON"* ]]; then exit 1; fi
if [[ "$*" == *pg_dump* && "${EMPTY_DUMP:-0}" != 1 ]]; then printf 'disposable-dump'; fi
if [[ "$*" == *pg_restore* ]]; then cat >/dev/null; fi
STUB
chmod +x "$fixture/bin/docker"
cd "$fixture"
expect_failure() {
  if "$@" > "$fixture/output" 2>&1; then
    echo "Expected failure: $*" >&2; exit 1
  fi
}
reset_case() {
  : > "$DOCKER_CALLS"
  unset FAIL_ON EMPTY_DUMP
}
reset_case
export FAIL_ON=pg_dump
expect_failure ./scripts/backup.sh
[[ -z "$(find backups -type f -print -quit)" ]]
reset_case
export EMPTY_DUMP=1
expect_failure ./scripts/backup.sh
[[ -z "$(find backups -type f -print -quit)" ]]
reset_case
./scripts/backup.sh >/dev/null
./scripts/backup.sh >/dev/null
[[ "$(find backups -type f | wc -l)" -eq 2 ]]
for dump in backups/*; do [[ "$(stat -c %a "$dump")" == 600 ]]; done
reset_case
expect_failure ./scripts/restore.sh missing.dump
[[ ! -s "$DOCKER_CALLS" ]]
printf data > disposable.dump
reset_case
expect_failure ./scripts/restore.sh disposable.dump <<< CANCEL
! grep -q 'stop app' "$DOCKER_CALLS"
reset_case
export FAIL_ON=pg_restore
expect_failure ./scripts/restore.sh disposable.dump <<< RESTORE
grep -q 'stop app' "$DOCKER_CALLS"
! grep -q 'up .*app proxy' "$DOCKER_CALLS"
reset_case
export FAIL_ON='migrate --check'
expect_failure ./scripts/restore.sh disposable.dump <<< RESTORE
! grep -q 'up .*app proxy' "$DOCKER_CALLS"
reset_case
export FAIL_ON=pg_dump
expect_failure ./scripts/update.sh
! grep -q 'stop app' "$DOCKER_CALLS"
reset_case
export FAIL_ON='migrate --noinput'
expect_failure ./scripts/update.sh
grep -q 'stop app' "$DOCKER_CALLS"
! grep -q 'up .*app proxy' "$DOCKER_CALLS"
reset_case
expect_failure ./scripts/install.sh 'invalid/hostname'
[[ ! -s "$DOCKER_CALLS" ]]
reset_case
COMPOSE_PROJECT_NAME=portal-fixture PORT_BIND_IP=127.0.0.1 ./scripts/install.sh fixture.localhost >/dev/null
[[ "$(stat -c %a .env)" == 600 ]]
grep -q '^PORT_BIND_IP=127.0.0.1$' .env
grep -q '^COMPOSE_PROJECT_NAME=portal-fixture$' .env
! grep -q REPLACE_ON_INSTALL .env
before="$(sha256sum .env)"
./scripts/install.sh fixture.localhost >/dev/null
[[ "$before" == "$(sha256sum .env)" ]]
expect_failure ./scripts/install.sh different.localhost
printf 'Operational script checks passed (backup, restore, update, installer failure paths).\n'
