#!/usr/bin/env bash
set -euo pipefail

# Check if needrestart is already installed
if command -v needrestart &> /dev/null; then
  echo "needrestart is already installed."
  exit 0
fi

# Detect package manager
if command -v apt-get &> /dev/null; then
  echo "Installing needrestart via apt..."
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq needrestart
elif command -v dnf &> /dev/null; then
  echo "Installing needrestart via dnf..."
  sudo dnf install -y -q needrestart
elif command -v yum &> /dev/null; then
  echo "Installing needrestart via yum..."
  sudo yum install -y -q needrestart
else
  echo "Skipping needrestart: Unsupported package manager"
  exit 0
fi

# Verify installation
if command -v needrestart &> /dev/null; then
  echo "needrestart installed successfully."
else
  echo "Failed to install needrestart."
  exit 1
fi