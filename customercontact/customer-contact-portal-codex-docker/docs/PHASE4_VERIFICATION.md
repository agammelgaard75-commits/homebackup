# Phase 4 verification — 24 October 2026

## Delivered functionality

The services app owns the central catalog and separate customer service agreements, including models, forms, views, URLs, templates, public write functions, read-only admin inspection and tests. Catalog entries have a unique name, optional short description/category, active/archive state and timestamps. Administrators manage entries through the GUI; names are not seeded or hardcoded. Catalog listing supports name/description/category search, status/category filtering and pagination. Each catalog entry shows its customer agreements and statuses, including historical agreements.

Customers have a Services tab with list/detail/create/edit/terminate workflows, status filtering and pagination. Multiple services per customer, the same service across customers, and repeated agreements for the same customer/service are supported. Each agreement retains a separate UUID, status (Active, Suspended, Expired, Terminated), optional dates/notes and timestamps. End date cannot precede start date. Customer Overview shows the count of active agreements.

Viewer reads; Editor manages agreements; Administrator additionally manages the catalog. Authentication, explicit model permissions and portal gates protect direct URLs and service-layer calls. The application/admin offers no deletion action. Archiving a catalog entry prevents new assignments but retains all existing agreements and permits their maintenance. Termination retains dates, notes and relationships. Status is maintained manually, independent of dates and catalog availability. Agreement ownership/catalog links are immutable through the GUI/API.

Key files:

- `apps/services/models.py`, `forms.py`, `permissions.py`, `services.py`, `selectors.py`
- `apps/services/views.py`, `urls.py`, `customer_urls.py`, `admin.py`, `templates/services/`, `tests.py`
- `apps/services/migrations/0001_initial.py`
- Account role mapping, customer overview, shared navigation/home and root URL integration.
- Contacts changes are limited to the Services link in its customer navigation.

Docker architecture, production configuration, dependencies, existing customer/contact schemas and authentication behavior were not changed. No billing, integrations, global search, audit or other Phase 5 implementation was added.

## Baseline and database changes

Before implementation, Git status and ignore rules were inspected. The previously verified Phase 3 source/documentation baseline was committed as **`07575c7`** (`Complete verified Phase 3 contact management`). No secrets, `.env`, runtime state or dumps were committed. Phase 4 changes remain available in the working tree for review.

`services.0001_initial` adds only two tables:

- **Service:** UUID, metadata, active flag and timestamps; nonblank-name and case-insensitive trimmed-name uniqueness constraints; category/active indexes. Archived names remain reserved.
- **CustomerService:** UUID, protected foreign keys to existing Customer and Service, status, nullable dates, notes and timestamps; valid-status/date-range constraints; customer/status composite index and automatic foreign-key indexes.

There is deliberately no customer/service pair uniqueness constraint. This and the four statuses implement the current Phase 4 request, superseding the earlier design proposal; the documentation was corrected. Existing tables/data are not rewritten. Role reconciliation adds service permissions while preserving existing account fields and memberships.

## Commands and actual results

All Django, PostgreSQL and HTTPS workflow execution ran inside Docker using the existing isolated `portal-phase1-review` project. Host commands used `sudo` for Docker access. The proxy remained bound to loopback; no production deployment occurred.

| Check | Observed result |
|---|---|
| Docker `manage.py makemigrations services` with the feature directory mounted | Generated additive `0001_initial.py` successfully. |
| `sudo docker compose build app` | Passed; static collection succeeded without database access. |
| `sudo ./scripts/test.sh` | **129 tests passed: all 92 existing tests plus 37 service tests.** Final full run: **35.041 seconds**. The earlier 128-test run also passed; a stale-submission regression check was then added and the full suite rerun. |
| `manage.py check` | No issues. |
| `manage.py check --deploy --fail-level WARNING` | Passed; only the two pre-existing documented internal-HSTS checks remain silenced. |
| `manage.py makemigrations --check --dry-run` | No changes detected. |
| `sudo docker compose config --quiet` | Passed. |
| `./scripts/tests/operations.sh` | Existing backup/restore/update/installer failure-path checks passed using their fake-Docker harness. No live restore was performed for Phase 4. |
| `sudo ./scripts/update.sh` | Created backup `backups/customer-portal-20261024T074430Z-DhbBGp.dump`, built the image, explicitly applied `services.0001_initial`, reconciled permissions, passed deployment checks and returned all three containers healthy. |
| `manage.py showmigrations services` | `[X] 0001_initial`. |
| HTTPS catalog workflow through Caddy with certificate verification | Administrator created two synthetic services, edited a service, rejected a duplicate case-insensitive name, searched/filtered and archived/restored. Viewer/Editor direct catalog-write URLs returned 403. |
| HTTPS customer agreement workflow | Editor and Administrator each created/edited a synthetic customer, created a contact/email, and added three agreements using two catalog services, including a repeated service. All four statuses, valid/invalid dates, editing and termination passed. |
| HTTPS history and authorization | Catalog archive retained complete assignment rows and blocked new assignments. Existing assignments and counts remained readable. Both customers appeared in catalog usage. Viewer writes and missing CSRF returned 403; a cross-customer assignment URL returned 404. |
| `sudo docker compose up -d --force-recreate --wait` | Recreated all three containers without removing volumes; all healthy. |
| Post-recreation verification | Complete synthetic customer/contact/detail/catalog/agreement row digests matched. A saved Editor login session still accessed an assignment over verified TLS. Database-aware `/health/` returned 200. |
| Existing data preservation | Digests of every pre-existing customer, contact, contact detail, user field (including password/flags) and group-membership row matched pre-change snapshots. |
| Configuration preservation | `.env`, `compose.yaml`, `Dockerfile`, `deploy/Caddyfile` and `requirements.txt` checksums were unchanged. |
| `git diff --check` | Passed. |

New tests cover optional fields and limits, unique names (including archived names), database constraints, repeated agreements, multiple customers/services, all statuses, date validation, immutable owner links, protected relationships, archive/termination preservation, active counts, invalid-update rollback, stale form submission after catalog archive, direct service-layer permission gates, anonymous/inactive/staff/unassigned users, direct URL authorization, CSRF, escaped HTML, read-only admin, filtering/pagination, and existing customer/contact integration. A PostgreSQL concurrency test uses separate connections to create two case-equivalent service names simultaneously: one succeeds, the other receives a validation error, and exactly one row remains.

## Final state and limitations

Phase 4 is **ready for review**. No functional blocker or unresolved test failure remains. The three review containers are healthy.

Open `https://portal.phase1.localhost/services/` for the catalog, or open a customer and choose **Services**. Existing credentials remain valid. To start this existing installation, use `sudo docker compose up -d --wait`; use `sudo ./scripts/update.sh` for upgrades requiring schema/code changes.

After testing, the six synthetic agreements were terminated, two synthetic catalog services/customer records/people were archived, and the three newly created test accounts disabled. Their two email details remain under the archived people. Cookie files were removed. No pre-existing records were changed/deleted and no persistent Docker volume was removed. Synthetic test records intentionally remain as archived history.

HTTP workflows and rendered HTML were verified programmatically over HTTPS. Graphical browser/mobile visual inspection was not performed. Agreement status is intentionally manual, and active counts count agreements rather than distinct catalog entries. No audit trail of individual field edits is included; that remains Phase 5.

Suggested next phase after review: **Phase 5 — Search, audit and polish**. It has not been started.
