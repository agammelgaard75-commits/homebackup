# Vulnerability Assessment Runbook

## Host Information

```bash
hostnamectl
uname -a
cat /etc/os-release
```

## Package Inventory

Debian/Ubuntu:

```bash
dpkg -l
apt list --installed
```

RHEL:

```bash
rpm -qa
```

## Running Services

```bash
systemctl list-units --type=service --state=running
```

## Listening Ports

```bash
ss -tulpn
```

## User Accounts

```bash
cat /etc/passwd
lastlog
```

## Sudo Permissions

```bash
sudo -l
```

## SUID Binaries

```bash
find / -perm -4000 -type f 2>/dev/null
```

## SSH Configuration

```bash
grep -v '^#' /etc/ssh/sshd_config
```

## Firewall

```bash
ufw status verbose
iptables -L -n -v
nft list ruleset
```

## Docker

```bash
docker ps
docker images
docker network ls
```

## Scheduled Tasks

```bash
crontab -l
ls -la /etc/cron*
```

## World Writable Files

```bash
find / -type f -perm -0002 2>/dev/null
```

## World Writable Directories

```bash
find / -type d -perm -0002 2>/dev/null
```

## Kernel Modules

```bash
lsmod
```

## Mounted Filesystems

```bash
mount
```

## OpenSSL

```bash
openssl version
```

## Recent Security Warnings

```bash
journalctl -p warning -n 100 --no-pager
```

## Nginx

```bash
nginx -t
grep -R "listen" /etc/nginx 2>/dev/null
```

## Docker Exposure

```bash
docker ps
ss -tulpn
```

## Summary

Generate findings after all checks complete.

