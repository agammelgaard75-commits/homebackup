# Operator-approved software exceptions

# Format: `- software-name: reason`. Names are case-insensitive. Each entry
# omits that software from automatic updates while retaining inventory and
# publishing its status to the Ignored Software dashboard.

- splunk: Retain the installed release because newer releases require unsupported CPU architecture features.
