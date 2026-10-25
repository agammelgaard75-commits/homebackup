# Phase 5 verification — 24 October 2026

## Functionality implemented

- **Global search:** `/search/`, main-navigation access, partial case-insensitive customer name/company-ID, contact name/job-title/email/phone, general customer detail, catalog name/description and customer-agreement search. PostgreSQL ORM substring/UNION queries paginate Customers, Contacts and Services independently (ten results per group). Permission checks precede queries and counts. People matching multiple details appear once. Phone queries use existing normalization; archived records are included with status labels, customer context and direct links. Empty/invalid/no-result inputs have explicit feedback.
- **Audit:** synchronous metadata-only events for customer/contact/catalog creation and changes, archive/restore, contact detail changes and primary demotion, service assignment creation/updates and status transitions. Events store UTC time, actor ID, action, object type/UUID, related customer, fixed description and changed field names. No business field values, personal-data snapshots, passwords or session data are copied into audit entries. Business writes and events share one transaction; recording failure rolls both back.
- **History interface:** Administrator-only global Audit history; customer Activity for authorized customer readers, filtered further by contact/service read permissions. Inclusive UTC date, user and action filters; newest-first, 25-event pagination. Read-only views/admin and ORM update/delete protections; no event mutation routes or forms.
- **Dashboard/UI:** actual active customer/contact/agreement counts, five recently updated customers and recently created contacts, consistent permission-aware Overview/Contacts/Services/Activity tabs, shared pagination, responsive table/filter layouts, retained role badge, clear empty states and safe archive confirmations. Customer editing now confirms a transition to Archived before saving.

Key files at the time: `apps/search/{forms,selectors,views,urls,tests}.py` and templates; `apps/audit/{models,services,selectors,forms,views,urls,customer_urls,admin,tests}.py`, migration and templates; the former `apps/core/selectors.py` and `test_dashboard.py`, dashboard/shared component templates; audit integration in owning customer/contact/service write services; account grants, root URLs and shared CSS. A later home-directory redesign removed the unused dashboard selector and renamed the directory regression tests to `apps/core/test_directory.py`.

No new dependency, external API, search service, worker, business module, billing or Phase 6 work was introduced. The Docker architecture/settings remain unchanged.

## Baseline and database changes

Before implementation, Git status, staged files and ignore rules were checked. The verified Phase 4 baseline was committed as **`a8a700b`** (`Complete verified Phase 4 service catalog and assignments`). Secrets, `.env`, dumps and runtime verification files were excluded. Phase 5 source/documentation changes remain in the working tree for review.

`audit.0001_initial` adds one AuditEvent table, protected user/customer relationships, indexes for newest-first global/customer history and object lookups, action/type/customer-scope constraints, and read permissions. Existing business tables and records are not rewritten. Actor/customer deletion through the application is protected to retain attribution; disabling users and archiving business records remain supported. No historical events are invented or backfilled. Search/dashboard require no schema changes.

## Actual verification results

All Django, database and HTTPS workflow execution used the existing isolated Docker project `portal-phase1-review`. Docker access used `sudo`; proxy ports remained bound to loopback. No production configuration or server was modified.

