# Phase 2 verification — 23 October 2026

## Delivered scope

Customer management in `apps/customers`: UUID model, optional CVR/company identifier (the documented `reference_code`), Active/Archived status, optional address, internal notes, timestamps, model/forms/service validation, additive migration, list/detail/create/edit/archive pages, case-insensitive search, status filtering, sorting and 25-row pagination. Archived records remain readable and can be reactivated. There is no delete route or admin deletion action.

All reads require portal and customer-view permissions. Writes also require portal-edit and the relevant customer model permission, including inside the owning module's service functions. Viewer reads; Editor and Administrator maintain records. Read-only Django admin registration links to the customer UI. Customer navigation and forms follow the existing layout.

No contacts, services, global search or audit features were implemented. Docker architecture, dependency versions, runtime services, ports, volumes, authentication implementation and maintenance scripts were not changed.

## Commands and actual results

All Django and database work ran inside Docker against the existing isolated `portal-phase1-review` project, bound to loopback. Docker commands used `sudo` because this workspace account lacks direct socket access.

| Verification | Result |
|---|---|
| Docker `manage.py makemigrations customers` with the module mounted for development | Generated `customers/0001_initial.py`; migration is stored in source. No startup migration generation. |
| `sudo docker compose build app` | Passed; static collection still works without database access. |
| `sudo ./scripts/test.sh` | **50 tests passed: 20 Phase 1 tests and 30 customer tests.** Final full run took 19.073 seconds. |
| `manage.py check` | No issues. |
| `manage.py check --deploy --fail-level WARNING` | Passed with only the two pre-existing, documented HSTS checks silenced. |
| `manage.py makemigrations --check --dry-run` | No changes detected. |
| `sudo docker compose config --quiet` | Passed; no Docker architecture changes. |
| `./scripts/tests/operations.sh` | Existing maintenance failure-path tests passed. |
| `sudo ./scripts/update.sh` | Created a private backup, applied `customers.0001_initial`, reconciled roles, passed deployment checks, and returned all three services to healthy. |
| `manage.py showmigrations customers` | `[X] 0001_initial`. |
| Real HTTPS workflow through Caddy with its trusted public CA | Editor and Administrator passed invalid-input rejection, create, edit, case-insensitive search, archive, status filtering and reactivation. Viewer read successfully and received 403 for direct create/edit/archive POSTs. Missing CSRF was rejected. |
| `sudo docker compose up -d --force-recreate --wait` | All three containers recreated successfully without deleting volumes. |
| Post-recreation HTTPS and data checks | Full customer-row digests were unchanged, including IDs, identifiers, notes and timestamps. The previously authenticated Editor session still accessed customer details without logging in again. Health returned 200. |
| Existing-data checks | Digests of all five original accounts (identities, password hashes, active/staff/superuser flags and group memberships), `.env`, and Caddy public CA were unchanged. |

The automated suite covers required/invalid fields, normalization and leading zeros, duplicate identifiers, database constraints, archived identifier retention, uniqueness races, transaction rollback, role and model permission combinations, anonymous/inactive/unassigned users, direct unauthorized writes, read-only admin protection, CSRF, escaping, missing records, unsupported methods, search, filters, stable pagination and query preservation. The existing role-initialization assertion was extended to include the newly authorized customer-view grant.

A stronger service-input test discovered that Django TextField's `max_length` did not enforce the intended text limits during direct model validation. Explicit `MaxLengthValidator` validators were added for addresses and notes; the still-unapplied migration was regenerated, and the complete suite then passed. No unresolved test failures remain.

## Final state and limitations

The isolated review stack is running with three healthy containers at `https://portal.phase1.localhost/`; customer management is at `/customers/`. Existing login credentials remain valid. Two clearly named synthetic verification customers were archived after testing, and the three newly created rehearsal accounts were disabled. The original accounts were not changed. No real customer information was used in verification, no production service was modified, and no persistent volume was deleted.

CVR/company ID is a general optional identifier, not an external registry validation feature. Notes are visible to authorized portal readers. Graphical browser/mobile visual review was not performed; HTTP behavior and rendered pages were checked programmatically. No functional blocker remains for Phase 2 review.

Suggested next phase after review: Phase 3 — Contacts and contact points. No Phase 3 work has begun.
