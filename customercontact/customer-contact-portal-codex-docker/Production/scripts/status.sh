#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose ps
printf '\nRecent application logs:\n'
docker compose logs --tail 35 app
