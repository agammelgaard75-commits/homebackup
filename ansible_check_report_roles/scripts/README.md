Usage:
  scripts/run_check_report_quiet.sh -i inventory.ini [options]

Options:
  -i, --inventory PATH       Inventory file. Required.
  -p, --playbook PATH        Playbook path. Default: check_report.yml
  -l, --limit LIMIT          Ansible host/group limit.
  -e, --extra-vars VARS      Extra vars passed to ansible-playbook. Can be repeated.
      --baseline             Shortcut for -e drift_detection_create_baseline=true
      --log-dir DIR          Local wrapper log directory. Default: ./run_logs/check_report/<timestamp>
      --no-summary-check     Only require ansible-playbook exit code 0. Do not inspect captured summary.
  -h, --help                 Show help.
  --                         Everything after this is passed directly to ansible-playbook.
    
Examples:
  scripts/run_check_report_quiet.sh -i inventory.ini
  scripts/run_check_report_quiet.sh -i inventory.ini --baseline
  scripts/run_check_report_quiet.sh -i inventory.ini -l web01 -e 'service_healthcheck_services=["ssh"]'
