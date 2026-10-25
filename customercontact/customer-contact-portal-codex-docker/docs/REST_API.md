# Customer Contact Portal REST API

The versioned API lives at `/api/v1/`. Its [OpenAPI schema](/api/v1/schema/) and
[interactive Swagger UI](/api/v1/docs/) require an Administrator browser session.
The Administration home page links to both. Paths below are relative to `/api/v1/`.
Business writes call the same customer, contact, service and import service functions
as the web interface. UUIDs are stable record IDs; timestamps use ISO 8601 UTC.

## Authentication and authorization

In the default `AUTH_MODE=local`, the credential flow below applies. With
`AUTH_MODE=oidc`, browser sessions use Keycloak and API calls use Keycloak
Bearer **access** tokens with the configured issuer, portal audience and
client roles. Legacy `ccp_` bearer credentials and their management endpoints
are disabled in OIDC mode. Valid OIDC tokens without a portal role get 403;
invalid, expired or wrong-audience tokens get 401. The same endpoint role
permissions continue to apply. See [Keycloak OIDC](KEYCLOAK_OIDC.md) for
realm setup, service accounts and curl examples.

Every endpoint except `GET health/` requires an authenticated, active portal user.
Session requests use the existing login cookie; **session writes require a CSRF
token**. Automation uses `Authorization: Bearer ccp_<credential-id>.<secret>`.
Never place a credential in a URL. No cross-origin access is enabled.

An Administrator creates a credential through `POST credentials/` while signed in
with a browser session. Supply a target `user_id`, label `name`, distinct `scopes`,
and an ISO 8601 `expires_at` within 366 days. The response shows the plaintext
token once; the database stores only an HMAC digest. `POST credentials/{id}/rotate/`
issues a replacement and invalidates the old token. `POST credentials/{id}/revoke/`
invalidates it immediately. Credential management requires an Administrator
**session**, not another bearer credential. Disable the owning user to disable its
credentials. Do not log authorization headers or returned tokens.

Scopes: `read` for business reads, `write` for permitted mutations, `import` for
import preview/execute, `audit` for global audit, and `cleanup` for cleanup reads
and execution. The credential owner's Viewer, Editor or Administrator permissions
must also allow the operation. Customer-specific activity uses `read`; global
audit uses `audit`. API documentation requires Administrator permissions.

## Response conventions

Lists return `count`, `next`, `previous`, and `results`. Use `page` (1-based) and
`page_size` (default 25, maximum 100). `next` and `previous` are URLs. Global
search paginates each result group separately with `customers_page`,
`contacts_page`, and `services_page`. `GET search/by-service/emails/` returns the
whole filtered email set, independent of result pagination.

Successful creates return `201`; reads and updates return `200`. Validation errors
return `400`, unauthenticated requests `401`, insufficient role/scope `403`,
missing records `404`, unsupported methods `405`, stale cleanup previews `409`, and throttling `429`. Errors
use one of these shapes:

```json
{"error":{"code":"validation_error","fields":{"name":["This field is required."]}}}
```

```json
{"error":{"code":"permission_denied","detail":"You do not have permission to perform this action."}}
```

Filtering is case-insensitive and uses partial matches for `q` unless specified.
Query strings are limited to 200 characters. Normal API requests have per-user
and anonymous rate limits; imports additionally allow 10 requests per minute.
Import JSON is limited by the existing `JSON_IMPORT_MAX_BYTES` and
`JSON_IMPORT_MAX_RECORDS` settings. Invalid booleans and choice values return
field-level `400` responses.

## Endpoints and permissions

`V` means Viewer, Editor or Administrator; `E` means Editor or Administrator;
`A` means Administrator. A bearer caller additionally needs the listed scope.
The listed scopes apply to local `ccp_` credentials; OIDC bearer callers use
their Keycloak portal client role and the endpoint's existing role check.

