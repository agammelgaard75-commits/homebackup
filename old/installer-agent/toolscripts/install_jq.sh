#!/usr/bin/env bash
set -euo pipefail

# Check if jq is already installed
if command -v jq &> /dev/null; then
  echo "jq is already installed. Skipping installation."
  exit 0
fi

# Detect package manager
if command -v apt-get &> /dev/null; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq jq
elif command -v dnf &> /dev/null; then
  sudo dnf install -y -q jq
elif command -v yum &> /dev/null; then
  sudo yum install -y -q jq
else
  echo "Unsupported package manager. Skipping jq installation."
  exit 0
fi

# Verify installation
if command -v jq &> /dev/null; then
  echo "jq installed successfully."
else
  echo "Failed to install jq."
  exit 1
fi