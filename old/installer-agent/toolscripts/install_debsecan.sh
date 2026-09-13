#!/usr/bin/env bash
set -euo pipefail

# Check if debsecan is already installed
if command -v debsecan &> /dev/null; then
    echo "debsecan is already installed."
    exit 0
fi

# Detect package manager
if command -v apt-get &> /dev/null; then
    echo "Installing debsecan via apt..."
    sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq debsecan
elif command -v dnf &> /dev/null; then
    echo "debsecan is not available for dnf-based systems. Skipping..."
elif command -v yum &> /dev/null; then
    echo "debsecan is not available for yum-based systems. Skipping..."
else
    echo "Unsupported package manager. Skipping debsecan installation."
fi

if command -v debsecan &> /dev/null; then
    echo "debsecan installation completed successfully."
else
    echo "Failed to install debsecan."
fi