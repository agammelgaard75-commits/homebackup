#!/usr/bin/env bash
# Shared host orchestration. Never source .env as executable shell code.
set -Eeuo pipefail
umask 077
PORTAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PORTAL_ROOT"
fail() { echo "$*" >&2; exit 1; }
for utility in docker jq flock curl ss sha256sum; do
  command -v "$utility" >/dev/null || fail "Missing prerequisite: $utility (see docs/PRODUCTION_INSTALL.md)."
done
docker compose version >/dev/null 2>&1 || fail 'Docker Compose plugin is required.'
docker info >/dev/null 2>&1 || fail 'Docker Engine is unavailable or access is denied.'
export PORTAL_ENV_FILE="${PORTAL_ENV_FILE:-$PORTAL_ROOT/.env}"
export APP_VERSION="${APP_VERSION:-$(cat "$PORTAL_ROOT/VERSION")}"
if [[ -z "${GIT_REVISION:-}" ]]; then
  GIT_REVISION="$(git -C "$PORTAL_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
  if [[ "$GIT_REVISION" != unknown && -n "$(git --no-optional-locks -C "$PORTAL_ROOT" status --porcelain -- .)" ]]; then
    GIT_REVISION="${GIT_REVISION}-dirty"
  fi
fi
export GIT_REVISION
[[ -f "$PORTAL_ENV_FILE" ]] || fail 'Configure a private .env from .env.example first; existing configuration is never overwritten.'
[[ $(stat -c %a "$PORTAL_ENV_FILE") =~ ^[46]00$ ]] || fail 'Environment file must have mode 600 or 400.'
DEPLOYMENT_MODE="${DEPLOYMENT_MODE:-production}"
compose_args=(--env-file "$PORTAL_ENV_FILE" -f "$PORTAL_ROOT/compose.yaml")
case "$DEPLOYMENT_MODE" in
  production) compose_args+=(-f "$PORTAL_ROOT/compose.production.yaml") ;;
  development) ;;
  *) fail 'DEPLOYMENT_MODE must be production or development.' ;;
