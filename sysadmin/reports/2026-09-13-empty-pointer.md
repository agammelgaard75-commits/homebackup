ITIL corrective change: EMPTY-POINTER-20260913
Status: CLOSED

Problem: Manual prepare rejects the zero-byte current-change file before checking
existing change history. Latest live change CHG-20260913-R2 is CLOSED. Both
lifecycle services were inactive, and installed controller matched repository.

Decision: Treat blank pointers as absent, inspect history for interrupted or
invalid records, and recover completed/prepared references without new execution.
Keep malformed nonempty pointers, failed changes, and invalid plans fail-closed.

Implementation: Back up controller, README, and pointer under the state directory;
atomically install controller 1.0.2 and updated README while holding controller.lock.
Run the installed prepare command twice. Record actions/results to audit.jsonl.
Do not execute maintenance, change schedules, or reboot.

Validation: Regression tests cover blank/whitespace, initial preparation, completed
change recovery, repeated calls, malformed references, old interrupted records,
failed changes and missing plans. Run full repository validation. Compare live
record/plan hashes before and after and verify the recovered reference.

Backout: Restore the backed-up controller and README atomically while holding the
controller lock. Keep change history and audit events. The recovered pointer is a
valid reference and need not be removed.

Closed at: 2026-09-13T17:41:16+00:00
Closing remark: Successful. Controller 1.0.2 and README deployed with backups in
/var/lib/ai-sysadmin/empty-pointer-backup-20260913. Both installed prepare calls
returned 0: CHG-20260913-R2 is CLOSED; no further action needed. Pointer restored
to CHG-20260913-R2. All live change-record and plan hashes remained unchanged.
All 38 tests and full scripts/validate.sh passed. No package maintenance, service
restart, schedule change, or reboot performed. No outstanding issue for this fix;
this validation did not perform a new full host-health inspection.

Evidence: reports/empty-pointer-tests.log, reports/empty-pointer-validation.log,
reports/empty-pointer-deployment.log, and /var/log/ai-sysadmin/audit.jsonl
(change_id EMPTY-POINTER-20260913, plus controller recovery/idempotency events).
