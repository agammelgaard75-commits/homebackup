#!/bin/sh
set -eu

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VALIDATE_DIR=$(mktemp -d)
trap 'rm -rf "$VALIDATE_DIR"' EXIT HUP INT TERM

python3 -m py_compile "$REPO_DIR/src/ai_sysadmin.py"
python3 -m unittest discover -s "$REPO_DIR/tests" -v
python3 - "$REPO_DIR/config/config.toml" <<'PY'
import sys, tomllib
with open(sys.argv[1], "rb") as handle:
    config = tomllib.load(handle)
assert config["policy"]["minimum_free_root_percent"] > 0
assert config["policy"]["package_update_timeout_seconds"] > 0
PY

sed "s#/var/lib/ai-sysadmin#$VALIDATE_DIR/state#; s#/var/log/ai-sysadmin#$VALIDATE_DIR/log#" \
    "$REPO_DIR/config/config.toml" > "$VALIDATE_DIR/config.toml"
"$REPO_DIR/src/ai_sysadmin.py" inspect --dry-run --config "$VALIDATE_DIR/config.toml"
"$REPO_DIR/src/ai_sysadmin.py" prepare --dry-run --config "$VALIDATE_DIR/config.toml" || test "$?" -eq 2
test -s "$VALIDATE_DIR/log/dry-run/audit.jsonl"
test -s "$VALIDATE_DIR/log/dry-run/health.jsonl"
test -s "$VALIDATE_DIR/state/dry-run/current-change"
test ! -e "$VALIDATE_DIR/state/current-change"
test ! -e "$VALIDATE_DIR/log/audit.jsonl"
CHANGE_ID=$(sed -n '1p' "$VALIDATE_DIR/state/dry-run/current-change")
CHANGE_FILE="$VALIDATE_DIR/state/dry-run/changes/$CHANGE_ID.txt"
test -s "$CHANGE_FILE"

# Exercise the configured host path, including safe refusal when AI is absent.
# Mocked regression tests separately cover successful execution and failures.
"$REPO_DIR/src/ai_sysadmin.py" prepare --dry-run --config "$VALIDATE_DIR/config.toml" || test "$?" -eq 2
"$REPO_DIR/src/ai_sysadmin.py" maintain --dry-run --config "$VALIDATE_DIR/config.toml" || test "$?" -eq 2
"$REPO_DIR/src/ai_sysadmin.py" maintain --dry-run --config "$VALIDATE_DIR/config.toml" || test "$?" -eq 1
grep -Eq '^Status: (CLOSED|FAILED)$' "$CHANGE_FILE"
test "$(grep -c 'Closed at:' "$CHANGE_FILE")" -eq 1
python3 "$REPO_DIR/scripts/render_deployment.py" "$VALIDATE_DIR/config.toml" "$VALIDATE_DIR/rendered"

if command -v systemd-analyze >/dev/null 2>&1; then
    for unit in "$REPO_DIR"/systemd/*; do
        sed "s#/opt/ai-sysadmin/bin/ai-sysadmin#$REPO_DIR/src/ai_sysadmin.py#" \
            "$unit" > "$VALIDATE_DIR/$(basename "$unit")"
    done
    cp "$VALIDATE_DIR/rendered/ai-sysadmin-prepare.timer" "$VALIDATE_DIR/"
    cp "$VALIDATE_DIR/rendered/ai-sysadmin-maintenance.timer" "$VALIDATE_DIR/"
    systemd-analyze verify "$VALIDATE_DIR"/*.service "$VALIDATE_DIR"/*.timer
fi
echo "Validation passed"
