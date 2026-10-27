#!/usr/bin/env bash
# Configuration is supplied explicitly; never overwrite an installation.
source "$(dirname "$0")/common.sh"
[[ $# == 0 ]] || fail 'Usage: ./scripts/install.sh (configure PORTAL_DOMAIN in .env first).'
validate_environment
lock_operation
if [[ -n "$(container_id db)" ]]; then
  require_health
  https_check
  echo "Existing installation is healthy at https://$domain/. Use update.sh for changes."
  exit 0
fi
volume="$(jq -r .volumes.postgres_data.name <<< "$configuration")"
if docker volume inspect "$volume" >/dev/null 2>&1; then
  fail 'Existing PostgreSQL volume found. Refusing a fresh installation; use the documented recovery/update procedure.'
fi
check_ports
prepare_image
if [[ "$DEPLOYMENT_MODE" == production ]]; then
  compose run --rm --no-deps app python manage.py check_oidc
fi
compose up -d --wait --wait-timeout 180 db
compose run --rm --no-deps app python manage.py migrate --noinput
compose run --rm --no-deps app python manage.py setup_roles
compose up -d --wait --wait-timeout 180 app proxy
require_health
https_check
record_deployment "$state_dir/deployed.json"
echo "Installation complete: https://$domain/"
echo 'Distribute the public Caddy CA certificate to managed clients. Configure off-server backups.'
if [[ "$DEPLOYMENT_MODE" == development ]]; then
  echo 'Development only: ./scripts/compose.sh exec app python manage.py createsuperuser'
else
  echo 'Sign in with an authorized Keycloak portal role; no local administrator was created.'
fi
