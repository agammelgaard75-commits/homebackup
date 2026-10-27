#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
compose ps -a
id="$(container_id app)"
if [[ -n "$id" ]]; then
  docker inspect "$id" | jq -r '.[0].Config.Labels | "Application version: \(.["org.opencontainers.image.version"] // "unknown")\nSource revision: \(.["org.opencontainers.image.revision"] // "unknown")"'
fi
result=0
for service in db app proxy; do
  if healthy "$service"; then echo "$service: healthy"; else echo "$service: unavailable"; result=1; fi
done
if compose exec -T db sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT 1"' 2>/dev/null | grep -qx 1; then
  echo 'Database connectivity: OK'
else
  echo 'Database connectivity: FAILED'; result=1
fi
if [[ -f "$state_dir/last-backup" ]]; then
  file="$(cat "$state_dir/last-backup")"
  if [[ -s "$file" && -s "$file.json" ]]; then
    jq -r '"Last successful backup: \(.completed_at) (\(.file)); application \(.version // "unknown")"' "$file.json"
  else echo 'Last backup is missing locally; verify off-server storage.'; fi
else echo 'Last successful backup: unknown'; fi
df -h "$PORTAL_ROOT"
exit "$result"
