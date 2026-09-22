#!/usr/bin/env bash
set -Eeuo pipefail

CONTAINER="n8n"

# Directory this script backs up.
# Change this to a fixed path if preferred.
REPO_DIR="$(pwd)"

WORKFLOW_DIR="$REPO_DIR/workflows"

REMOTE="origin"
BRANCH="main"

echo "======================================"
echo "Backup directory: $REPO_DIR"
echo "======================================"

#
# Make sure this is a Git repository
#
if [ ! -d "$REPO_DIR/.git" ]; then
    echo "ERROR: $REPO_DIR is not a Git repository."
    exit 1
fi

#
# Check for nested Git repositories
#
echo "Checking for nested Git repositories..."

mapfile -t NESTED_GIT < <(
    find "$REPO_DIR" \
        -path "$REPO_DIR/.codex/.tmp" -prune -o \
        -mindepth 2 \
        -type d \
        -name .git \
        -print
)

if [ ${#NESTED_GIT[@]} -gt 0 ]; then
    echo
    echo "WARNING: Nested Git repositories found:"
    printf '  %s\n' "${NESTED_GIT[@]}"
    echo
    echo "These directories cannot safely be included as normal files"
    echo "in the parent Git repository."
    echo
    exit 2
fi

#
# Export n8n workflows
#
echo "Exporting n8n workflows..."

mkdir -p "$WORKFLOW_DIR"

sudo docker exec "$CONTAINER" sh -c \
    'rm -rf /tmp/workflows &&
     mkdir -p /tmp/workflows &&
     n8n export:workflow --backup --output=/tmp/workflows'

#
# Remove previous workflow export.
# This makes workflow deletions appear correctly in Git.
#
find "$WORKFLOW_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +

#
# Copy fresh workflows from n8n container
#
sudo docker cp \
    "$CONTAINER":/tmp/workflows/. \
    "$WORKFLOW_DIR/"

#
# Only fix ownership on files Docker copied.
# Do NOT chown the entire project.
#
sudo chown -R "$USER:$(id -gn)" "$WORKFLOW_DIR"

#
# Clean temporary container files
#
sudo docker exec "$CONTAINER" \
    rm -rf /tmp/workflows

#
# Git backup
#
cd "$REPO_DIR"

echo "Adding changes..."

git add -A

#
# Nothing changed?
#
if git diff --cached --quiet; then
    echo "No changes found."
    exit 0
fi

echo
echo "Changes:"
git status --short
echo

TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"

git commit -m "Automatic backup $TIMESTAMP"

echo "Pushing to GitHub..."

git push "$REMOTE" "$BRANCH"

echo
echo "Backup completed successfully."