esac
compose() { docker compose "${compose_args[@]}" "$@"; }
# Resolved configuration contains secrets. Keep it in memory, never echo it.
configuration="$(compose config --format json)" || fail 'Compose configuration is invalid.'
setting() { jq -r --arg key "$1" '.services.app.environment[$key] // ""' <<< "$configuration"; }
project="$(jq -r .name <<< "$configuration")"
[[ "$project" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || fail 'Invalid Compose project name.'
domain="$(setting PORTAL_DOMAIN)"
[[ "$domain" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]] || fail 'PORTAL_DOMAIN must be a DNS hostname, without a scheme or port.'
state_dir="$PORTAL_ROOT/.state/$project"
backup_dir="${BACKUP_DIR:-$(setting BACKUP_DIR)}"
backup_dir="${backup_dir:-$PORTAL_ROOT/backups/$project}"
retention_days="${BACKUP_RETENTION_DAYS:-$(setting BACKUP_RETENTION_DAYS)}"
retention_days="${retention_days:-30}"
[[ "$retention_days" =~ ^[0-9]+$ ]] || fail 'BACKUP_RETENTION_DAYS must be a nonnegative integer.'
validate_environment() {
  local value key
  for key in DJANGO_SECRET_KEY POSTGRES_PASSWORD; do
    value="$(setting "$key")"
    [[ ${#value} -ge 32 && "$value" != *REPLACE* && "$value" != *SET_OUTSIDE* ]] || fail "Configure a strong $key before installation."
  done
  [[ "$(setting DJANGO_DEBUG)" == 0 ]] || fail 'Deployment scripts require DJANGO_DEBUG=0.'
  if [[ "$DEPLOYMENT_MODE" == production ]]; then
    [[ "$(setting AUTH_MODE)" == oidc ]] || fail 'Production requires AUTH_MODE=oidc. Local authentication is development-only.'
    value="$(setting DJANGO_SECRET_KEY)"
    [[ ${#value} -ge 50 ]] || fail 'Production Django secret must be at least 50 characters.'
    [[ "$(setting OIDC_ISSUER_URL)" == https://* && -n "$(setting OIDC_CLIENT_ID)" && -n "$(setting OIDC_CLIENT_SECRET)" ]] || fail 'Configure HTTPS OIDC issuer and client credentials.'
    [[ "$(setting OIDC_CLIENT_SECRET)" != *SET_OUTSIDE* && "$(setting OIDC_CLIENT_SECRET)" != *REPLACE* ]] || fail 'Replace the OIDC client secret placeholder.'
    [[ "$(setting OIDC_REDIRECT_URI)" == "https://$domain/oidc/callback/" ]] || fail 'OIDC_REDIRECT_URI must match the external HTTPS callback.'
    [[ "$(setting OIDC_VERIFIED)" == 1 ]] || fail 'Verify browser login, roles, logout and API tokens in staging, then explicitly set OIDC_VERIFIED=1.'
    [[ "$(jq -r .services.app.image <<< "$configuration")" != *:local ]] || fail 'Set APP_IMAGE to a versioned release tag in .env.'
  fi
}
lock_operation() {
  mkdir -p "$state_dir"
  if [[ "${PORTAL_LOCK_HELD:-}" != "$project" ]]; then
    exec 9>"$state_dir/operation.lock"
    flock -n 9 || fail 'Another installation, update, backup or restore is running.'
    export PORTAL_LOCK_HELD="$project"
  fi
}
container_id() {
  # Compose ps --all may include concurrent one-off test/management containers.
  docker ps -aq --filter "label=com.docker.compose.project=$project" \
    --filter "label=com.docker.compose.service=$1" --filter 'label=com.docker.compose.oneoff=False'
}
healthy() {
  local id
  id="$(container_id "$1")"
  [[ -n "$id" ]] && [[ "$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$id")" == healthy ]]
}
require_health() {
  for service in db app proxy; do healthy "$service" || fail "$service is not healthy; investigate before proceeding."; done
  compose exec -T db sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT 1"' | grep -qx 1 || fail 'Database connectivity failed.'
}
https_check() {
  local cert bind response
  cert="$(mktemp)"
  compose cp proxy:/data/caddy/pki/authorities/local/root.crt "$cert" >/dev/null 2>&1 || { rm -f "$cert"; fail 'Cannot read the public Caddy CA certificate.'; }
  bind="$(jq -r '.services.proxy.ports[] | select(.target == 443) | .host_ip // "0.0.0.0"' <<< "$configuration")"
  [[ "$bind" != 0.0.0.0 ]] || bind=127.0.0.1
  if ! response="$(curl --noproxy '*' --fail --silent --show-error --connect-timeout 5 --max-time 15 --cacert "$cert" --resolve "$domain:443:$bind" "https://$domain/health/")"; then
    rm -f "$cert"; fail 'HTTPS health check failed; no TLS verification was bypassed.'
  fi
  rm -f "$cert"
  [[ "$response" == '{"status": "ok"}' ]] || fail 'Application readiness check failed.'
}
check_ports() {
  local bind port occupied
  bind="$(jq -r '.services.proxy.ports[0].host_ip // "0.0.0.0"' <<< "$configuration")"
  for port in 80 443; do
    occupied="$(ss -H -ltn "sport = :$port" | awk '{print $4}')"
    while IFS= read -r address; do
      [[ -n "$address" ]] || continue
      if [[ "$bind" == 0.0.0.0 || "$address" == "$bind:$port" || "$address" == "0.0.0.0:$port" || "$address" == "*:$port" || "$address" == "[::]:$port" ]]; then
        fail "Port conflict on $address. No existing service has been stopped or replaced."
      fi
    done <<< "$occupied"
  done
}
prepare_image() {
  if [[ "${BUILD_IMAGE:-1}" == 1 ]]; then
    compose build app
    compose build proxy
  else
    docker image inspect "$(jq -r .services.app.image <<< "$configuration")" >/dev/null || fail 'Load the reviewed application image first.'
    docker image inspect "$(jq -r .services.proxy.image <<< "$configuration")" >/dev/null || fail 'Load the reviewed proxy image first.'
  fi
  # Catch invalid proxy images/configuration before any application downtime.
  compose run --rm --no-deps proxy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
  compose run --rm --no-deps app python manage.py check --deploy --fail-level WARNING
}
record_deployment() {
  local destination="$1" id proxy_id proxy_metadata
  id="$(container_id app)"
  proxy_id="$(container_id proxy)"
  proxy_metadata="$(docker inspect "$proxy_id" | jq '.[0] | {image_id:.Image, image:.Config.Image, version:.Config.Labels["org.opencontainers.image.version"]}')"
  docker inspect "$id" | jq --arg time "$(date -u +%FT%TZ)" --arg project "$project" --argjson proxy "$proxy_metadata" \
    '.[0] | {recorded_at:$time, project:$project, image_id:.Image, image:.Config.Image,
      version:.Config.Labels["org.opencontainers.image.version"], revision:.Config.Labels["org.opencontainers.image.revision"], proxy:$proxy}' > "$destination.partial"
  mv "$destination.partial" "$destination"
}
verify_archive() {
  [[ -s "$1" ]] || fail 'Backup is missing or empty.'
  # Read/decompress the complete archive, not just its header/table of contents.
  compose exec -T db pg_restore --file=/dev/null < "$1" || fail 'Backup archive validation failed.'
}
