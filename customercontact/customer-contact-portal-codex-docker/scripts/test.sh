#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
compose up -d --wait --wait-timeout 180 db
# Unit tests use isolated test databases and include mocked OIDC cases.
test_app() { compose run --rm --no-deps -e AUTH_MODE=local -e PORTAL_ENV=development app python manage.py "$@"; }
test_app check
test_app check --deploy --fail-level WARNING
test_app makemigrations --check --dry-run
test_app test "$@"
