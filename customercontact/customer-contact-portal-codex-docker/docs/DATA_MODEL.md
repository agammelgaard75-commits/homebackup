# Data model (MVP)

Use Django ORM and migrations. UUID primary keys are recommended for business records. Store `created_at` and `updated_at` on editable business records. Timestamps UTC in database; display with configured time zone.

## Customer (`customers` app)
- `id` UUID PK
- `name` required, searchable
- `reference_code` optional, unique when present (internal customer identifier)
- `status`: active | inactive
- `address` optional free-text for MVP
- `notes` optional, internal only
- `created_at`, `updated_at`
- `import_id` nullable unique stable key for explicitly mapped or newly imported JSON customers. Existing rows remain null until mapped; `company_id` in JSON maps to `reference_code`.

## Contact (`contacts` app)
- `id` UUID PK
- `customer_id` required FK -> original Customer (stable provenance and contact-point owner)
- `full_name` required
- `job_title` optional
- `contact_type`: technical | management | billing | support | other
- `is_general` bool (team/shared contact such as Support Desk or Reception)
- `is_active` bool
- `notes` optional
- `created_at`, `updated_at`
- `import_id` nullable unique stable key for explicitly mapped or newly imported JSON contacts. Existing rows remain null until mapped; imported multi-customer links use `ContactCustomer`.

`ContactCustomer` supplies one or more active customer associations for each Contact. The contact row is reused across customer and global pages; association archive removes a customer relationship without deleting the contact or its details.

## ContactPoint (`contacts` app)
Allows multiple contact email addresses and phone numbers for named or general contacts.
- `id` UUID PK
- `customer_id` required FK -> Contact's original Customer, retained for the existing composite foreign key
- `contact_id` required FK -> Contact; personless company points are no longer allowed
- `kind`: email | phone
- `label`: work | mobile | direct | support | other
- `value` required (email address or displayed phone number)
- `normalized_value` required normalized string for consistent search
- `is_primary` bool (at most one active primary per contact and kind)
- `created_at`, `updated_at`

Validation:
- The referenced Contact must have exactly the same original `customer_id` as the point; the contact may also be associated with other customers.
- Normalize emails for comparison/search; validate proper email shape.
- Permit international phone numbers; retain human-readable format. Use consistent normalizing/search strategy and test Danish and international formats.
- Enforce primary uniqueness in transactions/constraints where possible; tests must cover it.
- All customer email and phone values belong to Contact records. Customer has no email/phone fields.

## Service (`services` app)
- `id` UUID PK
- `name` required, unique
- `description` optional
- `category` optional
- `is_active` bool (whether new assignments are allowed)
- `created_at`, `updated_at`

## CustomerService (`services` app)
Join/assignment entity, not a plain unqualified many-to-many relationship.
- `id` UUID PK
- `customer_id` required FK -> Customer
- `service_id` required FK -> Service
- `status`: active | suspended | expired | terminated
- `start_date` optional
- `end_date` optional
- `notes` optional
- `created_at`, `updated_at`

Rules:
- Multiple assignments for the same customer/service are allowed as separate agreements or service periods, per the Phase 4 request. Each has its own UUID.
- `end_date >= start_date` when both provided.
- Inactive catalog services cannot be newly assigned; existing assignments remain visible.
- Deactivating a customer does not automatically erase service history.

## AuditEvent (`audit` app)
- `id` UUID PK
- `actor_id` required protected FK -> User (disable accounts instead of losing attribution)
- `customer_id` nullable protected FK -> Customer (required except for catalog events)
- `action`: created | updated | archived | restored | assigned | activated | suspended | expired | terminated
- `object_type` allowlisted entity type
- `object_id` UUID
- `description` fixed, non-sensitive action description
- `changed_fields` JSON list of allowlisted field names; no values
- `created_at`

Audit history is append-only through application code. Avoid logging contact emails, phone numbers or free-text notes in audit summaries.

## Relationships
```text
Customer 1 ────── * ContactCustomer * ────── 1 Contact
Customer 1 ────── * Contact [original owner/provenance]
Customer 1 ────── * ContactPoint [original owner/provenance]
Contact  1 ────── * ContactPoint
Customer 1 ────── * CustomerService * ────── 1 Service
User     1 ────── * AuditEvent
Customer 1 ────── * AuditEvent
```

## Search/index suggestions
- Index Customer(name), Customer(reference_code), Contact(customer_id, full_name), ContactPoint(customer_id, kind), ContactPoint(normalized_value), CustomerService(customer_id, status), CustomerService(service_id).
- Case-insensitive text search via Django/PostgreSQL for MVP. If volume grows significantly, revisit trigram/full-text indexing after measurement.

## Phase 2 customer implementation

