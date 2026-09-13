# Installer Runbook

## Step 1: Check Current Directory

```bash
pwd
ls -la
ls -la toolscripts
```

## Step 2: Check Install Scripts

```bash
for f in \
  toolscripts/install_lynis.sh \
  toolscripts/install_nmap.sh \
  toolscripts/install_nikto.sh \
  toolscripts/install_debsecan.sh \
  toolscripts/install_needrestart.sh \
  toolscripts/install_rkhunter.sh \
  toolscripts/install_chkrootkit.sh \
  toolscripts/install_openscap.sh \
  toolscripts/install_jq.sh \
  toolscripts/install_curl.sh \
  toolscripts/install_all_tools.sh
do
  echo "=== $f ==="
  test -f "$f" && echo "exists" || echo "missing"
done
```

## Step 3: Make Scripts Executable

```bash
chmod +x toolscripts/*.sh
```

## Step 4: Run Installer

```bash
toolscripts/install_all_tools.sh
```

## Step 5: Verify Tools

```bash
command -v lynis || true
command -v nmap || true
command -v nikto || true
command -v debsecan || true
command -v needrestart || true
command -v rkhunter || true
command -v chkrootkit || true
command -v oscap || true
command -v jq || true
command -v curl || true
```

## Step 6: Version Checks

```bash
lynis --version 2>/dev/null || true
nmap --version 2>/dev/null | head -5 || true
nikto -Version 2>/dev/null || true
debsecan --version 2>/dev/null || true
needrestart -v 2>/dev/null || true
rkhunter --versioncheck 2>/dev/null || true
chkrootkit -V 2>/dev/null || true
oscap --version 2>/dev/null || true
jq --version 2>/dev/null || true
curl --version 2>/dev/null | head -2 || true
```

## Step 7: Write Install Report

Create:

```text
install-report.md
```

Include:

* timestamp
* hostname
* OS
* install result per tool
* verification result per tool
* failed tools
* skipped tools
* next recommended agent

## Step 8: Update TASK.md

Mark completed success criteria.

If a tool failed or was skipped, leave its checkbox unchecked and document the reason in `install-report.md`.

## Step 9: Stop

Stop after installation verification.

Do not run any vulnerability scans.

