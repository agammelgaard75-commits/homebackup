#!/usr/bin/env bash
# Destructive restore into the explicitly selected Compose project only.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $# -ne 1 || ! -s "$1" ]]; then
  echo "Usage: $0 path/to/nonempty-backup.dump" >&2; exit 2
fi
file="$1"
docker compose config --quiet
read -r -p "This REPLACES the configured database contents. Type RESTORE to proceed: " answer
if [[ "$answer" != 'RESTORE' ]]; then
  echo "Cancelled."; exit 1
fi

echo "Stopping app to prevent concurrent writes"
docker compose stop app
docker compose up -d --wait db
if ! docker compose exec -T db sh -c 'exec pg_restore --clean --if-exists --exit-on-error --single-transaction --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$file"; then
  echo "Restore failed. Application remains stopped for investigation." >&2
  exit 1
fi
# Restore only a dump from the matching code/schema revision; do not migrate it here.
docker compose run --rm --no-deps app python manage.py migrate --check
docker compose run --rm --no-deps app python manage.py check
docker compose up -d --wait app proxy
echo "Restore completed. Verify data, user login, and application version compatibility."