| Path | Methods | Role / scope | Parameters and behavior |
| --- | --- | --- | --- |
| `health/` | GET | Public | Database-backed application health; `200` or `503`. |
| `me/` | GET | V / read | Current user ID, username and roles. |
| `dashboard/` | GET | V / read | Active customer, contact and assignment counts. |
| `directory/` | GET | V / read | Unified Home table: `customer_q`, `contact_q`, `service_q`, repeated `services`, `customer_status=active\|inactive\|` (empty = all), `include_inactive_services`, `include_archived_contacts`, `sort=name\|-name`; paginated customer rows with linked contact/service IDs and names. |
| `credentials/` | GET, POST | A / session | Paginated metadata; create a scoped expiring credential. |
| `credentials/{id}/rotate/` | POST | A / session | Replace secret, returned once. |
| `credentials/{id}/revoke/` | POST | A / session | Revoke credential. |
| `customers/` | GET, POST | V / read; E / write | `q` name/company ID, `status=active\|inactive\|all` (default active), `sort=name\|-name\|updated`; create with name and optional `reference_code`, status, address, notes. |
| `customers/{id}/` | GET, PUT, PATCH | V / read; E / write | Read/update customer fields. |
| `customers/{id}/archive/`, `customers/{id}/restore/` | POST | E / write | Archive/restore, no hard delete. |
| `customers/{id}/contacts/` | GET | V / read | Paginated associated contacts; `include_archived=true`. |
| `customers/{id}/services/` | GET | V / read | Paginated assignments; `include_inactive=true`. |
| `customers/{id}/activity/` | GET | V / read | Customer activity; `actor_id`, `action`, `date_from`, `date_to`. |
| `contacts/` | GET, POST | V / read; E / write | `q` name/email/phone/customer, `status=active\|archived\|all`, `contact_type`, `customer_id`, `include_archived_customers`, `sort=name\|-name\|updated`; create contact with customer UUIDs and methods. |
| `contacts/{id}/` | GET, PUT, PATCH | V / read; E / write | Read/update contact; `methods` on write is the full active set when supplied. |
| `contacts/{id}/archive/`, `contacts/{id}/restore/` | POST | E / write | Archive/restore contact. |
| `contacts/{id}/methods/` | GET, POST | V / read; E / write | Active emails/phones by default; `include_archived=true`; add method. |
| `contacts/{id}/methods/{point_id}/` | GET, PUT, PATCH | V / read; E / write | Read/update an email or phone. |
| `contacts/{id}/methods/{point_id}/archive/`, `contacts/{id}/methods/{point_id}/restore/` | POST | E / write | Archive/restore a method, subject to the at-least-one-method rule. |
| `contacts/{id}/customers/` | GET, POST | V / read; E / write | List links; `include_archived=true`; add with `{"customer_id":"uuid"}`. |
| `contacts/{id}/customers/{customer_id}/remove/` | POST | E / write | Detach while retaining at least one customer. |
| `services/` | GET, POST | V / read; A / write | `q` name/description/category, `status=active\|archived\|all`, `category` exact match, `sort=name\|-name\|updated`; catalog create. |
| `services/{id}/` | GET, PUT, PATCH | V / read; A / write | Catalog details/update. |
| `services/{id}/archive/`, `services/{id}/restore/` | POST | A / write | Archive/restore catalog entry; assignments remain. |
| `services/{id}/customers/` | GET | V / read | Paginated assignments; `status=active\|suspended\|expired\|terminated\|all`. |
| `assignments/` | GET, POST | V / read; E / write | `q`, `customer_id`, `service_id`, `status`; create separate agreement. |
| `assignments/{id}/` | GET, PUT, PATCH | V / read; E / write | Update status, dates, notes; customer/service links are immutable. |
| `assignments/{id}/terminate/` | POST | E / write | Retain historical assignment. |
| `search/` | GET | V / read | `q`, `include_archived`; results grouped by customers, contacts and services. |
| `search/by-service/` | GET | V / read | Repeat `services=uuid`; `mode=any\|all` (default any), `include_inactive_assignments`, `include_archived_services`, `include_archived_customers`, `include_archived_contacts`, `sort=customer\|contact\|updated`; one row per customer/contact link, including customers without contacts. |
| `search/by-service/emails/` | GET | V / read | Same service filters; distinct emails from active contacts and active customers across every page. |
| `imports/customers/preview/`, `imports/contacts/preview/` | POST | A / import | Preview `{"document":{...},"mappings":{},"separate":[]}`; no data change. |
| `imports/customers/execute/`, `imports/contacts/execute/` | POST | A / import | Execute `{"confirmation_token":"...","confirm":true}` transactionally. |
| `audit/` | GET | A / audit | Read-only history; `actor_id`, `action`, `customer_id`, `date_from`, `date_to`. |
| `cleanup/archived-customers/`, `cleanup/archived-contacts/` | GET | A / cleanup | Paginated archived-only lists with `q`; contacts also accept `contact_type`. |
| `cleanup/preview/` | POST | A / cleanup | Archived `customer_ids` and `contact_ids` UUID arrays; exact plan and blockers. |
| `cleanup/confirm/` | POST | A / cleanup | Signed `confirmation_token` plus `confirm: true`; never GET. |
| `cleanup/operations/{id}/` | GET | A / cleanup | Read-only result, stable IDs, counts and confirmation reference. |
| `schema/`, `docs/` | GET | A / session or read | OpenAPI YAML/JSON and Swagger UI. |

All ordinary business detail paths reject DELETE. User and group administration
remains in the existing Django Administration interface; no API endpoint can
grant roles, edit audit events, execute host backups or access Docker.

### GUI coverage check

