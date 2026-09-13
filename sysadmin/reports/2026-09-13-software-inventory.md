ITIL corrective change
Change ID: SOFTWARE-INVENTORY-20260913
Status: CLOSED
Prepared at: 2026-09-13
Risk: Low for deployment; no package maintenance in this change

Reason
Implement the updated AGENTS.md requirements for installed software/version
inventory, explicit upgrade boundaries, and verification of intended state.

Inspection and findings
Installed controller 1.0.2 has APT-only availability inspection. It lacks inventory
of extra software, a major-version gate, and installed-version verification.
Staged inventory found 637 installed APT packages and 108 extra entries, with no
inspection errors. Configured Splunk manifest: 9.3.14; dpkg: 9.0.9+6315942c563f.
LiteLLM metadata: 1.83.2. Archived Splunk installation is separately identified.
Unknown locations remain explicitly unclassified rather than assigned versions.

Implementation plan
Back up and atomically deploy controller 1.1.0, README and the two owned Splunk
dashboard files under the lifecycle lock. Preserve existing configuration,
schedules, change records and package state. Update the existing dashboard views
through the local Splunk API without a restart. Run the installed inspect command.
Record decisions, commands, hashes, results and verification in audit.jsonl.
Non-APT upgrades are not implemented by this inventory extension; they require
a defined, reviewed product-specific procedure. Major/unclassified transactions
are refused as a whole; no persistent holds or package removals are introduced.

Validation plan
Run the 52-test suite and full scripts/validate.sh, including isolated dry runs.
Check live installed controller version and compare artifacts to staged files.
Verify live inventory includes Splunk and LiteLLM and records the version conflict.
Verify indexed software events, anomaly finding and all dashboard queries via
local Splunk API. Compare historical change/plan/pointer and dpkg state hashes.

Backout plan
Under controller.lock, restore backed-up controller, README and dashboard files
with their recorded ownership/modes. Restore saved eai:data through the existing
local Splunk API. Preserve logs and all historical change records. No reboot.

Closure
Closed at: 2026-09-13T18:21:28+00:00
Successful: controller 1.1.0 and both existing dashboards deployed and verified. All 52 regression tests and full validation passed. 637 APT packages and 108 extra entries inventoried; all extra events indexed and dashboard queries returned data. Existing change records, plans, pointer, configuration, schedules and dpkg state preserved. No package maintenance or reboot performed. Attention remains: Splunk manifest/package version mismatch and unclassified software locations; non-APT updates require a reviewed procedure. Host inspection reported no errors or failed units.
