"""Active defaults and per-page choice memory across the portal."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.contacts.models import Contact, ContactCustomer, ContactPoint
from apps.customers.models import Customer
from apps.services.models import CustomerService, Service


class PortalChoiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.users = {}
        for role in ("Viewer", "Editor", "Administrator"):
            user = get_user_model().objects.create_user(username=f"choices-{role.lower()}")
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.active_customer = Customer.objects.create(name="Current Customer")
        cls.archived_customer = Customer.objects.create(name="Former Customer", status="inactive")
        cls.active_contact = Contact.objects.create(customer=cls.active_customer, full_name="Current Person")
        cls.archived_contact = Contact.objects.create(customer=cls.active_customer, full_name="Former Person", is_active=False)
        cls.archived_customer_contact = Contact.objects.create(customer=cls.archived_customer, full_name="Hidden Person")
        for contact in (cls.active_contact, cls.archived_contact, cls.archived_customer_contact):
            ContactCustomer.objects.create(customer=contact.customer, contact=contact)
            ContactPoint.objects.create(customer=contact.customer, contact=contact, kind="email",
                value=f"{contact.pk}@example.invalid", normalized_value=f"{contact.pk}@example.invalid")
        cls.archived_point = ContactPoint.objects.create(customer=cls.active_customer, contact=cls.active_contact,
            kind="phone", value="12345678", normalized_value="12345678", is_active=False)
        cls.active_service = Service.objects.create(name="Current Service")
        cls.archived_service = Service.objects.create(name="Former Service", is_active=False)
        cls.active_assignment = CustomerService.objects.create(customer=cls.active_customer, service=cls.active_service)
        CustomerService.objects.create(customer=cls.active_customer, service=cls.active_service)
        cls.old_assignment = CustomerService.objects.create(customer=cls.active_customer,
            service=cls.archived_service, status="terminated")
        CustomerService.objects.create(customer=cls.archived_customer, service=cls.active_service)

    def setUp(self):
        self.client.force_login(self.users["Viewer"])

    def test_archived_records_hidden_by_default_and_explicitly_available(self):
        checks = (
            (reverse("customers:list"), "Former Customer", {"status": "inactive"}),
            (reverse("global_contacts:list"), "Former Person", {"status": "archived"}),
            (reverse("global_contacts:list"), "Hidden Person", {"include_archived_customers": "on"}),
            (reverse("services:list"), "Former Service", {"status": "archived"}),
            (reverse("customer_services:list", args=[self.active_customer.pk]),
             str(self.old_assignment.pk), {"status": "terminated"}),
        )
        for url, hidden, selected in checks:
            with self.subTest(url=url, hidden=hidden):
                self.assertNotContains(self.client.get(url, {"reset": "1"}, secure=True), hidden)
                self.assertContains(self.client.get(url, {"filters": "1", **selected}, secure=True), hidden)
        detail = reverse("contacts:detail", args=[self.active_customer.pk, self.active_contact.pk])
        self.assertNotContains(self.client.get(detail, {"reset": "1"}, secure=True), str(self.archived_point.pk))
        self.assertContains(self.client.get(detail, {"status": "archived"}, secure=True), str(self.archived_point.pk))
        catalog = reverse("services:detail", args=[self.active_service.pk])
        self.assertEqual(self.client.get(catalog, secure=True).context["page_obj"].paginator.count, 2)
        self.assertEqual(self.client.get(catalog, {"status": "", "include_archived_customers": "on"},
                                         secure=True).context["page_obj"].paginator.count, 3)

    def test_choice_memory_reset_and_no_search_text_in_session(self):
        url = reverse("customers:list")
        self.client.get(url, {"filters": "1", "status": "inactive", "sort": "updated", "q": "Former"}, secure=True)
        response = self.client.get(url, secure=True)
        self.assertEqual(response.context["filter_form"].cleaned_data["status"], "inactive")
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertIn("sessionid", self.client.cookies)
        self.assertNotIn("Former", str(dict(self.client.session.items())))
        response = self.client.get(url, {"reset": "1"}, secure=True)
        self.assertEqual(response.context["filter_form"].cleaned_data["status"], "active")
        self.assertEqual(response.context["page_obj"].paginator.count, 1)

    def test_choices_are_scoped_to_each_directory(self):
        catalog_url = reverse("services:list")
        contact_url = reverse("global_contacts:list")
        assignment_url = reverse("customer_services:list", args=[self.active_customer.pk])
        self.client.get(catalog_url, {"filters": "1", "status": "archived"}, secure=True)
        self.client.get(contact_url, {"filters": "1", "status": "archived"}, secure=True)
        self.client.get(assignment_url, {"filters": "1", "status": "terminated"}, secure=True)
        self.assertEqual(self.client.get(catalog_url, secure=True).context["page_obj"].paginator.count, 1)
        self.assertEqual(self.client.get(contact_url, secure=True).context["page_obj"].paginator.count, 1)
        self.assertEqual(self.client.get(assignment_url, secure=True).context["page_obj"].paginator.count, 1)
        self.assertEqual(self.client.get(reverse("customers:list"), secure=True).context["filter_form"].cleaned_data["status"], "active")
        self.client.get(catalog_url, {"reset": "1"}, secure=True)
        self.assertEqual(self.client.get(catalog_url, secure=True).context["page_obj"].paginator.count, 1)
        self.assertEqual(self.client.get(contact_url, secure=True).context["filter_form"].cleaned_data["status"], "archived")

    def test_search_and_service_choices_remembered_without_exposing_archived_by_default(self):
        search_url = reverse("search:index")
        self.assertEqual(next(group for group in self.client.get(search_url, {"q": "Former"}, secure=True).context["groups"]
                              if group["label"] == "Customers")["page"].paginator.count, 0)
        self.client.get(search_url, {"filters": "1", "q": "Former", "include_archived": "on"}, secure=True)
        response = self.client.get(search_url, {"q": "Former"}, secure=True)
        self.assertEqual(next(group for group in response.context["groups"] if group["label"] == "Customers")["page"].paginator.count, 1)
        self.client.get(search_url, {"reset": "1"}, secure=True)
        response = self.client.get(search_url, {"q": "Former"}, secure=True)
        self.assertEqual(next(group for group in response.context["groups"] if group["label"] == "Customers")["page"].paginator.count, 0)
        service_url = reverse("search:services")
        response = self.client.get(service_url, secure=True)
        self.assertNotIn(self.archived_service, response.context["filter_form"].fields["services"].queryset)
        response = self.client.get(service_url, {"filters": "1", "services": [str(self.archived_service.pk)],
                                                 "include_archived_services": "on"}, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.archived_service, response.context["filter_form"].fields["services"].queryset)
        self.assertTrue(self.client.get(service_url, secure=True).context["searched"])
        self.assertFalse(self.client.get(service_url, {"reset": "1"}, secure=True).context["searched"])

    def test_contact_form_top_fields_default_and_active_customer_choices(self):
        self.client.force_login(self.users["Editor"])
        for url in (reverse("global_contacts:create"), reverse("contacts:create", args=[self.active_customer.pk])):
            response = self.client.get(url, secure=True)
            self.assertEqual(response.status_code, 200)
            html = response.content.decode()
            self.assertLess(html.index('name="full_name"'), html.index('name="primary_email"'))
            self.assertLess(html.index('name="primary_email"'), html.index('name="contact_type"'))
            self.assertEqual(response.context["form"]["contact_type"].value(), "technical")
            self.assertNotIn(self.archived_customer, response.context["form"].fields["customers"].queryset)
        response = self.client.get(reverse("global_contacts:create"), {"include_archived_customers": "1"}, secure=True)
        self.assertIn(self.archived_customer, response.context["form"].fields["customers"].queryset)
        response = self.client.post(reverse("global_contacts:create"), {
            "full_name": "New Technical", "primary_email": "new@example.invalid",
            "customers": [str(self.active_customer.pk)],
            "methods-TOTAL_FORMS": "0", "methods-INITIAL_FORMS": "0",
            "methods-MIN_NUM_FORMS": "0", "methods-MAX_NUM_FORMS": "1000",
        }, secure=True)
        self.assertEqual(response.status_code, 302)
        contact = Contact.objects.get(full_name="New Technical")
        self.assertEqual(contact.contact_type, "technical")
        self.assertEqual(contact.points.get(kind="email").value, "new@example.invalid")
        response = self.client.post(reverse("contacts:create", args=[self.active_customer.pk]), {
            "full_name": "Customer Technical", "primary_email": "customer@example.invalid",
            "customers_present": "1", "customers": [str(self.active_customer.pk)],
            "methods-TOTAL_FORMS": "0", "methods-INITIAL_FORMS": "0",
            "methods-MIN_NUM_FORMS": "0", "methods-MAX_NUM_FORMS": "1000",
        }, secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Contact.objects.get(full_name="Customer Technical").contact_type, "technical")

    def test_edit_preserves_hidden_archived_customer_association(self):
        ContactCustomer.objects.create(contact=self.active_contact, customer=self.archived_customer)
        self.client.force_login(self.users["Editor"])
        url = reverse("contacts:edit", args=[self.active_customer.pk, self.active_contact.pk])
        response = self.client.get(url, secure=True)
        self.assertNotIn(self.archived_customer, response.context["form"].fields["customers"].queryset)
        response = self.client.post(url, {"full_name": "Updated Person", "customers_present": "1",
                                          "customers": [str(self.active_customer.pk)]}, secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ContactCustomer.objects.get(contact=self.active_contact, customer=self.archived_customer).is_active)
        response = self.client.post(url, {"full_name": "Updated Person", "customers_present": "1",
                                          "customers": [str(self.active_customer.pk)],
                                          "include_archived_customers": "on"}, secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ContactCustomer.objects.get(contact=self.active_contact, customer=self.archived_customer).is_active)

    def test_customer_overview_links_and_all_current_services_once(self):
        response = self.client.get(self.active_customer.get_absolute_url(), secure=True)
        self.assertContains(response, reverse("contacts:list", args=[self.active_customer.pk]))
        self.assertContains(response, "View all contacts for Current Customer")
        self.assertContains(response, "Current Service")
        self.assertEqual(list(response.context["overview_services"]), [self.active_service])
        self.assertNotContains(response, "Former Service")
        self.assertContains(response, reverse("customer_services:list", args=[self.active_customer.pk]))
        response = self.client.get(self.active_customer.get_absolute_url(), {"filters": "1", "services": "all"}, secure=True)
        self.assertCountEqual(list(response.context["overview_services"]), [self.active_service, self.archived_service])
        self.assertContains(response, "Former Service")
        self.assertEqual(len(response.context["overview_services"]), 2)
        self.assertEqual(len(self.client.get(self.active_customer.get_absolute_url(), secure=True).context["overview_services"]), 2)
        self.assertEqual(len(self.client.get(self.active_customer.get_absolute_url(), {"reset": "1"}, secure=True).context["overview_services"]), 1)

    def test_customer_overview_lists_every_contact_and_service_with_direct_links(self):
        extra_service = Service.objects.create(name="Another Current Service")
        CustomerService.objects.create(customer=self.active_customer, service=extra_service)
        CustomerService.objects.create(customer=self.active_customer, service=extra_service)
        created = []
        for index in range(7):
            contact = Contact.objects.create(customer=self.active_customer, full_name=f"Overview Person {index}",
                                             is_general=index == 0)
            ContactCustomer.objects.create(customer=self.active_customer, contact=contact)
            created.append(contact)
        url = self.active_customer.get_absolute_url()
        response = self.client.get(url, {"reset": "1"}, secure=True)
        self.assertEqual(len(response.context["overview_contacts"]), 8)
        self.assertCountEqual(list(response.context["overview_services"]), [self.active_service, extra_service])
        for contact in [self.active_contact, *created]:
            self.assertContains(response, reverse("contacts:detail", args=[self.active_customer.pk, contact.pk]))
        for service in (self.active_service, extra_service):
            self.assertContains(response, service.get_absolute_url())
        self.assertNotContains(response, self.archived_contact.full_name)
        response = self.client.get(url, {"filters": "1", "contacts": "all", "services": "current"}, secure=True)
        self.assertEqual(len(response.context["overview_contacts"]), 9)
        self.assertContains(response, reverse("contacts:detail", args=[self.active_customer.pk, self.archived_contact.pk]))
        self.assertEqual(len(self.client.get(url, secure=True).context["overview_contacts"]), 9)
        self.assertEqual(len(self.client.get(url, {"reset": "1"}, secure=True).context["overview_contacts"]), 8)

    def test_home_directory_hides_archived_records_by_default(self):
        response = self.client.get(reverse("core:home"), secure=True)
        self.assertNotContains(response, "Former Customer")
        self.assertNotContains(response, "Former Person")
        self.assertNotContains(response, "Hidden Person")
        self.assertContains(response, "Current Customer")
        self.assertContains(response, "Current Person")

    def test_permission_guard_still_precedes_choices(self):
        self.client.logout()
        for url in (reverse("customers:list"), reverse("global_contacts:list"), reverse("services:list"),
                    reverse("search:index"), self.active_customer.get_absolute_url()):
            self.assertEqual(self.client.get(url, {"status": "archived"}, secure=True).status_code, 302)
