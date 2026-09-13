#!/usr/bin/env bash
set -euo pipefail

# Check if rkhunter is already installed
if command -v rkhunter &> /dev/null; then
  echo "rkhunter is already installed. Skipping installation."
  exit 0
fi

# Detect package manager
if command -v apt-get &> /dev/null; then
  echo "Detected Debian/Ubuntu system. Installing rkhunter via apt."
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq rkhunter
elif command - v dnf &> /dev/null; then
  echo "Detected RHEL-based system. Installing rkhunter via dnf."
  sudo dnf install -y -q rkhunter
elif command -v yum &> /dev/null; then
  echo "Detected RHEL-based system. Installing rkhunter via yum."
  sudo yum install -y -q rkhunter
else
  echo "Unsupported package manager. Skipping rkhunter installation."
  exit 1
fi

# Verify installation
if command -v rkhunter &> /dev/null; then
  echo "rkhunter installation completed successfully."
else
  echo "Failed to install rkhunter. Please check package availability."
  exit 1
fi