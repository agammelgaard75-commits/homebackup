from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.contacts.models import Contact, ContactCustomer, ContactPoint
from apps.customers.models import Customer
from apps.services.models import Service, CustomerService

User = get_user_model()


class CustomerDirectoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.users = {}
        for role in ("Viewer", "Editor", "Administrator"):
            user = User.objects.create_user(username=role.lower())
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.first = Customer.objects.create(name="Alpha")
        cls.second = Customer.objects.create(name="Beta")
        cls.empty = Customer.objects.create(name="Empty")
        cls.archived = Customer.objects.create(name="Archived", status="inactive")
        cls.person = Contact.objects.create(customer=cls.first, full_name="Shared Person")
        ContactCustomer.objects.create(contact=cls.person, customer=cls.first)
        ContactCustomer.objects.create(contact=cls.person, customer=cls.second)
        ContactPoint.objects.create(contact=cls.person, customer=cls.first, kind="email", label="work",
                                    value="shared@example.test", normalized_value="shared@example.test")
        cls.other = Contact.objects.create(customer=cls.first, full_name="Another Person")
        cls.inactive = Contact.objects.create(customer=cls.first, full_name="Archived Person", is_active=False)
        cls.service = Service.objects.create(name="Monitoring")
        cls.hidden_service = Service.objects.create(name="Retired", is_active=False)
        for customer in (cls.first, cls.second):
            CustomerService.objects.create(customer=customer, service=cls.service)
        CustomerService.objects.create(customer=cls.first, service=cls.service)
        CustomerService.objects.create(customer=cls.first, service=cls.hidden_service, status="suspended")

    def setUp(self):
        self.client.force_login(self.users["Viewer"])

    def test_home_is_one_row_per_active_customer_with_direct_links(self):
        response = self.client.get("/", secure=True)
        self.assertEqual(response.status_code, 200)
        rows = response.context["rows"]
        self.assertEqual([row["customer"].name for row in rows], ["Alpha", "Beta", "Empty"])
        self.assertEqual([contact.full_name for contact in rows[0]["contacts"]], ["Another Person", "Shared Person"])
        self.assertEqual([contact.full_name for contact in rows[1]["contacts"]], ["Shared Person"])
        self.assertEqual([service.name for service in rows[0]["services"]], ["Monitoring"])
        self.assertEqual(rows[2]["contacts"], [])
        self.assertEqual(rows[2]["services"], [])
        self.assertContains(response, self.first.get_absolute_url())
        self.assertContains(response, reverse("contacts:detail", args=[self.second.pk, self.person.pk]))
        self.assertContains(response, self.service.get_absolute_url())
        self.assertContains(response, "No contacts")
        self.assertContains(response, "No services")
        self.assertNotContains(response, "Recently updated")
        self.assertNotContains(response, "Active record counts")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.client.post("/", secure=True).status_code, 405)

    def test_search_filters_status_services_and_sort(self):
        for values, expected in (({"customer_q": "bet"}, ["Beta"]),
                                 ({"contact_q": "shared@"}, ["Alpha", "Beta"]),
                                 ({"contact_q": "another"}, ["Alpha"]),
                                 ({"service_q": "monitor"}, ["Alpha", "Beta"]),
                                 ({"services": [str(self.service.pk)]}, ["Alpha", "Beta"]),
                                 ({"services": [str(self.service.pk), str(self.hidden_service.pk)],
                                   "include_inactive_services": "on"}, ["Alpha", "Beta"]),
                                 ({"services": [str(self.hidden_service.pk)], "include_inactive_services": "on"}, ["Alpha"]),
                                 ({"customer_status": "inactive"}, ["Archived"]),
                                 ({"sort": "-name"}, ["Empty", "Beta", "Alpha"])):
            with self.subTest(values=values):
                response = self.client.get("/", {"filters": "1", "customer_status": "active", "sort": "name", **values}, secure=True)
                self.assertEqual(response.status_code, 200)
                self.assertEqual([row["customer"].name for row in response.context["rows"]], expected)
        response = self.client.get("/", {"filters": "1", "contact_q": "Archived Person"}, secure=True)
        self.assertEqual(response.context["rows"], [])
        response = self.client.get("/", {"filters": "1", "contact_q": "Archived Person",
                                         "include_archived_contacts": "on"}, secure=True)
        self.assertEqual([row["customer"].name for row in response.context["rows"]], ["Alpha"])
        self.assertContains(self.client.get("/", {"customer_q": "No such customer"}, secure=True),
                            "No customers match these filters.")

    def test_pagination_and_saved_filter_choice(self):
        for index in range(28):
            Customer.objects.create(name=f"Extra {index:02d}")
        first = self.client.get("/", {"filters": "1", "sort": "-name"}, secure=True)
        self.assertEqual(len(first.context["rows"]), 25)
        second = self.client.get("/", {"page": "2"}, secure=True)
        self.assertEqual(second.context["filter_form"].cleaned_data["sort"], "-name")
        self.assertEqual(len(second.context["rows"]), 6)
        selected = self.client.get("/", {"filters": "1", "services": [str(self.service.pk)],
                                          "include_archived_contacts": "on"}, secure=True)
        self.assertEqual(selected.status_code, 200)
        revisit = self.client.get("/", secure=True)
        self.assertEqual(list(revisit.context["filter_form"].cleaned_data["services"]), [self.service])
        self.assertTrue(revisit.context["filter_form"].cleaned_data["include_archived_contacts"])
        reset = self.client.get("/", {"reset": "1"}, secure=True)
        self.assertEqual(list(reset.context["filter_form"].cleaned_data["services"]), [])

    def test_permissions_and_navigation(self):
        response = self.client.get("/", secure=True)
        self.assertNotContains(response, "Add customer")
        self.assertNotContains(response, "Edit customer details")
        self.assertContains(response, f'href="{reverse("search:services")}"')
        self.assertContains(response, ">Search By Service</a>")
        service_search = self.client.get(reverse("search:services"), secure=True)
        self.assertContains(service_search, ">Search By Service</a>")
        self.assertContains(service_search, 'aria-current="page">Search By Service</a>')
        self.assertNotContains(service_search, 'aria-current="page">Search</a>')
        self.assertContains(self.client.get(reverse("search:index"), secure=True), reverse("search:services"))
        self.client.force_login(self.users["Editor"])
        self.assertContains(self.client.get(self.first.get_absolute_url(), secure=True), "Edit customer details")
        self.assertContains(self.client.get(self.first.get_absolute_url(), secure=True), "Add contact for this customer")
        self.assertContains(self.client.get(self.first.get_absolute_url(), secure=True), "Assign service to this customer")
        self.client.force_login(self.users["Administrator"])
        self.assertContains(self.client.get(self.service.get_absolute_url(), secure=True), "Edit catalog service")
        self.assertContains(self.client.get(reverse("search:index"), secure=True), reverse("audit:history"))
        minimal = User.objects.create_user(username="minimal")
        minimal.user_permissions.add(Permission.objects.get(content_type__app_label="accounts", codename="access_portal"))
        self.client.force_login(minimal)
        response = self.client.get("/", secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.first.name)
        minimal.user_permissions.add(Permission.objects.get(content_type__app_label="customers", codename="view_customer"))
        self.client.force_login(minimal)
        scoped = self.client.get("/", secure=True)
        self.assertContains(scoped, self.first.name)
        self.assertNotContains(scoped, self.person.full_name)
        self.assertNotContains(scoped, self.service.name)
        self.assertNotContains(scoped, "Contact name or email")
        self.assertNotContains(scoped, "Include archived contacts")
        self.assertNotContains(scoped, ">Search By Service</a>")
        self.client.logout()
        self.assertEqual(self.client.get("/", secure=True).status_code, 302)

    def test_shared_tabs_and_keyboard_friendly_controls(self):
        urls = [(self.first.get_absolute_url(), "Overview"), (reverse("contacts:list", args=[self.first.pk]), "Contacts"),
                (reverse("customer_services:list", args=[self.first.pk]), "Services"),
                (reverse("customer_activity:list", args=[self.first.pk]), "Activity")]
        for url, current in urls:
            response = self.client.get(url, secure=True)
            self.assertContains(response, 'aria-label="Customer sections"')
            self.assertContains(response, 'aria-current="page"')
            self.assertContains(response, 'class="skip-link"')

    def test_inline_customer_contact_and_service_forms_save_through_existing_handlers(self):
        self.client.force_login(self.users["Editor"])
        detail = self.client.get(self.first.get_absolute_url(), secure=True)
        self.assertContains(detail, f'action="{reverse("customers:edit", args=[self.first.pk])}"')
        self.assertContains(detail, f'action="{reverse("contacts:create", args=[self.first.pk])}"')
        self.assertContains(detail, f'action="{reverse("customer_services:create", args=[self.first.pk])}"')
        updated = self.client.post(reverse("customers:edit", args=[self.first.pk]), {
            "name": "Alpha Updated", "reference_code": "", "status": "active", "address": "", "notes": "",
        }, secure=True)
        self.assertRedirects(updated, self.first.get_absolute_url(), fetch_redirect_response=False)
        self.first.refresh_from_db()
        self.assertEqual(self.first.name, "Alpha Updated")
        created = self.client.post(reverse("contacts:create", args=[self.first.pk]), {
            "full_name": "Support Desk", "primary_email": "support@example.test", "is_general": "on",
            "job_title": "", "department": "", "contact_type": "support", "notes": "",
            "customers": [str(self.first.pk)], "customers_present": "1", "return_to": "customer",
            "methods-TOTAL_FORMS": "0", "methods-INITIAL_FORMS": "0",
        }, secure=True)
        self.assertRedirects(created, self.first.get_absolute_url(), fetch_redirect_response=False)
        support = Contact.objects.get(full_name="Support Desk")
        self.assertContains(self.client.get(self.first.get_absolute_url(), secure=True), support.full_name)
        self.assertContains(self.client.get(support.get_absolute_url(), secure=True), "Edit contact and customer associations")
        changed_contact = self.client.post(reverse("contacts:edit", args=[self.first.pk, self.person.pk]), {
            "full_name": "Shared Renamed", "job_title": "", "department": "", "contact_type": "technical",
            "notes": "", "return_to": "customer",
        }, secure=True)
        self.assertRedirects(changed_contact, self.first.get_absolute_url(), fetch_redirect_response=False)
        self.assertContains(self.client.get(self.second.get_absolute_url(), secure=True), "Shared Renamed")
        assigned = self.client.post(reverse("customer_services:create", args=[self.first.pk]), {
            "service": str(self.service.pk), "status": "active", "start_date": "", "end_date": "",
            "notes": "", "return_to": "customer",
        }, secure=True)
        self.assertRedirects(assigned, self.first.get_absolute_url(), fetch_redirect_response=False)
        self.assertEqual(CustomerService.objects.filter(customer=self.first, service=self.service).count(), 3)
        self.assertContains(self.client.get(self.first.get_absolute_url(), secure=True), "Manage service agreements")
        assignment = CustomerService.objects.filter(customer=self.first, service=self.service).first()
        updated_assignment = self.client.post(reverse("customer_services:edit", args=[self.first.pk, assignment.pk]), {
            "status": "suspended", "start_date": "", "end_date": "", "notes": "Paused",
            "return_to": "customer",
        }, secure=True)
        self.assertRedirects(updated_assignment, self.first.get_absolute_url(), fetch_redirect_response=False)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, "suspended")
        self.client.force_login(self.users["Administrator"])
        catalog = self.client.get(self.service.get_absolute_url(), secure=True)
        self.assertContains(catalog, f'action="{reverse("services:edit", args=[self.service.pk])}"')
        self.assertRedirects(self.client.post(reverse("services:edit", args=[self.service.pk]), {
            "name": "Monitoring Plus", "description": "", "category": "",
        }, secure=True), self.service.get_absolute_url(), fetch_redirect_response=False)
        self.service.refresh_from_db()
        self.assertEqual(self.service.name, "Monitoring Plus")

    def test_inline_validation_stays_on_record_detail_and_preserves_data(self):
        self.client.force_login(self.users["Editor"])
        response = self.client.post(reverse("customers:edit", args=[self.first.pk]), {
            "inline_edit": "1", "name": "", "reference_code": "", "status": "active",
            "address": "", "notes": "",
        }, secure=True)
        self.assertEqual(response.status_code, 400)
        self.assertTemplateUsed(response, "customers/detail.html")
        self.assertContains(response, "Edit customer details", status_code=400)
        response = self.client.post(reverse("contacts:edit", args=[self.first.pk, self.person.pk]), {
            "inline_edit": "1", "full_name": "Shared Person", "customers": [str(self.first.pk), str(self.second.pk)],
            "customers_present": "1", "is_general": "", "job_title": "", "department": "",
            "contact_type": "technical", "notes": "", "methods-TOTAL_FORMS": "1",
            "methods-INITIAL_FORMS": "1", "methods-0-point_id": str(self.person.points.first().pk),
            "methods-0-kind": "email", "methods-0-value": "shared@example.test",
            "methods-0-label": "work", "methods-0-remove": "on",
        }, secure=True)
        self.assertEqual(response.status_code, 400)
        self.assertTemplateUsed(response, "contacts/detail.html")
        self.assertContains(response, "At least one email address or phone number is required.", status_code=400)
        self.assertTrue(self.person.points.first().is_active)
        self.client.force_login(self.users["Administrator"])
        response = self.client.post(reverse("services:edit", args=[self.service.pk]), {
            "inline_edit": "1", "name": "", "description": "", "category": "",
        }, secure=True)
        self.assertEqual(response.status_code, 400)
        self.assertTemplateUsed(response, "services/catalog_detail.html")
        self.service.refresh_from_db()
        self.assertEqual(self.service.name, "Monitoring")

    def test_customer_page_manages_full_contact_methods_and_associations(self):
        self.client.force_login(self.users["Editor"])
        response = self.client.get(self.first.get_absolute_url(), {"edit_contact": str(self.person.pk)}, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manage Shared Person")
        self.assertContains(response, f'action="{reverse("contacts:edit", args=[self.first.pk, self.person.pk])}"')
        point = self.person.points.first()
        payload = {
            "inline_edit": "1", "return_to": "customer", "full_name": "Shared Person",
            "customers": [str(self.first.pk), str(self.second.pk)], "customers_present": "1",
            "job_title": "Engineer", "department": "", "contact_type": "technical", "notes": "",
            "methods-TOTAL_FORMS": "1", "methods-INITIAL_FORMS": "1", "methods-0-point_id": str(point.pk),
            "methods-0-kind": "email", "methods-0-value": "new-shared@example.test", "methods-0-label": "work",
        }
        saved = self.client.post(reverse("contacts:edit", args=[self.first.pk, self.person.pk]), payload, secure=True)
        self.assertRedirects(saved, self.first.get_absolute_url(), fetch_redirect_response=False)
        point.refresh_from_db()
        self.assertEqual(point.value, "new-shared@example.test")
        self.assertContains(self.client.get(self.second.get_absolute_url(), secure=True), "Shared Person")
        payload["methods-0-remove"] = "on"
        invalid = self.client.post(reverse("contacts:edit", args=[self.first.pk, self.person.pk]), payload, secure=True)
        self.assertEqual(invalid.status_code, 400)
        self.assertTemplateUsed(invalid, "customers/detail.html")
        self.assertContains(invalid, "At least one email address or phone number is required.", status_code=400)

    def test_archived_customer_contact_can_still_be_edited_from_customer_page(self):
        self.client.force_login(self.users["Editor"])
        contact = Contact.objects.create(customer=self.archived, full_name="Historic Desk")
        point = ContactPoint.objects.create(contact=contact, customer=self.archived, kind="phone", label="work",
                                            value="12345678", normalized_value="12345678")
        response = self.client.get(self.archived.get_absolute_url(), {"edit_contact": str(contact.pk)}, secure=True)
        self.assertContains(response, "Manage Historic Desk")
        saved = self.client.post(reverse("contacts:edit", args=[self.archived.pk, contact.pk]), {
            "inline_edit": "1", "return_to": "customer", "full_name": "Historic Reception",
            "customers": [str(self.archived.pk)], "customers_present": "1",
            "job_title": "", "department": "", "contact_type": "support", "notes": "",
            "methods-TOTAL_FORMS": "1", "methods-INITIAL_FORMS": "1", "methods-0-point_id": str(point.pk),
            "methods-0-kind": "phone", "methods-0-value": "12345678", "methods-0-label": "work",
        }, secure=True)
        self.assertRedirects(saved, self.archived.get_absolute_url(), fetch_redirect_response=False)
        contact.refresh_from_db()
        self.assertEqual(contact.full_name, "Historic Reception")
