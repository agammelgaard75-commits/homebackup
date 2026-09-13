#!/usr/bin/env bash
set -euo pipefail

# Check if chkrootkit is already installed
if command -v chkrootkit &> /dev/null; then
  echo "[INFO] chkrootkit is already installed. Skipping installation."
  exit 0
fi

# Detect package manager
if command -v apt-get &> /dev/null; then
  PACKAGE_MANAGER="apt"
elif command -v dnf &> /dev/null; then
  PACKAGE_MANAGER="dnf"
elif command -v yum &> /dev/null; then
  PACKAGE_MANAGER="yum"
else
  echo "[ERROR] Unsupported package manager. Skipping chkrootkit installation."
  exit 1
fi

# Install chkrootkit based on package manager
if [ "$PACKAGE_MANAGER" = "apt" ]; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq chkrootkit
elif [ "$PACKAGE_MANAGER" = "dnf" ]; then
  sudo dnf install -y -q chkrootkit
elif [ "$PACKAGE_MANAGER" = "yum" ]; then
  sudo yum install -y -q chkrootkit
fi

# Verify installation
if command -v chkrootkit &> /dev/null; then
  echo "[SUCCESS] chkrootkit installed successfully."
else
  echo "[ERROR] Failed to install chkrootkit."
  exit 1
fi