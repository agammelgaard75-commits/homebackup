
set -eu
export LC_ALL=C
printf '\n=== Baseline ===\n'
date -u
pveversion
cat /proc/sys/kernel/random/boot_id
qm list
pct list
pvesm status
df -h / /boot
systemctl --failed --no-pager
dpkg --audit
apt-mark showhold
printf '\n=== Configuration checksums ===\n'
sha256sum /etc/resolv.conf /etc/network/interfaces /etc/ssh/sshd_config /etc/pve/storage.cfg /etc/chrony/chrony.conf /etc/chrony/sources.d/sandbox-ip.sources /etc/apt/sources.list.d/*.sources
printf '\n=== Boot configuration ===\n'
test ! -d /sys/firmware/efi && echo BIOS || echo UEFI
cat /etc/default/grub
ls -lh /boot/vmlinuz* /boot/initrd*
dpkg-query -W grub-pc grub-pc-bin proxmox-ve pve-manager
printf '\n=== Refresh repositories ===\n'
apt-get -o APT::Update::Error-Mode=any -o Acquire::Retries=1 update
printf '\n=== Upgrade simulation ===\n'
apt-get -s dist-upgrade
