# Unified contact data correction: verification

Verified on 2026-10-24 in the isolated Docker review project `portal-phase1-review`, bound to loopback at `https://portal.phase1.localhost/`. The verified Phase 5B source was committed as `9866904` before this correction. No production configuration, host application or persistent volume was replaced.

## Cause and correction

The old `ContactPoint.contact_id` accepted NULL, allowing customer-level email/phone rows without a Contact. Customer Overview and the customer Contacts tab rendered those rows in a separate General Contact Details section, while global Contacts listed only Contact records. Phase 5B service search had an additional branch for null-contact points, so its table and email export could disagree with the global directory.

The Contacts app now owns all named and general contacts. `Contact.is_general` identifies team/shared entries such as Support Desk or Reception; they use the same customer associations, pages, notes and multiple email/phone details as named people. The customer Overview previews associated contacts; the Contacts tab lists them; the global page edits the same records. New `ContactPoint` rows require a Contact. Old general-detail GET URLs redirect to the corresponding contact actions; POST to those legacy routes no longer writes data. Global and service search use contact-linked points only, including general contacts, and email export still deduplicates across all matched pages.

## Data migration and preservation

`contacts.0004_unify_general_contact_points` adds `is_general` and attaches each legacy null-contact point to one general Contact associated with its customer. It can reuse a single empty, unshared `General Contact` placeholder when unambiguous. `contacts.0005_require_contact_for_details` then removes the obsolete general-primary constraint and makes `ContactPoint.contact_id` non-null. The data and schema changes use separate transactions so PostgreSQL foreign-key triggers complete before the table alteration. The data migration is intentionally irreversible in place; use the pre-update backup and matching prior code revision for rollback.

Before migration, the isolated database had **10 null-contact points across 6 customers**, all archived. Immediately afterward it had **27 original points, 0 null-contact points, 6 associated general contacts and 0 mismatched point/customer owners**. All 10 points retained their IDs, values, normalized values, labels, primary and active flags, creation/updated timestamps and original customer IDs. Digests of all pre-existing customers, contacts, associations, attached points, catalog services, assignments, audit events, users and group memberships matched after migration and after full container recreation. No record was unable to migrate automatically. Historical audit entries were retained; the migration did not invent a staff actor or event.

## Commands and observed results

| Check | Observed result |
|---|---|
| `sudo docker compose build app` | Passed, including static collection. |
| `sudo ./scripts/test.sh` | **191 tests passed in 56.584 seconds.** Django checks passed; deploy checks passed with the two previously documented internal-HSTS silences; `makemigrations --check --dry-run` reported no changes. |
| `sudo ./scripts/update.sh` | Backed up first, applied `contacts.0004` and `contacts.0005`, reconciled roles and returned app, database and proxy healthy. |
| `sudo docker compose config --quiet` | Passed. |
| `sudo bash scripts/tests/operations.sh` | Backup, restore, update and installer failure-path harness passed. |
| Post-migration `sudo ./scripts/backup.sh` | Wrote a custom PostgreSQL archive. `pg_restore --list` contained Contact, ContactCustomer and ContactPoint table data; `pg_restore --file=/dev/null` read the complete archive successfully. |
| Authenticated HTTPS workflow through Caddy | Editor created Support Desk under a customer, edited it via global Contacts, linked a second customer and added two emails/two phones. Viewer, Editor and Administrator saw the same contact under both customers and in service search; email export returned two unique addresses. Viewer direct writes returned 403. |
| `sudo docker compose up -d --force-recreate --wait` | All three services became healthy without deleting volumes. Synthetic contact, associations, points and audit digests matched; an authenticated Editor session still worked. HTTPS `/health/` returned `{"status":"ok"}`. |
| Configuration and source checks | `.env`, Compose, Dockerfile, Caddyfile, requirements and Django settings hashes were unchanged; `git diff --check` passed. |

The first update attempt encountered PostgreSQL's pending foreign-key trigger restriction when the data move and non-null alteration were in one migration transaction. That transaction rolled back and the update script left the app stopped as designed. Splitting it into `0004` and `0005` fixed the issue; the rerun and final tests passed. The initial 188-test development run exposed fixtures that intentionally used the old null-contact path; they were updated to test the unified model. The final 191-test suite includes an end-to-end customer/global/service-search workflow, missing-contact database and service rejection, archived contact behavior, relationship/role checks and the earlier phases.

After the HTTPS rehearsal, synthetic contacts, services and customers were archived, assignments terminated and test accounts disabled. No business rows or named volumes were deleted. The post-migration backup archive was fully read, but a destructive restore was not performed on the populated review stack. Browser visual layout and clipboard interaction were not manually inspected; the authenticated export endpoint and script delivery remain covered by application checks.

For manual review, start the existing isolated stack with `sudo docker compose up -d --wait` and open `https://portal.phase1.localhost/` with its CA trusted. Under a disposable customer, add **Support Desk**, select **General contact**, then add two emails and two phones from its detail page. Confirm it appears in global **Contacts**, edit its name there and check the customer Contacts tab and Overview. Link a second disposable customer, search by an assigned service, use **Copy All Emails**, and archive the test records afterward.

**The contact-unification correction is ready for review.** No functional blocker or unresolved test failure remains. Phase 6 has not been started.
