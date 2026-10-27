#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
legacy=0
if [[ "${1:-}" == --legacy ]]; then legacy=1; shift; fi
[[ $# == 1 && -s "$1" ]] || fail 'Usage: restore.sh [--legacy] backup.dump (legacy mode explicitly accepts old archives without metadata).'
file="$1"
validate_environment
lock_operation
healthy db || fail 'Start the target database and verify its health first.'
if [[ "$legacy" == 0 ]]; then
  [[ -s "$file.json" ]] || fail 'Backup metadata is required. For reviewed older archives use --legacy.'
  expected="$(jq -er '.sha256 | select(test("^[a-f0-9]{64}$"))' "$file.json")" || fail 'Invalid backup metadata.'
  [[ "$(sha256sum "$file" | cut -d ' ' -f1)" == "$expected" ]] || fail 'Backup checksum mismatch; nothing was stopped or changed.'
else
  echo 'Legacy archive: no recorded checksum or application version is available. Verify provenance and matching code independently.'
fi
verify_archive "$file"
echo "WARNING: This overwrites database contents in project $project with the selected snapshot. All later writes will be lost."
echo 'Use matching application/schema versions. Preserve a current backup separately before proceeding.'
read -r -p "Type RESTORE $project to confirm: " answer
[[ "$answer" == "RESTORE $project" ]] || fail 'Cancelled; database unchanged.'
compose stop app
trap 'result=$?; if [[ "$result" != 0 ]]; then compose stop app >&2 || true; echo "Restore failed. Application stopped; inspect database and schema compatibility before recovery." >&2; fi; exit "$result"' EXIT
compose exec -T db sh -c 'exec pg_restore --clean --if-exists --exit-on-error --single-transaction --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$file"
compose run --rm --no-deps app python manage.py migrate --check
compose run --rm --no-deps app python manage.py check
compose exec -T db sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM pg_constraint WHERE NOT convalidated"' | grep -qx 0
compose up -d --wait --wait-timeout 180 app proxy
require_health
https_check
record_deployment "$state_dir/deployed.json"
echo "Restore completed and health verified for $project. Perform an authenticated data spot-check."
