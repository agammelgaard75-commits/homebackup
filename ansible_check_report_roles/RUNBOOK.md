# Runbook

## Normal check

```bash
scripts/run_check_report_quiet.sh -i inventory.ini
```

## First baseline run

Only run this when explicitly requested:

```bash
scripts/run_check_report_quiet.sh -i inventory.ini --baseline
```

## One host only

```bash
scripts/run_check_report_quiet.sh -i inventory.ini --limit <host>
```

## Logs

The wrapper writes local logs under:

```text
run_logs/check_report/<timestamp>/
```

Do not print those logs unless explicitly requested.

