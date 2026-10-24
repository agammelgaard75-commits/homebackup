from django.contrib.auth import get_user_model
import uuid
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse

from apps.contacts.models import Contact, ContactCustomer, ContactPoint
from apps.contacts.services import create_contact, save_contact_point, set_contact_active, set_contact_customers
from apps.customers.models import Customer
from apps.services.models import Service, CustomerService
from apps.services.services import create_service, create_assignment

User = get_user_model()


class ServiceContactSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.users = {}
        for role in ("Viewer", "Editor", "Administrator"):
            user = User.objects.create_user(username=role.lower())
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.a = Customer.objects.create(name="Alpha")
        cls.b = Customer.objects.create(name="Bravo")
        cls.c = Customer.objects.create(name="Charlie")
        cls.d = Customer.objects.create(name="Delta", status="inactive")
        cls.service1 = Service.objects.create(name="Monitoring")
        cls.service2 = Service.objects.create(name="Consulting")
        cls.service3 = Service.objects.create(name="Support")
        for customer, service, status in ((cls.a, cls.service1, "active"), (cls.a, cls.service1, "active"),
                                          (cls.a, cls.service2, "active"), (cls.b, cls.service1, "active"),
                                          (cls.b, cls.service2, "suspended"), (cls.c, cls.service1, "active"),
                                          (cls.d, cls.service1, "active"), (cls.d, cls.service2, "active")):
            CustomerService.objects.create(customer=customer, service=service, status=status)
        cls.shared = create_contact(actor=cls.users["Editor"], customer_id=cls.a.pk, full_name="Shared", contact_type="technical")
        set_contact_customers(actor=cls.users["Editor"], customer_id=cls.a.pk, contact_id=cls.shared.pk,
                              customer_ids=[cls.a.pk, cls.b.pk])
        cls.a_second = create_contact(actor=cls.users["Editor"], customer_id=cls.a.pk, full_name="Another", job_title="Operator")
        cls.archived = create_contact(actor=cls.users["Editor"], customer_id=cls.a.pk, full_name="Former", contact_type="management")
        set_contact_active(actor=cls.users["Editor"], customer_id=cls.a.pk, contact_id=cls.archived.pk, is_active=False)
        cls.email1 = save_contact_point(actor=cls.users["Editor"], customer_id=cls.a.pk, contact_id=cls.shared.pk,
                                        kind="email", value="Shared@Example.invalid", is_primary=True)
        cls.email2 = save_contact_point(actor=cls.users["Editor"], customer_id=cls.a.pk, contact_id=cls.shared.pk,
                                        kind="email", value="second@example.invalid")
        save_contact_point(actor=cls.users["Editor"], customer_id=cls.a.pk, contact_id=cls.shared.pk,
                           kind="phone", value="+45 12 34 56 78")
        save_contact_point(actor=cls.users["Editor"], customer_id=cls.a.pk, contact_id=cls.a_second.pk,
                           kind="email", value="shared@example.INVALID")
        save_contact_point(actor=cls.users["Editor"], customer_id=cls.a.pk, contact_id=cls.archived.pk,
                           kind="email", value="former@example.invalid")
        save_contact_point(actor=cls.users["Editor"], customer_id=cls.a.pk,
                           kind="email", value="reception@example.invalid")
        save_contact_point(actor=cls.users["Editor"], customer_id=cls.b.pk,
                           kind="email", value="shared@example.invalid")
        save_contact_point(actor=cls.users["Editor"], customer_id=cls.d.pk,
                           kind="email", value="archived-company@example.invalid")

    def setUp(self):
        self.client.force_login(self.users["Viewer"])

    def query(self, services=None, **extra):
        selected = services if services is not None else [self.service1.pk]
        return {"services": [str(service.pk if isinstance(service, Service) else service) for service in selected], **extra}

    def page(self, services=None, **extra):
        return self.client.get(reverse("search:services"), self.query(services, **extra), secure=True)

    def emails(self, services=None, **extra):
        return self.client.get(reverse("search:service_emails"), self.query(services, **extra), secure=True)

    def rows(self, response):
        return list(response.context["rows"])

    def test_single_service_and_one_row_per_customer_contact(self):
        response = self.page()
        self.assertEqual(response.status_code, 200)
        rows = self.rows(response)
        self.assertCountEqual([(r["row_customer_id"], r["row_contact_id"]) for r in rows],
                              [(self.a.pk, self.shared.pk), (self.a.pk, self.a_second.pk),
                               (self.b.pk, self.shared.pk), (self.c.pk, None)])
        self.assertEqual(len(rows), len(set((r["row_customer_id"], r["row_contact_id"]) for r in rows)))
        self.assertContains(response, self.shared.get_absolute_url())
        self.assertContains(response, "+45 12 34 56 78")
        self.assertNotContains(response, "Former")

    def test_multiple_services_any_all_and_repeated_agreements(self):
        services = [self.service1, self.service2]
        self.assertCountEqual({row["row_customer_id"] for row in self.rows(self.page(services, mode="any"))},
                              [self.a.pk, self.b.pk, self.c.pk])
        self.assertEqual({row["row_customer_id"] for row in self.rows(self.page(services, mode="all"))}, {self.a.pk})
        row = next(r for r in self.rows(self.page(services, mode="all")) if r["row_contact_id"] == self.shared.pk)
        self.assertEqual({service.name for service in row["matching_services"]}, {"Monitoring", "Consulting"})
        self.assertEqual(len(row["matching_services"]), 2)

    def test_inactive_assignments_and_archived_customer_contact_filters(self):
        rows = self.rows(self.page([self.service1, self.service2], mode="all", include_inactive_assignments="on"))
        self.assertEqual({r["row_customer_id"] for r in rows}, {self.a.pk, self.b.pk})
        rows = self.rows(self.page([self.service1, self.service2], mode="all", include_archived_customers="on"))
        self.assertEqual({r["row_customer_id"] for r in rows}, {self.a.pk, self.d.pk})
        rows = self.rows(self.page(include_archived_contacts="on"))
        self.assertIn((self.a.pk, self.archived.pk), {(r["row_customer_id"], r["row_contact_id"]) for r in rows})
        self.assertContains(self.page(include_archived_contacts="on"), "Archived contact")

    def test_no_contacts_and_multiple_contacts_per_customer(self):
        rows = self.rows(self.page())
        no_contact = next(r for r in rows if r["row_customer_id"] == self.c.pk)
        self.assertIsNone(no_contact["row_contact_id"])
        self.assertEqual(no_contact["emails"], [])
        self.assertEqual({r["row_contact_id"] for r in rows if r["row_customer_id"] == self.a.pk}, {self.shared.pk, self.a_second.pk})
        self.assertContains(self.page(), "No matching contacts")

    def test_email_export_collects_all_distinct_active_across_customers(self):
        response = self.emails()
        self.assertEqual(response.status_code, 200)
        addresses = response.json()["emails"].split("; ")
        self.assertCountEqual([address.lower() for address in addresses],
                              ["shared@example.invalid", "second@example.invalid", "reception@example.invalid"])
        self.assertEqual(response.json()["count"], 3)
        self.assertContains(self.page(), "3 unique emails")
        self.assertNotIn("former@example.invalid", addresses)
        self.assertNotIn("archived-company@example.invalid", addresses)
        self.assertIn("no-store", response["Cache-Control"])

    def test_email_export_ignores_display_archive_expansions(self):
        response = self.emails(include_archived_contacts="on", include_archived_customers="on")
        self.assertEqual(response.json()["count"], 3)
        self.assertNotIn("former@example.invalid", response.json()["emails"])
        self.assertNotIn("archived-company@example.invalid", response.json()["emails"])

    def test_email_export_across_all_pages(self):
        for i in range(28):
            contact = Contact.objects.create(customer=self.a, full_name=f"Extra {i:02}")
            ContactCustomer.objects.create(contact=contact, customer=self.a)
            ContactPoint.objects.create(customer=self.a, contact=contact, kind="email",
                                        value=f"extra{i:02}@example.invalid", normalized_value=f"extra{i:02}@example.invalid")
        response = self.page(page=2)
        self.assertEqual(response.context["page_obj"].paginator.count, 32)
        self.assertEqual(len(self.rows(response)), 7)
        exported = self.emails(page=2).json()
        self.assertEqual(exported["count"], 31)
        self.assertIn("extra00@example.invalid", exported["emails"])
        self.assertIn("extra27@example.invalid", exported["emails"])

    def test_sorting_pagination_and_invalid_filters(self):
        for sort in ("customer", "contact", "updated"):
            self.assertEqual(self.page(sort=sort).status_code, 200)
        for invalid in ({"mode": "bad"}, {"sort": "bad"}, {"services": [uuid.uuid4()]}):
            self.assertEqual(self.client.get(reverse("search:services"), invalid, secure=True).status_code, 400)
        self.assertEqual(self.client.get(reverse("search:services"), secure=True).status_code, 200)
        self.assertContains(self.client.get(reverse("search:services"), secure=True), "Choose one or more services")
        self.assertEqual(self.emails([]).status_code, 400)

    def test_permissions_all_roles_and_direct_endpoint(self):
        for role in ("Viewer", "Editor", "Administrator"):
            self.client.force_login(self.users[role])
            self.assertEqual(self.page().status_code, 200)
            self.assertEqual(self.emails().status_code, 200)
        self.client.logout()
        self.assertEqual(self.page().status_code, 302)
        self.assertEqual(self.emails().status_code, 302)
        user = User.objects.create_user(username="partial")
        user.user_permissions.add(Permission.objects.get(content_type__app_label="accounts", codename="access_portal"))
        self.client.force_login(user)
        self.assertEqual(self.page().status_code, 403)
        self.assertEqual(self.emails().status_code, 403)
        self.client.force_login(self.users["Viewer"])
        self.assertEqual(self.client.post(reverse("search:service_emails"), secure=True).status_code, 405)

    def test_page_queries_stay_bounded_with_many_contacts_and_points(self):
        for i in range(25):
            person = Contact.objects.create(customer=self.a, full_name=f"Query Person {i:02}")
            ContactCustomer.objects.create(contact=person, customer=self.a)
            ContactPoint.objects.create(customer=self.a, contact=person, kind="email",
                                        value=f"q{i:02}@example.invalid", normalized_value=f"q{i:02}@example.invalid")
        with CaptureQueriesContext(connection) as queries:
            response = self.page()
            self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 14)
