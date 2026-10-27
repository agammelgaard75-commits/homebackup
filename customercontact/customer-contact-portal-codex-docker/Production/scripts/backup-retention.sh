#!/usr/bin/env bash
# Read-only inventory. Deletion always requires separate operator approval.
source "$(dirname "$0")/common.sh"
[[ -d "$backup_dir" ]] || exit 0
[[ "$retention_days" != 0 ]] || { echo 'Retention review disabled (keep indefinitely).'; exit 0; }
echo "Backup metadata older than $retention_days days (review off-server copies and retention obligations before removal):"
find "$backup_dir" -maxdepth 1 -type f -name 'portal-*.dump.json' -mtime "+$retention_days" -print
