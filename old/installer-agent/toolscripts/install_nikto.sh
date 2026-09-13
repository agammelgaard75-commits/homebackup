#!/usr/bin/env bash
set -euo pipefail

if command -v nikto &> /dev/null;
then
  echo " nikto already installed"
else
  if command -v apt &> /dev/null;
  then
    sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nikto
  elif command -v dnf &> /dev/null;
  then
    sudo dnf install -y -q nikto
  elif command -v yum &> /dev/null;
  then
    sudo yum install -y -q nikto
  else
    echo "Skipping nikto: Unsupported package manager"
  fi
fi

if [[ $? -eq 0 ]]; then echo "✓ nikto installed"; else echo "✗ nikto skipped"; fi