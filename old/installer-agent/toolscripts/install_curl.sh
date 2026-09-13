#!/usr/bin/env bash
set -euo pipefail

# Check if curl is already installed
if command -v curl &> /dev/null; then
  echo "curl is already installed. Skipping installation."
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
  echo "Unsupported package manager. Skipping curl installation."
  exit 0
fi

# Install curl based on the detected package manager
if [ "$PACKAGE_MANAGER" = "apt" ]; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq curl
elif [ "$PACKAGE_MANAGER" = "dnf" ]; then
  sudo dnf install -y -q curl
elif [ "$PACKAGE_MANAGER" = "yum" ]; then
  sudo yum install -y -q curl
fi

# Verify installation
if command -v curl &> /dev/null; then
  echo "curl installed successfully."
else
  echo "Failed to install curl."
  exit 1
fi
