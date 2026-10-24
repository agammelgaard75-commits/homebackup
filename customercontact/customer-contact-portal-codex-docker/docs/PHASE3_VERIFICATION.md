# Phase 3 verification — 23–24 October 2026

## Implemented functionality

The contacts app now owns Contact and ContactPoint models, validation, forms, scoped URLs/views, templates, service functions, read-only admin registration and tests. Contacts belong to an existing customer and include name, optional job title/department/type/notes, active status and timestamps. The requested types are Technical, Management, Billing, Support and Other. A contact can be created with only a name.

People can have multiple labeled emails and phones with at most one active primary of each kind. General customer details use the same model with no person assigned. Selecting a primary replaces the previous one transactionally. Customer Contacts pages support name/email/phone search, active/archive filters and pagination; customer Overview includes general details. People and details can be edited, archived and restored without deleting records. Contact archive retains its details and primary flags; individual detail archive clears its primary flag, so restoration does not silently replace another primary.

Viewer has read access; Editor and Administrator have explicit add/change permissions. All URLs, forms and service writes enforce permissions and customer/person/detail ownership. There are no services-module features or new JavaScript/dependencies.

Key files: `apps/contacts/models.py`, `validation.py`, `permissions.py`, `services.py`, `selectors.py`, `forms.py`, `views.py`, `urls.py`, `admin.py`, `templates/contacts/`, `tests.py`; integration changes are limited to account grants, customer overview, navigation/layout and root URL inclusion.

## Database changes

- `contacts/0001_initial.py`: adds Contact and ContactPoint, protected foreign keys to existing customers, timestamps, search indexes, required-name/value and choice constraints, and separate conditional unique constraints for person/general primary details.
- `contacts/0002_contact_point_customer_integrity.py`: adds a composite foreign key from a detail's `(contact_id, customer_id)` to Contact's unique `(id, customer_id)`. This prevents mismatched relationships even if application validation is bypassed. The narrow PostgreSQL DDL migration is necessary because Django check constraints cannot join related rows; application CRUD remains Django ORM.
- Both migrations were generated/maintained in source and applied explicitly in Docker after a backup. No existing customer/account schema or records were rewritten. Group permission reconciliation retains memberships and credentials.

## Actual checks and results

All Django/database execution used Docker and PostgreSQL in the existing isolated `portal-phase1-review` project. The proxy remains bound to loopback; no production deployment or configuration changes occurred.

| Command/check | Actual result |
|---|---|
| Docker `manage.py makemigrations contacts` | Initial migration generated successfully; the additive composite-FK migration was added explicitly. |
| `sudo docker compose build app` | Passed; static collection still works without database access. |
| `sudo ./scripts/test.sh` | **92 tests passed**: all 50 existing tests plus 42 new contact tests. Final full run: 28.813 seconds. |
| `manage.py check` | No issues. |
| `manage.py check --deploy --fail-level WARNING` | Passed; only the two pre-existing documented internal-HSTS checks remain silenced. |
| `manage.py makemigrations --check --dry-run` | No changes detected. |
| `sudo ./scripts/update.sh` | Backed up before migrations; applied both contact migrations, initialized grants and returned all three services healthy. |
| `manage.py showmigrations contacts` | Both migrations marked `[X]`. |
| `sudo docker compose config --quiet` | Passed. |
| `./scripts/tests/operations.sh` | Existing maintenance-script failure checks passed. |
| Real HTTPS customer/contact workflows | Editor and Administrator each created/edited a synthetic customer, created two contacts, added multiple emails/phones, changed primaries, searched by name/email/normalized phone, archived/restored people/details, and added general email/phone information. All passed through Caddy with certificate verification enabled. |
| Real HTTPS authorization | Viewer could read; direct create/edit/archive/restore requests were refused with 403. Missing CSRF was rejected. A cross-customer contact URL returned 404. |
| `sudo docker compose up -d --force-recreate --wait` | All three containers recreated without removing volumes and became healthy. |
| Post-recreation data/session verification | Complete synthetic customer/contact/detail digests were unchanged. A previously saved authenticated session still accessed contact details over trusted HTTPS. `/health/` returned 200. |
| Existing-data verification | Digests of every pre-existing customer row and account identity/password/flags/group-membership data matched the pre-change snapshots. |
| Configuration verification | `.env`, Compose, Dockerfile, Caddyfile and requirements checksums were unchanged. |

The tests cover name-only contacts, all requested types, optional metadata, maximum lengths, multiple contact points, Danish/international phone formats, email normalization, invalid values, primary switching, direct database constraint violations, mismatched owners, immutable ownership, protected relationships, transaction rollback, archive/restore preservation, customer scoping, pagination, form validation, escaping, CSRF, direct URL permissions and read-only admin protection. A PostgreSQL concurrency test used separate connections to select two primaries simultaneously; both writes succeeded serially and exactly one primary remained.

The first full run had one test expectation error: POST to a read-only detail URL correctly returned 405 before record lookup, while its GET returned 404 for the wrong customer. The assertion was corrected and all 92 tests then passed. No application failure remains unresolved.

## Final state and review limitations

The review stack is running with three healthy containers. Open a customer at `https://portal.phase1.localhost/customers/` and choose **Contacts**. Existing credentials remain valid.

After verification, the two synthetic customers and four synthetic people were archived, their general details archived, and the three newly created test accounts disabled. No pre-existing records were changed or deleted, and no persistent volume was deleted. Session-cookie test files were removed. Only synthetic information was used for verification; no contact data was sent to external services.

Graphical browser/mobile visual inspection was not performed; pages and workflows were checked programmatically over HTTPS. Phone extensions are not supported, and normalization does not infer country codes. These behaviors are documented in the UI/data model. No functional blocker remains. **Phase 3 is ready for review.**

Suggested next phase after review: Phase 4 — Service catalog and assignments. No Phase 4 implementation has begun.
