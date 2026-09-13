# Task

Run the Ubuntu check/report playbook through the quiet wrapper.

## Command

```bash
scripts/run_check_report_quiet.sh -i inventory.ini
```

## Expected response

Success:

```text
OK
```

Failure:

```text
FAIL reason=<reason> log_dir=<path>
```

Do not include anything else.