| Command/check | Observed result |
|---|---|
| Docker `manage.py makemigrations audit` with module mounted | Generated additive `0001_initial.py`. |
| `sudo docker compose build app` | Passed; database-free static collection passed. |
| `sudo ./scripts/test.sh` | **167 tests passed: all 129 existing tests plus 38 Phase 5 tests. Final run: 44.215 seconds.** |
| `manage.py check` | No issues. |
| `manage.py check --deploy --fail-level WARNING` | Passed; only the two existing documented internal-HSTS checks remain silenced. |
| `manage.py makemigrations --check --dry-run` | No changes detected. |
| `sudo docker compose config --quiet` | Passed. |
| `./scripts/tests/operations.sh` | Existing backup/restore/update/installer failure-path harness passed. |
| `sudo ./scripts/update.sh` | Created backup `backups/customer-portal-20261024T082415Z-sCTWpH.dump`, built, applied `audit.0001_initial`, reconciled grants, passed checks and returned the stack healthy. |
| `manage.py showmigrations audit` | `[X] 0001_initial`. |
| Real HTTPS regression workflow | Administrator catalog management and Editor/Administrator customer/contact management, multiple/repeated agreements, statuses, dates, termination and archive/restore all passed through Caddy with certificate verification. |
| Real HTTPS global search | Customer names/IDs, partial person names/job titles/emails, local/international formatted phone fragments, general email/phone details, catalog descriptions and related agreements returned correct links. Empty/no-result states and direct general-detail anchors passed. |
| Audit lifecycle/attribution/privacy | Create/update/archive/restore and assignment status events were present for the correct object/customer and responsible Editor/Administrator. Changed-field metadata included actual changes. Synthetic contact values/notes were absent from stored audit metadata. |
| History authorization/immutability | Viewer/Editor global history returned 403. Customer Activity was readable to all three authorized roles. Missing underlying permissions were covered by automated tests. History POST returned 405; direct admin audit edits returned 403. UTC user/action/date filters passed. |
| Dashboard verification | Every displayed count matched a direct database count in Docker. All four customer tabs rendered consistently. |
| `sudo ./scripts/backup.sh` after audit data existed | Created `backups/customer-portal-20261024T082650Z-E9sSLR.dump`. PostgreSQL `pg_restore --list` confirmed AuditEvent TABLE and TABLE DATA entries. `pg_restore --file=/dev/null` read the complete archive successfully without touching database contents. No live restore was performed in Phase 5. |
| `sudo docker compose up -d --force-recreate --wait` | All three containers recreated and became healthy, without deleting volumes. |
| Persistence after recreation | Full synthetic business/audit row digests matched; an existing Editor session still accessed its agreement over verified HTTPS. Database-aware `/health/` returned 200. |
| Original data preservation | All pre-existing customer/contact/detail/catalog/agreement/user-field/group-membership digests matched snapshots. |
| Configuration preservation | `.env`, Compose, Dockerfile, Caddyfile, requirements and Django settings checksums were unchanged. |
| `git diff --check` | Passed. |

The first 166-test run found two UI regressions: the dashboard omitted the existing role badge (three role subtest failures), and general-detail links used an invalid all-status filter value. The badge was restored and links corrected to the existing empty-value filter. An additional test verified that a new AuditEvent instance cannot overwrite an existing event UUID; the final 167-test suite passed.

Audit tests cover every entity lifecycle, actor/customer IDs, fixed descriptions, changed fields, privacy, no-op suppression, invalid/unauthorized writes, database constraints, protected relationships, immutable records and read-only admin. Failure injection verifies rollback for all five entity creation types, all update/archive/termination paths, primary-detail replacement after an earlier event was written, and outer transaction failure. Search tests cover partial/case-insensitive matching, normalized phones, archived records, direct links, independent mixed-result pagination, duplicate-person prevention, invalid/literal input and permission-limited users. Dashboard tests cover actual counts, recent ordering/limits, permission hiding and accessible navigation/form markup. All previous business and concurrency tests still pass.

## Final state and outstanding limitations

**Phase 5 is ready for review.** No functional blocker or unresolved test failure remains. The review stack has three healthy containers.

Start the existing stack with `sudo docker compose up -d --wait`. Visit `https://portal.phase1.localhost/` for the dashboard, `/search/` for search, `/audit/` as an Administrator, or a customer's Activity tab. Existing login credentials remain valid.

After testing, six synthetic agreements were terminated; two catalog services, two customers, two people and the new general details were archived; three new test accounts were disabled. Audit history and business records were retained. Cookie files were removed. No original data or persistent volume was deleted.

Graphical browser/mobile visual inspection was not performed; HTML workflows and accessible markup were checked programmatically. Substring search is appropriate for the current directory, but large-volume performance has not been benchmarked. Audit begins with Phase 5 and protects portal/application mutations; it is not tamper-proof against a database owner. Status/count semantics remain explicit: active contacts/agreements may belong to archived customers, and dates do not automatically change status.

Suggested next phase, only when separately requested: **Phase 6 — Production-readiness checkpoint**. It has not been started.
