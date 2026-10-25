#!/usr/bin/env bash
# Custom-format PostgreSQL dump; atomic publication and private permissions.
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p backups
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
file="$(mktemp "backups/customer-portal-${stamp}-XXXXXX.dump")"
partial="${file}.partial"
trap 'rm -f "$partial"; [[ -s "$file" ]] || rm -f "$file"' EXIT
if ! docker compose exec -T db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-privileges' > "$partial"; then
  echo "Backup failed; incomplete file deleted." >&2
  exit 1
fi
if [[ ! -s "$partial" ]]; then
  echo "Backup is empty; operation failed." >&2
  exit 1
fi
mv "$partial" "$file"
chmod 600 "$file"
echo "Backup written: $file"
echo "Copy it to encrypted off-server storage and regularly test restores."
