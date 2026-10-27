#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
validate_environment
lock_operation
require_health
https_check
record="$state_dir/pre-update-$(date -u +%Y%m%dT%H%M%SZ)-$$.json"
record_deployment "$record"
"$PORTAL_ROOT/scripts/backup.sh"
echo "Previous deployment recorded: $record"
# Build/check both reviewed images while the current app serves; no DB upgrade.
prepare_image
if [[ "$DEPLOYMENT_MODE" == production ]]; then
  compose run --rm --no-deps app python manage.py check_oidc
fi
compose stop app
trap 'echo "Update failed; no automatic database rollback was attempted. Use the recorded deployment and backup; see docs/OPERATIONS.md." >&2' ERR
compose run --rm --no-deps app python manage.py migrate --noinput
compose run --rm --no-deps app python manage.py setup_roles
compose up -d --wait --wait-timeout 180 --no-deps --force-recreate app proxy
require_health
https_check
record_deployment "$state_dir/deployed.json"
echo "Update complete and HTTPS health verified: https://$domain/"
