# Phase 5B verification

Phase 5B was implemented and tested on 2026-10-24 in the existing isolated Docker review project `portal-phase1-review` at `https://portal.phase1.localhost/`. Its proxy binds to loopback; this was not a production deployment. The verified Phase 5 starting point was committed as `b590cce` before editing. Secrets, dumps and runtime evidence were excluded from Git.

## Implemented behavior

- `/search/by-service/` offers one or more catalog services, ANY/ALL matching, inactive-assignment and archived-record filters, sorting and 25-row pagination. A customer with no qualifying contacts still gets a row. Repeated agreements and email/phone detail rows do not duplicate a customer/contact association.
- Copy All Emails collects active contact and general customer email addresses from every matched active customer across every page. It deduplicates without case sensitivity, shows a count, and offers a selectable fallback if browser clipboard access fails.
- `/contacts/` is a global directory with name/email/phone/customer search, status/type filters, pagination and direct create/edit/archive/restore access. Existing customer-scoped URLs and contact details remain available.
- A contact can have multiple customer associations. The original Contact/ContactPoint customer columns remain as provenance and detail ownership. Removing an association archives that link, leaving the person and details intact. Association changes and contact/detail changes are audited transactionally for affected customers using IDs and field names, without copying values.
- The dashboard Active Contacts widget now displays active people and links to the global directory. A shared person is counted once.

## Database upgrade and preservation

`contacts.0003_contact_customers` created the unique, indexed contact/customer association table and backfilled one active association per existing contact. `audit.0002_remove_auditevent_audit_object_type_valid_and_more` expanded the audit object-type check for association events. Neither migration rewrote existing Contact, ContactPoint, Customer, Service, CustomerService, User or AuditEvent rows. Both migrations showed `[X]` after update.

The update script backed up the isolated database before applying these migrations. Immediately after migration, **8 existing contacts had 8 association rows and 0 missing original associations**. Pre-update digests of all existing customer, contact, point, service, assignment, audit and user rows, plus group memberships, matched after migration and after full container recreation. `.env`, Compose, Dockerfile, Caddyfile, requirements and Django settings hashes were unchanged. No named volume was deleted.

## Actual checks

| Check | Observed result |
|---|---|
| `sudo docker compose config --quiet` | Passed. |
| `sudo docker compose build app` | Passed; static collection succeeded. |
| `sudo ./scripts/test.sh` | **188 tests passed in 53.466 seconds**. Django system checks passed, deploy checks passed with the two previously documented internal-HSTS silences, and `makemigrations --check --dry-run` reported no changes. |
| `sudo bash scripts/tests/operations.sh` | Passed backup, restore, update and installer failure-path harness. |
| `sudo ./scripts/update.sh` | Passed backup-first update, applied both Phase 5B migrations, reconciled roles and returned app, DB and proxy healthy. |
| Real post-migration `sudo ./scripts/backup.sh` | Wrote a private custom-format dump. `pg_restore --list` contained both AuditEvent and ContactCustomer table data; `pg_restore --file=/dev/null` read the complete archive successfully. |
| Authenticated HTTPS smoke test | Viewer, Editor and Administrator opened the global Contacts and service-search pages. Shared contact appeared under two customers; a no-contact customer appeared. Email export returned two unique addresses despite differently cased duplicates; dashboard showed the active contact. Viewer contact creation returned 403 and Editor creation page returned 200. |
| `sudo docker compose up -d --force-recreate --wait` | All three services became healthy without removing volumes. Synthetic shared-contact and audit digests matched, and an existing Editor session still worked over verified TLS. `/health/` returned `{"status":"ok"}`. |
| Static asset and source checks | Clipboard JavaScript was served over HTTPS; `git diff --check` passed. |

The automated suite covers single-service, ANY/ALL, active/inactive assignments, no-contact customers, repeated agreements, multiple/shared contacts, association creation/removal and uniqueness, migration backfill, primary and general email details, case-insensitive deduplication across result pages, sorting, archived filters, permissions, dashboard counts, audit attribution/rollback and all previously implemented phases. The first test runs caught a form-to-selector argument mismatch and two incorrect assertions; these were fixed before the 188-test passing run. A first live smoke assertion compared email display case instead of normalized case; the assertion was corrected and the workflow passed. Synthetic data from both attempts was archived or terminated, and synthetic users disabled; no rows were deleted.

## Limits and manual review

No graphical browser clipboard interaction or mobile visual inspection was performed. The authenticated email endpoint, count and HTTPS JavaScript delivery were verified; manually test both clipboard success and fallback in a browser. The post-migration dump was fully read and the restore failure-path harness passed, but no destructive database restore was performed on the populated review stack. A complete restore rehearsal should use a separate disposable stack and the documented matching revision.

For manual review, start the isolated existing stack with `sudo docker compose up -d --wait` and sign in at `https://portal.phase1.localhost/`. Open **Contacts** to create one person linked to two disposable customers, edit its associations, and check that it appears under both customer Contacts tabs. Open **Search by service**, select two services, compare ANY and ALL, include inactive assignments, and use **Copy All Emails** after adding distinct and duplicate test addresses. Check the Active Contacts widget and customer Activity. Archive the test records when done. Avoid real personal data in this review environment.

**Phase 5B is ready for review.** No functional blocker or unresolved test failure remains. Phase 6 has not been started.
