# Current Task: Execute Local Vulnerability Assessment

## Agent Role

Agent 3: Execution Agent

## Goal

Run installed vulnerability assessment tools against localhost, collect evidence, and generate `assessment-report.md`.

## Scope

Target:

```text
localhost
```

This agent performs read-only local vulnerability assessment.

## Required Inputs

```text
assessment-tools-plan.md
install-report.md
RUNBOOK.md
```

## Required Output Directory

```text
evidence/
```

## Required Output Report

```text
assessment-report.md
```

## Success Criteria

* [ ] evidence directory created
* [ ] host information collected
* [ ] OS and kernel information collected
* [ ] listening ports collected
* [ ] running services collected
* [ ] users reviewed
* [ ] sudo permissions reviewed or skipped with reason
* [ ] SSH configuration reviewed
* [ ] firewall status reviewed
* [ ] package inventory collected
* [ ] Docker status reviewed or skipped with reason
* [ ] cron reviewed
* [ ] world-writable files/directories reviewed
* [ ] SUID files reviewed
* [ ] lynis executed or skipped with reason
* [ ] nmap localhost scan executed or skipped with reason
* [ ] nikto localhost check executed only if local web service exists
* [ ] rkhunter executed or skipped with reason
* [ ] chkrootkit executed or skipped with reason
* [ ] needrestart executed or skipped with reason
* [ ] debsecan executed or skipped with reason
* [ ] openscap executed or skipped with reason
* [ ] findings generated
* [ ] assessment-report.md created
* [ ] final summary produced

## Do Not Do

* Do not scan external systems
* Do not scan the LAN
* Do not exploit vulnerabilities
* Do not brute force
* Do not modify services
* Do not modify firewall
* Do not modify SSH
* Do not install packages
* Do not remediate findings
* Do not delete files
* Do not ask for confirmation

## Completion State

Not started.

