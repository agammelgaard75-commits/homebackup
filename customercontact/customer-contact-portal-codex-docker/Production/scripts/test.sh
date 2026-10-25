#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose config --quiet
docker compose up -d --wait db
docker compose run --rm --no-deps app python manage.py check
docker compose run --rm --no-deps app python manage.py check --deploy --fail-level WARNING
docker compose run --rm --no-deps app python manage.py makemigrations --check --dry-run
docker compose run --rm --no-deps app python manage.py test
