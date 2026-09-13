#!/usr/bin/env bash
set -euo pipefail

# Run individual install scripts in order
source toolscripts/install_lynis.sh
source toolscripts/install_nmap.sh
source toolscripts/install_nikto.sh
source toolscripts/install_debsecan.sh
source toolscripts/install_needrestart.sh
source toolscripts/install_rkhunter.sh
source toolscripts/install_chkrootkit.sh
source toolscripts/install_openscap.sh
source toolscripts/install_jq.sh
source toolscripts/install_curl.sh

echo "All tools installed successfully"