| Existing GUI task | API equivalent |
| --- | --- |
| Home customer directory and filters | `GET directory/`; `GET dashboard/` for counts. |
| Customer list, details, inline edit, archive/restore, contacts, services, activity | `customers/`, `customers/{id}/`, status actions, nested contacts/services/activity reads. |
| Global and customer contact lists, details, edits, methods and customer links | `contacts/`, `contacts/{id}/`, nested methods/customers and status actions. |
| Catalog list/details, edit/archive, customers using service | `services/`, `services/{id}/`, catalog status actions, `services/{id}/customers/`. |
| Customer service assignment/create/edit/terminate | `assignments/`, `assignments/{id}/`, terminate action. Reactivate with `PATCH status=active`. |
| Global search and Search By Service with Copy All Emails | `search/`, `search/by-service/`, `search/by-service/emails/`. |
| Customer/contact JSON import preview and confirm | `imports/{kind}/preview/`, `imports/{kind}/execute/`. |
| Global audit and customer Activity | `audit/`, `customers/{id}/activity/`; both are read-only. |
| Administration Data Cleanup | Archived lists, `cleanup/preview/`, `cleanup/confirm/`, operation result. |
| Login/logout and staff account/role management | Existing session login/logout and restricted Django Administration only. Credential issuance is separate; no user-role API exists. |
| Filter-choice cookies | Web-only convenience; API callers provide explicit query parameters. |
| Database backup/restore and deployment | Existing host-operated Docker scripts only; intentionally unavailable to the web/API process. |

### Contact write example

```json
{
  "full_name": "Support Desk",
  "is_general": true,
  "contact_type": "support",
  "customer_ids": ["CUSTOMER_UUID"],
  "methods": [
    {"kind": "email", "label": "work", "value": "support@example.invalid", "is_primary": true},
    {"kind": "phone", "label": "direct", "value": "+45 12 34 56 78"}
  ]
}
```

`methods` may contain multiple email and phone items. A contact must retain at
least one valid email **or** phone after the complete create/update request.
For updates, include an existing method's `point_id` to change it; `remove: true`
archives it. Omitting `methods` from PATCH leaves methods as they are. Supplying
`methods` replaces the active set, archiving omitted methods. The stable
`customer_ids` association list may contain multiple customers.

### Import examples

Use the existing [JSON import format](JSON_IMPORT_FORMAT.md),
[customer example](../examples/customers.example.json),
[contact example](../examples/contacts.example.json), and
[JSON schemas](../schemas/). Preview reports create/update/unchanged/reject
counts, candidate IDs, row errors and a signed confirmation token. The token
expires after 30 minutes and binds the preview to its user and data. Explicit
`mappings` are needed to update an existing record without a matching import ID;
names and email addresses alone are never auto-matched. Repeating a stable
`import_id` is idempotent. Execute revalidates the manifest and rolls back the
whole import if it changed or audit recording fails. Example files and the guide
remain downloadable from the customer/contact GUI import screens.

### Cleanup safeguards

Before **production** cleanup, run and verify a database backup using the
existing [Docker operations procedure](DOCKER_OPERATIONS.md). The application
has no Docker socket or backup-script access. Archived customers with service
assignment history are blocked. A customer's original contact must be archived
and selected separately; active or unselected original contacts block deletion.
Shared contacts owned by another customer are preserved and only their selected
customer link is detached. Archived contacts may be selected for deletion with
their methods and links. Audit events remain, with the deleted customer's stable
UUID retained separately from its nullable foreign key.

Preview makes no changes. It lists record UUIDs, detachment and deletion counts,
preserved contacts, audit counts and blockers. A signed token expires after 15
minutes, is bound to the Administrator and selection, and is rejected if the
dependency fingerprint changes. Confirm locks and rechecks dependencies, then
deletes explicitly in a transaction with a count-only audit event. An audit
failure rolls deletion back. Failed stale/protected attempts are separately
recorded when possible. Tokens cannot be reused after an operation. Database
backups can retain previously deleted personal information until backup
retention expires. No scheduled or force delete is available.

### curl examples

Use your actual HTTPS domain and a securely stored credential. These examples
use placeholders and do not put secrets in command-line query parameters.

```bash
curl --header "Authorization: Bearer $PORTAL_API_TOKEN" \
  'https://portal.example.internal/api/v1/customers/?q=example&status=active&page_size=25'

curl --header "Authorization: Bearer $PORTAL_API_TOKEN" \
  'https://portal.example.internal/api/v1/search/by-service/?services=SERVICE_UUID&mode=any'

curl --header "Authorization: Bearer $PORTAL_API_TOKEN" \
  'https://portal.example.internal/api/v1/search/by-service/emails/?services=SERVICE_UUID'

curl --request POST --header "Authorization: Bearer $PORTAL_API_TOKEN" \
  --header 'Content-Type: application/json' \
  --data '{"name":"Example Customer"}' \
  'https://portal.example.internal/api/v1/customers/'
```

For a browser session, send the existing `sessionid` cookie and a matching
`X-CSRFToken` header on POST/PUT/PATCH. The Swagger UI uses the same origin and
the established CSRF protection.
