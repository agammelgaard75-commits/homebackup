#!/usr/bin/env bash
set -euo pipefail

if command -v nmap &> /dev/null;
then
  echo " nmap already installed"
else
  if command -v apt &> /dev/null;
  then
    sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nmap
  elif command -v dnf &> /dev/null;
  then
    sudo dnf install -y -q nmap
  elif command -v yum &> /dev/null;
  then
    sudo yum install -y -q nmap
  else
    echo "Skipping nmap: Unsupported package manager"
  fi
fi

if [[ $? -eq 0 ]]; then echo "✓ nmap installed"; else echo "✗ nmap skipped"; fi