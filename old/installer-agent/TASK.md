# Current Task: Install Vulnerability Assessment Tools

## Agent Role

Agent 2: Installer

## Goal

Install and verify the vulnerability assessment tools prepared by Agent 1.

## Scope

This agent only installs tools.

This agent does not run vulnerability scans.

This agent does not analyze findings.

This agent does not remediate vulnerabilities.

## Required Input Directory

```text
toolscripts/
```

## Required Install Scripts

```text
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

## Required Output

```text
install-report.md
```

## Success Criteria

* [ ] toolscripts directory found
* [ ] all required install scripts found
* [ ] scripts made executable
* [ ] install_all_tools.sh executed
* [ ] lynis verified
* [ ] nmap verified
* [ ] nikto verified
* [ ] debsecan verified or skipped with reason
* [ ] needrestart verified or skipped with reason
* [ ] rkhunter verified
* [ ] chkrootkit verified
* [ ] openscap/oscap verified or skipped with reason
* [ ] jq verified
* [ ] curl verified
* [ ] install-report.md created
* [ ] final summary produced

## Do Not Do

* Do not run scans
* Do not run lynis audit
* Do not run nmap scan
* Do not run nikto scan
* Do not run rkhunter check
* Do not run chkrootkit scan
* Do not change firewall
* Do not modify SSH config
* Do not remediate vulnerabilities
* Do not ask for confirmation

