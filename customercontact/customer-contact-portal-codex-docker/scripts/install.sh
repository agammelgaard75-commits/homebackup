#!/usr/bin/env bash
# Usage: ./scripts/install.sh portal.home.lab
# Run on target server. Host needs only Docker Engine + Compose plugin + Bash.
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077

domain="${1:-portal.home.lab}"
if [[ ! "$domain" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]]; then
  echo "Invalid DNS hostname: $domain" >&2; exit 2
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Engine with the Docker Compose v2 plugin is required." >&2; exit 1
fi

if [[ ! -e .env ]]; then
  cp .env.example .env
  # Generate secrets without installing Python or OpenSSL on the host.
  secret="$(od -An -tx1 -N 48 /dev/urandom | tr -d ' \n')"
  db_secret="$(od -An -tx1 -N 32 /dev/urandom | tr -d ' \n')"
  sed -i \
    -e "s|^PORTAL_DOMAIN=.*|PORTAL_DOMAIN=${domain}|" \
    -e "s|^COMPOSE_PROJECT_NAME=.*|COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-customer-contact-portal}|" \
    -e "s|^PORT_BIND_IP=.*|PORT_BIND_IP=${PORT_BIND_IP:-0.0.0.0}|" \
    -e "s|^DJANGO_ALLOWED_HOSTS=.*|DJANGO_ALLOWED_HOSTS=${domain},127.0.0.1,localhost|" \
    -e "s|^DJANGO_CSRF_TRUSTED_ORIGINS=.*|DJANGO_CSRF_TRUSTED_ORIGINS=https://${domain}|" \
    -e "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=${secret}|" \
    -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${db_secret}|" \
    .env
  chmod 600 .env
  echo "Created .env with generated passwords and domain ${domain}."
else
  existing_domain="$(sed -n 's/^PORTAL_DOMAIN=//p' .env | head -n 1)"
  if [[ -z "$existing_domain" ]]; then
    echo "Existing .env lacks PORTAL_DOMAIN." >&2; exit 1
  fi
  if [[ $# -ge 1 && "$domain" != "$existing_domain" ]]; then
    echo "Existing .env uses ${existing_domain}; change it manually to change domain." >&2
    exit 1
  fi
  domain="$existing_domain"
fi
chmod 600 .env

if grep -Eq '^(DJANGO_SECRET_KEY|POSTGRES_PASSWORD)=REPLACE_ON_INSTALL' .env; then
  echo "Set DJANGO_SECRET_KEY and POSTGRES_PASSWORD in .env before continuing." >&2
  exit 1
fi

if [[ ! -f manage.py ]]; then
  echo "Django application not created yet. Ask Codex to finish Phase 1 first." >&2
  exit 1
fi

docker compose config --quiet
docker compose build --pull app
docker compose up -d --wait db
docker compose run --rm --no-deps app python manage.py migrate --noinput
docker compose run --rm --no-deps app python manage.py setup_roles
docker compose run --rm --no-deps app python manage.py check --deploy --fail-level WARNING
docker compose up -d --wait app proxy

echo
echo "Portal deployed. URL: https://${domain}/"
echo "Create first admin: docker compose exec app python manage.py createsuperuser"
echo "IMPORTANT: Trust the local Caddy CA on clients; see docs/DOCKER_OPERATIONS.md."
echo "IMPORTANT: Back up the database off-server; run ./scripts/backup.sh."
