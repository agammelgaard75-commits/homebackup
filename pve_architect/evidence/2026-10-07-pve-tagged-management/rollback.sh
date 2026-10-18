#!/bin/bash
set -eu
work_dir=/root/pve-network-tagged4-20261007
test ! -e "$work_dir/committed" || exit 0
cp -a "$work_dir/interfaces.before" /etc/network/interfaces
ifreload -a
