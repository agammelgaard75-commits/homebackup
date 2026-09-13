#!/usr/bin/env bash
set -euo pipefail

# Check if openscap is already installed
if command -v oscap &> /dev/null; then
  echo "openscap is already installed. Skipping installation."
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
  echo "Unsupported package manager. Skipping openscap installation."
  exit 0
fi

# Install openscap based on package manager
if [ "$PACKAGE_MANAGER" = "apt" ]; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openscap
elif [ "$PACKAGE_MANAGER" = "dnf" ]; then
  sudo dnf install -y -q openscap
elif [ "$PACKAGE_MANAGER" = "yum" ]; then
  sudo yum install -y -q openscap
fi

# Verify installation
if command -v oscap &> /dev/null; then
  echo "Successfully installed openscap."
else
  echo "Failed to install openscap."
fi