`customers.Customer` now implements the customer entity. The requested **CVR / company ID** uses the planned `reference_code` field; it is not a second identifier. It accepts up to 64 ASCII letters/digits plus `.`, `/`, `_`, and `-`, starts with a letter/digit, trims surrounding whitespace, stores letters in uppercase, and preserves leading zeros. It is a general company identifier, with no external registry lookup or Denmark-specific checksum validation. Empty identifiers can repeat; supplied identifiers are unique ignoring case and surrounding spaces, including on archived records.

Names are required, trimmed and limited to 200 characters; duplicate company names are allowed. Optional addresses are limited to 2,000 characters and internal notes to 10,000. Forms and customer service functions call model validation. PostgreSQL constraints also enforce nonblank names, valid status values, and unique supplied identifiers, including concurrent writes.

Status values remain `active` and `inactive`; `inactive` is displayed as **Archived**. Archive retains the UUID, identifier, notes and creation timestamp, and changes status/updated_at. Editing an archived record can reactivate it. There is no application delete route or admin delete action.

Migration `customers/0001_initial.py` only adds the customer table, indexes and constraints. It does not modify or remove Phase 1 users, sessions, groups or existing data. Explicit `setup_roles` after migration adds customer grants to existing groups while retaining their memberships. No contacts, services or audit tables are introduced in this phase.

## Phase 3 contact implementation

The current Phase 3 request defines `Contact` as a UUID record belonging to exactly one protected Customer foreign key, with `full_name` (required, trimmed, maximum 200), optional `job_title` and `department` (maximum 200 each), `contact_type` (Technical, Management, Billing, Support, Other; defaults to Other), optional internal `notes` (maximum 10,000), `is_active`, and timestamps. These types supersede the earlier proposed role list. Primary selection applies to email/phone records; no preferred-person flag is introduced. Contacts cannot be reassigned to another customer through the application.

`ContactPoint` has protected `customer` and optional `contact` foreign keys, email/phone kind, Work/Mobile/Direct/Support/Other label (default Other), required value when adding a detail (maximum 254), normalized search value, primary/active flags and timestamps. A null person means a general customer contact point. A person can have any number of emails/phones; a name-only contact has no required contact points. General details use the same model and validation without duplicating customer records.

At most one **active primary** per owner and kind is enforced with separate PostgreSQL conditional unique constraints for people and general customer details. Selecting a new primary explicitly demotes the previous primary in the same transaction. Zero primaries are allowed. Archiving a person retains all its details and primary flags; restoring restores visibility. Archiving an individual detail retains its value and clears its primary flag; restoring the detail does not silently replace another primary. No main-UI or admin deletion is provided.

Email values are validated locally with Django and normalized to lowercase for search while preserving displayed case. Phone values retain formatting, permit 7–15 digits, a leading `+` or `00`, spaces, parentheses, dots and hyphens. Search strips formatting and the international `00` prefix; `+45 12 34 56 78` and `0045 12345678` normalize to `4512345678`. Local Danish eight-digit numbers are accepted; no country code is guessed. Country-code searches therefore match stored international forms; local suffix searches also match those international numbers. Extensions and registry verification are not supported; no external lookup occurs.

`contacts/0001_initial.py` adds only Contact/ContactPoint tables, indexes and constraints. `0002_contact_point_customer_integrity.py` adds a composite foreign key from `(contact_id, customer_id)` to Contact's declared unique `(id, customer_id)` key. This narrow schema migration uses PostgreSQL DDL because Django CheckConstraint cannot compare related rows; all application CRUD remains Django ORM. It prevents mismatched customer/person pairs and invalid reparenting even if model validation is bypassed. General details remain valid with a null contact. Neither migration changes existing customer/account records or their schemas.

## Phase 4 service implementation

The Phase 4 request supersedes the original unique-customer/service rule and three-status proposal. `services.Service` has a UUID, trimmed required name (maximum 200), optional description (maximum 1,000), optional trimmed category (maximum 100), active flag and timestamps. A PostgreSQL functional unique constraint reserves names ignoring case and surrounding spaces even after archive. Category is free text; names/categories are managed through the GUI, with no seeded catalog or unused service-code field.

`services.CustomerService` has its own UUID, protected customer/catalog foreign keys, Active/Suspended/Expired/Terminated status, nullable start/end dates, optional notes (maximum 10,000) and timestamps. Repeated customer/service pairs are intentionally allowed. Customer and catalog links are immutable in forms and the public write API. PostgreSQL enforces valid status and end date >= start date when both exist. Foreign-key indexes and a composite customer/status index support history and overview queries; catalog category/active fields are indexed.

Only active catalog entries can be newly assigned, checked inside a transaction holding the catalog row lock. Archiving a catalog entry leaves all existing agreements unchanged and editable. Termination retains dates, notes and relationships and is idempotent. Status can subsequently be edited, including on a terminated agreement. Dates are descriptive: no scheduler automatically expires or activates agreements. The overview count is the number of agreements with Active status, including repeated services and archived catalog entries. Archiving a customer does not erase or alter assignments.

