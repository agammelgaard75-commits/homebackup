#!/bin/sh
exec /usr/bin/timeout 25s /usr/bin/python3 /opt/splunk/etc/apps/server_health/bin/journal_events.py
