#!/usr/bin/env bash
# Controlled update; app remains stopped if a migration/check fails.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose config --quiet

echo "1/6: Backing up the current database"
./scripts/backup.sh

echo "2/6: Stopping application to prevent writes during migrations"
docker compose stop app

echo "3/6: Pulling the explicitly configured Docker images"
docker compose pull db proxy

echo "4/6: Rebuilding Django app from reviewed source"
docker compose build --pull app

echo "5/6: Starting database and applying migrations"
docker compose up -d --wait db
docker compose run --rm --no-deps app python manage.py migrate --noinput
docker compose run --rm --no-deps app python manage.py setup_roles
docker compose run --rm --no-deps app python manage.py check --deploy --fail-level WARNING

echo "6/6: Starting app and proxy"
docker compose up -d --wait --force-recreate app proxy

echo "Update complete. Verify login, roles and application health."
echo "If an update fails, inspect logs and restore the matching code revision before restoring a backup."
