#!/usr/bin/env bash
# Maintainer-only allowlisted bundle refresh. Never copies env/data or removes files.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v rg >/dev/null || { echo 'ripgrep is required for source packaging.' >&2; exit 1; }
manifest="$(mktemp)"
trap 'rm -f "$manifest"' EXIT
rg --files apps config deploy scripts static schemas examples |
  grep -E '(\.py|\.html|\.css|\.js|\.json|\.sh|\.go|/go\.mod|/go\.sum|/Dockerfile|/Caddyfile)$' |
  grep -v '^scripts/package-production.sh$' > "$manifest"
printf '%s\n' Dockerfile compose.yaml compose.production.yaml requirements.txt manage.py VERSION .env.example .env.development.example .gitignore .dockerignore >> "$manifest"
for doc in PRODUCTION_INSTALL OPERATIONS BACKUP_RESTORE SECURITY CADDY_SECURITY TROUBLESHOOTING RELEASE_VERIFICATION KEYCLOAK_OIDC REST_API JSON_IMPORT_FORMAT DOCKER_OPERATIONS; do
  printf 'docs/%s.md\n' "$doc" >> "$manifest"
done
while IFS= read -r source; do
  [[ -f "$source" && ! -L "$source" ]] || { echo "Refusing nonregular source: $source" >&2; exit 1; }
  mkdir -p "Production/$(dirname "$source")"
  cp -p "$source" "Production/$source"
done < "$manifest"
# Production README/architecture are intentionally curated, not planning docs.
printf '%s\n' README.md docs/ARCHITECTURE.md >> "$manifest"
(cd Production && sort -u "$manifest" | xargs sha256sum > FILES.sha256)
echo 'Production bundle refreshed. No existing file or runtime data was deleted.'
