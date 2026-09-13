# Execution Agent Runbook

## Step 1: Prepare Evidence Directory

```bash
mkdir -p evidence
```

## Step 2: Host Information

```bash
{
  echo "=== hostname ==="
  hostname
  echo
  echo "=== hostnamectl ==="
  hostnamectl 2>/dev/null || true
  echo
  echo "=== date ==="
  date -Is
} > evidence/00_host_info.txt
```

## Step 3: OS and Kernel

```bash
{
  echo "=== uname ==="
  uname -a
  echo
  echo "=== os-release ==="
  cat /etc/os-release 2>/dev/null || true
  echo
  echo "=== kernel command line ==="
  cat /proc/cmdline 2>/dev/null || true
} > evidence/01_os_kernel.txt
```

## Step 4: Listening Ports

```bash
{
  echo "=== ss listening ports ==="
  ss -tulpn 2>/dev/null || true
} > evidence/02_listening_ports.txt
```

## Step 5: Running Services

```bash
{
  echo "=== running systemd services ==="
  systemctl list-units --type=service --state=running --no-pager 2>/dev/null || true
} > evidence/03_running_services.txt
```

## Step 6: Users

```bash
{
  echo "=== passwd ==="
  cat /etc/passwd 2>/dev/null || true
  echo
  echo "=== lastlog ==="
  lastlog 2>/dev/null || true
} > evidence/04_users.txt
```

## Step 7: Sudo

```bash
{
  echo "=== sudo -l ==="
  sudo -n -l 2>&1 || echo "sudo check skipped or requires password"
  echo
  echo "=== sudoers files ==="
  ls -la /etc/sudoers /etc/sudoers.d 2>/dev/null || true
} > evidence/05_sudo.txt
```

## Step 8: SSH Configuration

```bash
{
  echo "=== sshd_config effective non-comment lines ==="
  grep -Ev '^\s*#|^\s*$' /etc/ssh/sshd_config 2>/dev/null || echo "sshd_config not readable or missing"
  echo
  echo "=== ssh service status ==="
  systemctl status ssh --no-pager 2>/dev/null || systemctl status sshd --no-pager 2>/dev/null || true
} > evidence/06_ssh_config.txt
```

## Step 9: Firewall

```bash
{
  echo "=== ufw ==="
  ufw status verbose 2>/dev/null || true
  echo
  echo "=== nft ==="
  nft list ruleset 2>/dev/null || true
  echo
  echo "=== iptables ==="
  iptables -L -n -v 2>/dev/null || true
} > evidence/07_firewall.txt
```

## Step 10: Packages

```bash
{
  echo "=== apt packages ==="
  dpkg -l 2>/dev/null || true
  echo
  echo "=== rpm packages ==="
  rpm -qa 2>/dev/null || true
} > evidence/08_packages.txt
```

## Step 11: Docker

```bash
{
  echo "=== docker version ==="
  docker version 2>/dev/null || true
  echo
  echo "=== docker ps ==="
  docker ps 2>/dev/null || true
  echo
  echo "=== docker images ==="
  docker images 2>/dev/null || true
  echo
  echo "=== docker networks ==="
  docker network ls 2>/dev/null || true
} > evidence/09_docker.txt
```

## Step 12: Cron

```bash
{
  echo "=== user crontab ==="
  crontab -l 2>/dev/null || true
  echo
  echo "=== system cron ==="
  ls -la /etc/cron* 2>/dev/null || true
} > evidence/10_cron.txt
```

## Step 13: World-Writable Objects

```bash
{
  echo "=== world-writable directories ==="
  find / -xdev -type d -perm -0002 2>/dev/null || true
  echo
  echo "=== world-writable files ==="
  find / -xdev -type f -perm -0002 2>/dev/null || true
} > evidence/11_world_writable.txt
```

## Step 14: SUID Files

```bash
{
  echo "=== suid files ==="
  find / -xdev -perm -4000 -type f 2>/dev/null || true
} > evidence/12_suid.txt
```

## Step 15: Lynis

```bash
{
  if command -v lynis >/dev/null 2>&1; then
    lynis audit system --quick --no-colors 2>&1 || true
  else
    echo "lynis not installed"
  fi
} > evidence/13_lynis.txt
```

## Step 16: Nmap Localhost Only

```bash
{
  if command -v nmap >/dev/null 2>&1; then
    nmap -sV -O -T3 localhost 2>&1 || true
  else
    echo "nmap not installed"
  fi
} > evidence/14_nmap_localhost.txt
```

## Step 17: Nikto Localhost Only

Only run if local port 80 or 443 is listening.

```bash
{
  if ! command -v nikto >/dev/null 2>&1; then
    echo "nikto not installed"
  elif ss -tln 2>/dev/null | grep -Eq ':(80|443)\s'; then
    nikto -host http://localhost 2>&1 || true
  else
    echo "No local HTTP/HTTPS listener detected. Nikto skipped."
  fi
} > evidence/15_nikto_localhost.txt
```

## Step 18: Rkhunter

```bash
{
  if command -v rkhunter >/dev/null 2>&1; then
    rkhunter --check --sk --nocolors 2>&1 || true
  else
    echo "rkhunter not installed"
  fi
} > evidence/16_rkhunter.txt
```

## Step 19: Chkrootkit

```bash
{
  if command -v chkrootkit >/dev/null 2>&1; then
    chkrootkit 2>&1 || true
  else
    echo "chkrootkit not installed"
  fi
} > evidence/17_chkrootkit.txt
```

## Step 20: Needrestart

```bash
{
  if command -v needrestart >/dev/null 2>&1; then
    needrestart -b 2>&1 || true
  else
    echo "needrestart not installed"
  fi
} > evidence/18_needrestart.txt
```

## Step 21: Debsecan

```bash
{
  if command -v debsecan >/dev/null 2>&1; then
    debsecan 2>&1 || true
  else
    echo "debsecan not installed or not applicable"
  fi
} > evidence/19_debsecan.txt
```

## Step 22: OpenSCAP

```bash
{
  if command -v oscap >/dev/null 2>&1; then
    oscap --version 2>&1 || true
    echo
    echo "OpenSCAP installed. Full profile scan skipped unless profile/content is available."
  else
    echo "oscap not installed"
  fi
} > evidence/20_openscap.txt
```

## Step 23: Generate Report

Create `assessment-report.md` with:

```text
# Vulnerability Assessment Report

## Executive Summary

## Scope

## Tools Used

## Host Summary

## Findings Summary

| ID | Severity | Title | Evidence |
|---|---|---|---|

## Detailed Findings

## Evidence Files

## Limitations

## Recommended Next Steps
```

## Step 24: Update TASK.md

Mark completed checklist items.

## Step 25: Stop

Do not remediate findings.

Do not run additional scans outside localhost.

Do not ask for permission.

