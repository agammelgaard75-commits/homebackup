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

## Contact (`contacts` app)
- `id` UUID PK
- `customer_id` required FK -> Customer
- `full_name` required
- `job_title` optional
- `role`: general | technical | billing | escalation | management | other
- `is_primary` bool (only one primary person per customer; validate)
- `is_active` bool
- `notes` optional
- `created_at`, `updated_at`

## ContactPoint (`contacts` app)
Allows multiple contact numbers/email addresses for a person, **or** company-level general contact points.
- `id` UUID PK
- `customer_id` required FK -> Customer
- `contact_id` optional FK -> Contact, same Customer required; NULL means a company/general contact point.
- `kind`: email | phone
- `label`: work | mobile | support | billing | emergency | other
- `value` required (email address or displayed phone number)
- `normalized_value` optional stored normalized string for consistent search
- `is_primary` bool (at most one primary per owner and kind)
- `created_at`, `updated_at`

Validation:
- If `contact_id` is set, the referenced Contact must have exactly the same `customer_id`.
- Normalize emails for comparison/search; validate proper email shape.
- Permit international phone numbers; retain human-readable format. Use consistent normalizing/search strategy and test Danish and international formats.
- Enforce primary uniqueness in transactions/constraints where possible; tests must cover it.
- Do not duplicate general contact point values directly on Customer.

## Service (`services` app)
- `id` UUID PK
- `name` required, unique
- `code` optional, unique when present
- `description` optional
- `is_active` bool (whether new assignments are allowed)
- `created_at`, `updated_at`

## CustomerService (`services` app)
Join/assignment entity, not a plain unqualified many-to-many relationship.
- `id` UUID PK
- `customer_id` required FK -> Customer
- `service_id` required FK -> Service
- `status`: active | suspended | ended
- `start_date` optional
- `end_date` optional
- `notes` optional
- `created_at`, `updated_at`

Rules:
- Unique `(customer_id, service_id)` for MVP; edit/reopen the assignment rather than create duplicate rows.
- `end_date >= start_date` when both provided.
- Inactive catalog services cannot be newly assigned; existing assignments remain visible.
- Deactivating a customer does not automatically erase service history.

## AuditEvent (`audit` app)
- `id` UUID PK
- `actor_id` FK -> User (nullable if account subsequently removed)
- `customer_id` nullable FK -> Customer (preserve relevant link)
- `verb`: created | updated | archived | assigned | ended | status_changed
- `entity_type` short identifier
- `entity_id` UUID or safe text identifier
- `summary` brief, non-sensitive action description
- `created_at`

Audit history is append-only through application code. Avoid logging contact emails, phone numbers or free-text notes in audit summaries.

## Relationships
```text
Customer 1 ────── * Contact
Customer 1 ────── * ContactPoint [contact is optional]
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
