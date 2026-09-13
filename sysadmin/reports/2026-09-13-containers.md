ITIL corrective change
Change ID: CONTAINERS-20260913
Status: CLOSED
Prepared at: 2026-09-13
Risk: Low for framework deployment; application restarts only in future approved plans

Reason
Add regular container image maintenance to the existing weekly lifecycle.

Inspection
n8n is a single Compose service, project n8n, file /home/bot/n8n/docker-compose.yml.
Current image application version is 2.29.7, with DHI Node.js 24.16.0.
The container has one persistent named volume and two writable bind mounts.
The readiness endpoint http://127.0.0.1:5678/healthz/readiness returns HTTP 200.
The source Compose fingerprint matches the running container. Available latest
image reports n8n 2.38.7 and Node.js 26.7.0; the Node major change is deferred by
AGENTS.md policy. No application update is included in this deployment.

Implementation
Deploy controller 1.2.0 and container adapter with backups and checksum verification.
Enable the reviewed n8n container policy in existing production TOML, preserving
other configuration. Keep weekly schedule and all historical maintenance records.
Install scoped read-only Compose-directory access in lifecycle service drop-ins;
keep Docker CLI state under /var/lib/ai-sysadmin. Reload systemd definitions.
Update existing Splunk health/anomaly views to show container images and deferrals.
Run registry/inventory preview within matching service sandbox, without pulling,
stopping or replacing n8n. Record outputs, decisions and verification in audit log.

Future maintenance behavior
Preparation records immutable platform-specific digest candidates before AI review.
Holds, unknown versions, application/dependency major changes, downgrades, drift,
shared writable data and missing health checks prevent automatic image replacement.
Maintenance pulls/validates the exact prepared image; stops only the target service,
creates bounded private data archives and verifies them before replacing the service.
It verifies image ID, labels, mounts and stable readiness before recording success.
Backup failure resumes the old service; replacement failure preserves backups for
operator recovery, without a potentially unsafe automatic database downgrade.
No compose down, volume removal, image pruning, network edits or host reboot.

Validation
72 tests and scripts/validate.sh pass. Live staged preview verifies current
configuration and correctly defers Node.js 24 -> 26. Verify deployed artifacts,
effective unit sandbox, full container preview and Splunk inventory/anomaly queries.
Verify n8n identity/image/start time, readiness and historical change hashes remain
unchanged. No application upgrade is claimed or required for this deployment.

Backout
Under controller.lock, restore backed-up controller, README, config and dashboards.
Remove only newly introduced container drop-ins/module if restoring the old release,
then reload unit definitions. Restore backed-up live Splunk eai:data through local
API. Preserve all audit logs and historical change records. No reboot required.

Closure
Closed at: 2026-09-13T18:45:43+00:00
Successful: container maintenance enabled for n8n on existing weekly timers; controller 1.2.0, adapter, scoped service sandbox and Splunk dashboards deployed and verified. 72 tests and full validation passed. Service-sandbox registry preview and live Splunk queries passed. n8n image, identity, startup time, data mounts and readiness unchanged; no image pull, application restart, package update or reboot performed by this deployment. Existing history and schedule preserved. Current candidate n8n 2.38.7 is deferred because bundled Node.js changes major version 24 to 26. That major transition requires explicit operator approval under AGENTS.md.
