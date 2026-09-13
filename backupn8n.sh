#!/usr/bin/env bash
set -euo pipefail

CONTAINER="n8n"
REPO_DIR="$HOME/n8n-stock-agent"
WORKFLOW_DIR="$REPO_DIR/workflows"

mkdir -p "$WORKFLOW_DIR"

echo "Exporting n8n workflows..."

sudo docker exec "$CONTAINER" sh -c \
  'rm -rf /tmp/workflows &&
   mkdir -p /tmp/workflows &&
   n8n export:workflow --backup --output=/tmp/workflows'

# Clear old exports so deleted workflows are also removed from Git
find "$WORKFLOW_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +

sudo docker cp "$CONTAINER":/tmp/workflows/. "$WORKFLOW_DIR/"
sudo chown -R "$USER:$USER" "$REPO_DIR"

cd "$REPO_DIR"

git add workflows

if git diff --cached --quiet; then
    echo "No workflow changes found."
    exit 0
fi

git commit -m "Backup n8n workflows $(date '+%Y-%m-%d %H:%M:%S')"
git push origin main

echo "Backup committed and pushed successfully."
