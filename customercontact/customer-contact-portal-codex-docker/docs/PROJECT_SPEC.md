# Product specification

## Users and permissions
- **Viewer**: sign in, view customers, contacts, channels, services, search.
- **Editor**: all Viewer actions; create/edit/archive customers and contacts; create/edit/remove customer-service assignments. Cannot administer user roles.
- **Administrator**: all Editor actions; manage users, permissions, and service catalog.
- Everyone is authenticated; no anonymous access except the login screen.
- User roles are implemented using Django Groups + explicit permissions checked server-side.

## Navigation
Header: `Customers | Services | Search` and user/profile/logout. The `Administration` link is visible to admins only.

### 1. Customer directory (`/customers/`)
- Paginated table with name, status, number of active services, primary customer contact, last updated.
- Search by customer name and reference ID. Filters: active/inactive and service.
- Sort by name or last updated.
- Editors can add a customer; viewers cannot see edit controls.
- Clicking a row opens the customer detail page.

### 2. Customer detail (`/customers/<id>/`)
- Header: customer name, reference ID, status, primary general email/phone.
- Tabs: **Overview | Contacts | Services | Activity**.
- **Overview**: company fields, general contact channels and internal notes.
- **Contacts**: people with role, email(s), phone(s), preferred/primary flag, status. Support add/edit/archive.
- **Services**: current assigned services, status, optional start/end date and internal notes. Support assign/edit/end.
- **Activity**: timestamp, staff username, action and affected record, without dumping full personally identifiable record values.

### 3. Service catalog (`/services/`)
- Show catalog service names, descriptions and active/inactive state.
- Admin can add/edit/retire catalog services.
- Editors can only assign existing active catalog services to customers.
- Retired catalog services remain visible on customers with historical assignments.

### 4. Global search (`/search/`)
- One search input with results grouped as Customers, Contacts (people and general details), Services.
- Search by customer name, contact name, email address, phone number, service name.
- Results lead to relevant customer or record page.
- All searches are scoped to records the logged-in user may view.
- MVP may use straightforward case-insensitive database queries. No external search service.

### 5. Login/administration
- Django-provided authentication, session handling and CSRF protection.
- Use Django admin for user and group management initially; no custom admin UI in MVP.
- Disable open sign-up.

## Layout sketch
```text
+------------------------------------------------------------------+
| CUSTOMER PORTAL       Customers   Services   Search     User/Logout|
+------------------------------------------------------------------+
| Search customers... [________________________] [Status v] [+ Add] |
+------------------------------------------------------------------+
| Customer              Services     Main contact        Status    |
| Example A/S            3            support@...         Active    |
| Example Industries     1            +45 12 34 ...       Active    |
+------------------------------------------------------------------+

Customer: Example A/S                  [Edit]
[Overview] [Contacts] [Services] [Activity]

Contacts
Name                 Role          Email                Phone
Jane Example         Technical     jane@...             +45 ...
Support Desk         Support       support@...          +45 ...
[+ Add contact]
```

## CRUD rules
- Archive rather than hard-delete customers or people in the main interface.
- Customer-service assignment may be marked ended; preserve its relationship for reporting.
- Validate on the server, never rely only on browser checks.
- Empty values should render clearly (not placeholder addresses).
- For errors, retain form inputs and show validation messages.

## Non-functional requirements
- Works in modern desktop and mobile browsers.
- Responsive, accessible HTML with keyboard navigation and labels.
- HTTPS in production, secure cookies, least-privilege database access.
- Environment-driven configuration; no credentials checked into Git.
- Audit writes for creates, changes, archive actions and service assignments.
- Routine database backup and documented restore instructions before production use.
- Include automated tests for permissions, relationships, validation, and key pages.

## MVP definition of done
- Staff can log in and can only do actions permitted by their role.
- Admin can create a customer, create contacts with multiple email/phone contact points, create service catalog entries, and assign services.
- Viewer can search by name/email/phone/service and find the correct customer.
- Viewer cannot add/edit/archive via direct HTTP requests.
- Updates appear on customer detail and are recorded in activity history.
- Database is persistent across container restarts; migrations and tests succeed.
- README documents local installation and production precautions.

## Out of scope in MVP
Ticketing, billing, sending messages, contracts, SLA enforcement, attachments, synchronizing Splunk/CRM, AI chat, mobile apps, customer login, public API, background workers, multi-organization tenant isolation.
