#!/usr/bin/env bash
set -Eeuo pipefail

# Quiet wrapper for check_report.yml.
# Captures noisy Ansible stdout/stderr to local log files and prints only:
#   OK
# or:
#   FAIL reason=... log_dir=...

usage() {
  cat <<'USAGE'
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
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd "${script_dir}/.." && pwd)"

inventory=""
playbook="${project_dir}/check_report.yml"
limit=""
log_dir=""
summary_check=true
extra_vars=()
pass_through=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -i|--inventory)
      inventory="${2:-}"
      shift 2
      ;;
    -p|--playbook)
      playbook="${2:-}"
      shift 2
      ;;
    -l|--limit)
      limit="${2:-}"
      shift 2
      ;;
    -e|--extra-vars)
      extra_vars+=("${2:-}")
      shift 2
      ;;
    --baseline)
      extra_vars+=("drift_detection_create_baseline=true")
      shift
      ;;
    --log-dir)
      log_dir="${2:-}"
      shift 2
      ;;
    --no-summary-check)
      summary_check=false
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      pass_through+=("$@")
      break
      ;;
    *)
      echo "FAIL reason=unknown_argument arg=$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$inventory" ]]; then
  echo "FAIL reason=missing_inventory" >&2
  usage >&2
  exit 2
fi

if [[ ! -f "$inventory" ]]; then
  echo "FAIL reason=inventory_not_found path=$inventory" >&2
  exit 2
fi

if [[ ! -f "$playbook" ]]; then
  echo "FAIL reason=playbook_not_found path=$playbook" >&2
  exit 2
fi

if ! command -v ansible-playbook >/dev/null 2>&1; then
  echo "FAIL reason=ansible_playbook_not_found" >&2
  exit 127
fi

if [[ -z "$log_dir" ]]; then
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  log_dir="${project_dir}/run_logs/check_report/${timestamp}"
fi
mkdir -p "$log_dir"

stdout_log="${log_dir}/ansible_stdout.log"
stderr_log="${log_dir}/ansible_stderr.log"
status_json="${log_dir}/wrapper_status.json"

cmd=(ansible-playbook -i "$inventory" "$playbook")
if [[ -n "$limit" ]]; then
  cmd+=(--limit "$limit")
fi
for ev in "${extra_vars[@]}"; do
  cmd+=(-e "$ev")
done
cmd+=("${pass_through[@]}")

printf '%q ' "${cmd[@]}" > "${log_dir}/command.txt"
printf '\n' >> "${log_dir}/command.txt"

set +e
ANSIBLE_FORCE_COLOR=false \
ANSIBLE_DISPLAY_SKIPPED_HOSTS=false \
ANSIBLE_DISPLAY_OK_HOSTS=false \
"${cmd[@]}" >"$stdout_log" 2>"$stderr_log"
exit_code=$?
set -e

# Default to ansible exit code. Then, unless disabled, also inspect the captured
# compact summary line so a report-level failure becomes a wrapper failure.
result="fail"
reason="ansible_exit_${exit_code}"

if [[ $exit_code -eq 0 ]]; then
  if [[ "$summary_check" == "true" ]]; then
    if grep -Eq 'check_report: ok=(True|true)' "$stdout_log"; then
      result="ok"
      reason="ok"
    elif grep -Eq 'check_report: ok=(False|false)' "$stdout_log"; then
      result="fail"
      reason="check_report_not_ok"
    elif grep -Eq 'unreachable=0[[:space:]]+failed=0' "$stdout_log"; then
      # Fallback: Ansible succeeded and the PLAY RECAP has no unreachable or failed hosts.
      # This handles runs where the final debug summary is suppressed or skipped by
      # display settings, tags, callbacks, or other Ansible weirdness. Computers, eh.
      result="ok"
      reason="ok_recap_fallback"
    else
      result="fail"
      reason="summary_not_found"
    fi
  else
    result="ok"
    reason="ok"
  fi
fi

cat > "$status_json" <<JSON
{
  "result": "$result",
  "reason": "$reason",
  "ansible_exit_code": $exit_code,
  "log_dir": "$log_dir",
  "stdout_log": "$stdout_log",
  "stderr_log": "$stderr_log"
}
JSON

if [[ "$result" == "ok" ]]; then
  echo "OK"
  exit 0
fi

echo "FAIL reason=${reason} log_dir=${log_dir}"
exit 1

