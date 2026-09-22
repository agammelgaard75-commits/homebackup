#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "install.sh must run as root" >&2
    exit 1
fi

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
STAGE_DIR=$(mktemp -d)
trap 'rm -rf "$STAGE_DIR"' EXIT HUP INT TERM
install -d -m 0755 /opt/ai-sysadmin/bin /opt/ai-sysadmin/splunk /etc/ai-sysadmin
install -d -m 0750 /var/lib/ai-sysadmin/changes /var/log/ai-sysadmin
install -m 0644 "$REPO_DIR/src/container_maintenance.py" /opt/ai-sysadmin/bin/container_maintenance.py
install -m 0755 "$REPO_DIR/src/ai_sysadmin.py" /opt/ai-sysadmin/bin/ai-sysadmin
install -m 0644 "$REPO_DIR/scripts/litellm_planner.py" /opt/ai-sysadmin/bin/litellm-planner.py
if [ ! -e /etc/ai-sysadmin/litellm.key ] && [ -f "$REPO_DIR/.secrets/litellm.key" ]; then
    install -m 0600 "$REPO_DIR/.secrets/litellm.key" /etc/ai-sysadmin/litellm.key
fi
install -m 0644 "$REPO_DIR/README.md" /opt/ai-sysadmin/README.md
install -m 0644 "$REPO_DIR/splunk/README.md" /opt/ai-sysadmin/splunk/README.md
if [ ! -e /etc/ai-sysadmin/config.toml ]; then
    install -m 0644 "$REPO_DIR/config/config.toml" /etc/ai-sysadmin/config.toml
fi
if [ ! -e /etc/ai-sysadmin/IGNORE.md ]; then
    install -m 0644 "$REPO_DIR/IGNORE.md" /etc/ai-sysadmin/IGNORE.md
fi
install -m 0644 "$REPO_DIR/systemd/ai-sysadmin-prepare.service" /etc/systemd/system/
python3 "$REPO_DIR/scripts/render_deployment.py" /etc/ai-sysadmin/config.toml "$STAGE_DIR"
install -m 0644 "$STAGE_DIR/ai-sysadmin-prepare.timer" /etc/systemd/system/
install -m 0644 "$REPO_DIR/systemd/ai-sysadmin-maintenance.service" /etc/systemd/system/
install -m 0644 "$STAGE_DIR/ai-sysadmin-maintenance.timer" /etc/systemd/system/
for PHASE in prepare maintenance; do
    install -d -m 0755 "/etc/systemd/system/ai-sysadmin-$PHASE.service.d"
    install -m 0644 "$STAGE_DIR/ai-sysadmin-$PHASE.containers.conf" "/etc/systemd/system/ai-sysadmin-$PHASE.service.d/50-containers.conf"
done
SPLUNK_DIR=$(python3 -c 'import tomllib; print(tomllib.load(open("/etc/ai-sysadmin/config.toml", "rb"))["splunk"]["home"])')
SPLUNK_INSTALL_APP=$(python3 -c 'import tomllib; print(int(tomllib.load(open("/etc/ai-sysadmin/config.toml", "rb"))["splunk"].get("install_app", True)))')
if [ "$SPLUNK_INSTALL_APP" -eq 0 ]; then
    echo "Splunk app installation deferred by configuration."
elif [ -x "$SPLUNK_DIR/bin/splunk" ]; then
    install -d -m 0755 "$SPLUNK_DIR/etc/apps/ai_sysadmin"
    cp -R "$STAGE_DIR/ai_sysadmin/default" "$STAGE_DIR/ai_sysadmin/metadata" "$SPLUNK_DIR/etc/apps/ai_sysadmin/"
    SPLUNK_GROUP=$(stat -c %G "$SPLUNK_DIR")
    chgrp "$SPLUNK_GROUP" /var/log/ai-sysadmin
    chmod 2750 /var/log/ai-sysadmin
    for log in /var/log/ai-sysadmin/*.jsonl; do
        [ -f "$log" ] || continue
        chgrp "$SPLUNK_GROUP" "$log"
        chmod 0640 "$log"
    done
    echo "Splunk app installed; activate using your normal Splunk reload/restart procedure."
else
    echo "Splunk not installed at configured location; integration remains pending." >&2
fi
install -m 0644 "$REPO_DIR/logrotate/ai-sysadmin" /etc/logrotate.d/ai-sysadmin
systemctl daemon-reload
echo "Installed. Timers were not enabled or started."
echo "Review, then run: systemctl enable --now ai-sysadmin-prepare.timer ai-sysadmin-maintenance.timer"