`services/0001_initial.py` is additive: two new tables, constraints and indexes, with no existing table/data rewrites. No uniqueness constraint is applied to the customer/service pair. There is no application/admin delete action and no billing, contract document management or audit/event schema in this phase.

## Phase 5 audit implementation

`audit.AuditEvent` is an append-only application record with UUID, UTC `created_at`, required protected actor FK, action, allowlisted object type, object UUID, optional protected customer FK, fixed human-readable description and JSON list of changed field names. Actor and customer links use PROTECT so history cannot lose attribution or customer association through application deletion; accounts can still be disabled. Catalog events have no customer; all other event types require one. The object UUID is deliberately not a cascading foreign key to the mutable business object.

Supported object types are Customer, Contact, Contact detail (including general details), Catalog service and Service assignment. Actions are Created, Updated, Archived, Restored, Assigned, Activated, Suspended, Expired and Terminated. PostgreSQL constraints validate action/type and customer scope. Indexes cover newest-first global/customer activity, object lookups, actor and action. No field values or personal-data snapshots are stored; descriptions are generated from enums, never user-submitted free text.

Migration `audit.0001_initial` adds only this table, indexes, constraints and view permissions. Existing business schemas/data are unchanged. Historical activity before Phase 5 is **not** fabricated/backfilled. All supported subsequent business mutations use transactional recording; archive preserves history. No search/dashboard schema or additional runtime service is needed.

## Phase 5B shared contact extension

Phase 5B extends the Phase 3 one-customer model above. `ContactCustomer` is the authoritative association between a person and a customer: UUID, protected contact/customer foreign keys, active flag and timestamps. The `(contact, customer)` pair is unique; removing a customer archives the association and restoring it reuses the same row. At least one active association is required by the contact write service. Customer directories show active associations and include shared people once per customer. A person's own active/archived flag remains independent of association state.

`Contact.customer_id` is retained as the original owner and provenance, not treated as the sole current association. This preserves existing contact IDs, point ownership, the composite `(contact_id, customer_id)` foreign key on contact details, and all old email/phone records without a destructive rewrite. Person contact points continue to use the original customer as their database owner; their values appear under every actively associated customer. General contact points remain linked only to their customer.

Migration `contacts.0003_contact_customers` creates the new table and backfills exactly one active association from each preexisting contact's original customer. It does not update or delete Contact or ContactPoint rows. Migration `audit.0002_...` expands the audit type constraint to accept association events; existing events are untouched. Association create/archive/restore and person/detail changes record actor and affected customer(s) transactionally, using only field names and fixed descriptions. A previously removed original-customer GET URL redirects to an active association; writes through a removed association are refused.

At the Phase 5B checkpoint, the relationship was `Customer * ─ ContactCustomer ─ * Contact`; `Contact 1 ─ * ContactPoint` and the older customer-owned general points still existed. Both customer and contact status are checked for the default service-search result rows and email export. A contact shared by two customers is counted once on the dashboard.

## Contact unification after Phase 5B

The later contact-unification request supersedes the historical personless `ContactPoint` design described in the Phase 3/5B sections above. `Contact.is_general` distinguishes a team or shared contact from a named person; both are ordinary Contact rows with the same customer associations and email/phone support. `ContactPoint.contact_id` is now required. The existing `customer_id` on a point remains the original owner needed by the composite foreign key, and is not a second place to store an address or number.

The current contact write boundary requires at least one active valid email point or active nonempty phone point for both named and general contacts. All point rows in a contact edit are validated together; archiving the last active method fails unless the same transaction adds a replacement. No schema migration is used for this rule, so older incomplete Contact rows remain intact and readable. They must gain a valid method before their metadata, associations or status can be changed through the portal.

The later UI change makes Technical the default `contact_type` for new Contact records via `contacts.0006_default_technical_contact_type`. This is a default-only `AlterField`; it does not rewrite existing Contact rows or relationships. Archived customer options are hidden in new contact selection by default and can be explicitly included; existing hidden associations are preserved during edits.

`contacts.0004_unify_general_contact_points` adds the flag and groups every legacy null-contact point by customer. It creates at most one general contact per affected customer, or reuses an unambiguous empty `General Contact` placeholder belonging only to that customer. It attaches the original point rows without changing their IDs, values, normalized values, labels, primary/active flags or timestamps. A newly created contact is archived when all of its inherited points are archived. `contacts.0005_require_contact_for_details` then removes the obsolete general-primary constraint and makes `contact_id` non-null in a separate transaction, after foreign-key triggers from the data move have committed. The data migration aborts if any orphan remains; no value is discarded. Existing historical audit events remain untouched, and migrations do not fabricate an actor or event. The backup-first update flow provides the rollback point; the data migration is deliberately irreversible in place.
