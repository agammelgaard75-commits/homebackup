#!/usr/bin/env bash
set -euo pipefail

if command -v lynis &> /dev/null;
then
  echo " lynis already installed"
else
  if command -v apt &> /dev/null;
  then
    sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq lynis
  elif command -v dnf &> /dev/null;
  then
    sudo dnf install -y -q lynis
  elif command -v yum &> /dev/null;
  then
    sudo yum install -y -q lynis
  else
    echo "Skipping lynis: Unsupported package manager"
  fi
fi

if [[ $? -eq 0 ]]; then echo "✓ lynis installed"; else echo "✗ lynis skipped"; fi