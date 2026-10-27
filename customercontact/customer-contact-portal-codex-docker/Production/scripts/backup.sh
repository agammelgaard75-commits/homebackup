#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
lock_operation
healthy db || fail 'Database must be healthy before backup.'
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
file="$(mktemp "$backup_dir/portal-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX.dump.partial")"
partial="$file"
file="${partial%.partial}"
trap 'rm -f "$partial" "${file}.json.partial"' EXIT
compose exec -T db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-privileges' > "$partial" || fail 'Backup failed; no successful backup was published.'
verify_archive "$partial"
id="$(container_id app)"
[[ -n "$id" ]] || fail 'Cannot identify the deployed application version.'
metadata="$(docker inspect "$id")"
checksum="$(sha256sum "$partial" | cut -d ' ' -f1)"
jq --arg time "$(date -u +%FT%TZ)" --arg project "$project" --arg sha256 "$checksum" --arg file "$(basename "$file")" \
  '.[0] | {format:1, completed_at:$time, project:$project, file:$file, sha256:$sha256,
    image_id:.Image, image:.Config.Image, version:.Config.Labels["org.opencontainers.image.version"],
    revision:.Config.Labels["org.opencontainers.image.revision"]}' <<< "$metadata" > "$file.json.partial"
mv "$partial" "$file"
mv "$file.json.partial" "$file.json"
printf '%s\n' "$file" > "$state_dir/last-backup.partial"
mv "$state_dir/last-backup.partial" "$state_dir/last-backup"
echo "Verified backup: $file (metadata: $file.json)"
echo "Retention: $retention_days days. Review older backups with backup-retention.sh; nothing is deleted automatically."
