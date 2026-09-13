# Ubuntu Ansible Check/Report Roles

This bundle contains read-only sysadmin reporting roles for Ubuntu servers.

The roles now keep Ansible stdout compact and write the useful details to files on the target host. This makes the playbook much friendlier for LLM/agent runs, because apparently dumping every socket, journal line, and package diff into a model context is how we summon billing demons.

## Roles

- `asset_inventory` - OS, hardware, network, package count
- `disk_watch` - filesystem usage, inode usage, large files
- `failed_units_check` - failed systemd services
- `journal_error_scan` - recent critical/error journal entries
- `port_inventory` - listening TCP/UDP sockets
- `service_healthcheck` - configured services and ports
- `vulnerability_scan` - apt upgrades, optional Ubuntu security status, optional Trivy
- `drift_detection` - compare packages and selected config checksums against a baseline

## Run

```bash
ansible-playbook -i inventory.ini check_report.yml
```

## Report files

Default report directory on each target host:

```text
/var/log/ansible-reports/
```

Default files:

```text
/var/log/ansible-reports/asset_inventory.json
/var/log/ansible-reports/disk_watch.json
/var/log/ansible-reports/failed_units_check.json
/var/log/ansible-reports/journal_error_scan.json
/var/log/ansible-reports/port_inventory.json
/var/log/ansible-reports/service_healthcheck.json
/var/log/ansible-reports/vulnerability_scan.json
/var/log/ansible-reports/drift_detection.json
/var/log/ansible-reports/check_report_summary.json
```

The playbook stdout only prints compact status lines like:

```text
vulnerability_scan: ok=False; report=/var/log/ansible-reports/vulnerability_scan.json
check_report: ok=False; summary=/var/log/ansible-reports/check_report_summary.json
```

## Drift baseline

First run a controlled baseline:

```bash
ansible-playbook -i inventory.ini check_report.yml -e drift_detection_create_baseline=true
```

Baseline files are still stored here:

```text
/var/lib/ansible-drift/packages.txt
/var/lib/ansible-drift/checksums.txt
```

Later runs compare against that baseline and write the diff result to:

```text
/var/log/ansible-reports/drift_detection.json
```

## Timeouts

Some checks have timeout variables so a scan does not cosplay as a permanent resident:

```yaml
journal_error_scan_timeout_seconds: 30
port_inventory_timeout_seconds: 15
disk_watch_find_timeout_seconds: 60
drift_detection_package_timeout_seconds: 60
drift_detection_checksum_timeout_seconds: 120
vulnerability_scan_apt_timeout_seconds: 120
vulnerability_scan_trivy_timeout_seconds: 300
```

Tune these in `group_vars/ubuntu_servers.yml` if your server is slow, cursed, or both.

# Goose Minimal Markdown Files

Copy these files into the root of the Ansible project.

Recommended files:

```text
AGENTS.md
TASK.md
RUNBOOK.md
VERIFY.md
```

Then ask Goose to execute `TASK.md`.

