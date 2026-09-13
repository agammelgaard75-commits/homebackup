# Current Task: Assessment Tool Planning

## Goal

Create a vulnerability assessment tool plan and one silent install script per tool.

## Agent Role

Agent 1: Planner

## Scope

This agent only prepares tooling.

This agent does not run scans.

This agent does not fix findings.

This agent does not change system configuration except creating files in the current project directory.

## Required Directory

```text
toolscripts/
```

## Required Files

```text
assessment-tools-plan.md
toolscripts/install_lynis.sh
toolscripts/install_nmap.sh
toolscripts/install_nikto.sh
toolscripts/install_debsecan.sh
toolscripts/install_needrestart.sh
toolscripts/install_rkhunter.sh
toolscripts/install_chkrootkit.sh
toolscripts/install_openscap.sh
toolscripts/install_jq.sh
toolscripts/install_curl.sh
toolscripts/install_all_tools.sh
```

## Success Criteria

* [ ] Tool plan created
* [ ] toolscripts directory created
* [ ] One install script created per tool
* [ ] Scripts check whether tool is already installed
* [ ] Scripts install silently if missing
* [ ] Scripts support apt, dnf, and yum where possible
* [ ] Scripts fail safely if unsupported
* [ ] Scripts are executable
* [ ] install_all_tools.sh created
* [ ] install_all_tools.sh runs all tool scripts
* [ ] Final response lists created files

## Do Not Do

* Do not run vulnerability scans
* Do not install tools directly from this agent unless explicitly instructed later
* Do not use offensive tools
* Do not use exploit frameworks
* Do not ask for confirmation

