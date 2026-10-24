from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.contacts.models import Contact, ContactPoint
from apps.customers.models import Customer
from apps.services.models import Service, CustomerService

User = get_user_model()


class SearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.users = {}
        for role in ("Viewer", "Editor", "Administrator"):
            user = User.objects.create_user(username=role.lower())
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.customer = Customer.objects.create(name="Example Industries", reference_code="DK-012345")
        cls.person = Contact.objects.create(customer=cls.customer, full_name="Alice Example", job_title="Systems Architect")
        cls.email = ContactPoint.objects.create(customer=cls.customer, contact=cls.person, kind="email", value="Alice@Example.invalid", normalized_value="alice@example.invalid")
        cls.phone = ContactPoint.objects.create(customer=cls.customer, contact=cls.person, kind="phone", value="+44 (20) 7946 0958", normalized_value="442079460958")
        cls.general = ContactPoint.objects.create(customer=cls.customer, kind="email", value="support@example.invalid", normalized_value="support@example.invalid")
        cls.general_phone = ContactPoint.objects.create(customer=cls.customer, kind="phone", value="+45 12 34 56 78", normalized_value="4512345678")
        cls.service = Service.objects.create(name="Infrastructure Monitoring", description="Operational telemetry")
        cls.assignment = CustomerService.objects.create(customer=cls.customer, service=cls.service)

    def setUp(self):
        self.client.force_login(self.users["Viewer"])

    def search(self, q, **params):
        return self.client.get(reverse("search:index"), {"q": q, **params}, secure=True)

    def rows(self, response, label):
        return next(group["results"] for group in response.context["groups"] if group["label"] == label)

    def test_customer_name_and_company_id_partial_case_insensitive(self):
        for query in ("AMPLE IND", "dk-012", "2345"):
            response = self.search(query)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.rows(response, "Customers")[0]["result_id"], str(self.customer.pk))
            self.assertContains(response, self.customer.get_absolute_url())

    def test_contact_name_title_and_email_partial(self):
        for query in ("ALICE", "architect", "lice@EXAM", "example.invalid"):
            response = self.search(query)
            people = [row for row in self.rows(response, "Contacts") if row["result_kind"] == "contact"]
            self.assertEqual(len(people), 1)
            self.assertEqual(people[0]["url"], self.person.get_absolute_url())
            self.assertEqual(people[0]["result_customer_name"], self.customer.name)

    def test_phone_formats_partial_and_general_information(self):
        for query in ("7946", "0044 20 7946", "+44 (20) 7946 0958"):
            self.assertEqual(self.rows(self.search(query), "Contacts")[0]["result_id"], str(self.person.pk))
        for query in ("SUPPORT@EX", "12345678", "0045 12 34"):
            rows = self.rows(self.search(query), "Contacts")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["result_kind"], "general")
            self.assertIn("?status=#detail-", rows[0]["url"])
            path, anchor = rows[0]["url"].split("#")
            self.assertContains(self.client.get(path, secure=True), f'id="{anchor}"')

    def test_catalog_description_and_assigned_services(self):
        for query in ("MONITOR", "teleMETRY"):
            rows = self.rows(self.search(query), "Services")
            self.assertCountEqual([row["result_kind"] for row in rows], ["service", "assignment"])
            assignment = next(row for row in rows if row["result_kind"] == "assignment")
            self.assertEqual(assignment["url"], self.assignment.get_absolute_url())
            self.assertEqual(assignment["result_customer_name"], self.customer.name)
        self.assertEqual(self.rows(self.search("DK-012"), "Services")[0]["result_kind"], "assignment")

    def test_archived_and_terminated_records_visible_with_status(self):
        Customer.objects.filter(pk=self.customer.pk).update(status="inactive")
        Contact.objects.filter(pk=self.person.pk).update(is_active=False)
        ContactPoint.objects.filter(pk=self.general.pk).update(is_active=False)
        Service.objects.filter(pk=self.service.pk).update(is_active=False)
        CustomerService.objects.filter(pk=self.assignment.pk).update(status="terminated")
        self.assertEqual(self.rows(self.search("Alice"), "Contacts")[0]["result_status"], "Archived")
        self.assertContains(self.search("support@"), "Archived")
        path, anchor = self.rows(self.search("support@"), "Contacts")[0]["url"].split("#")
        self.assertContains(self.client.get(path, secure=True), f'id="{anchor}"')
        self.assertContains(self.search("telemetry"), "Terminated")
        self.assertContains(self.search("telemetry"), "Archived catalog service")
        self.assertContains(self.search("Alice"), "Archived customer")

    def test_empty_whitespace_no_results_invalid_and_literal_query(self):
        for query in ("", "   "):
            response = self.search(query)
            self.assertEqual(response.context["groups"], [])
            self.assertContains(response, "Enter part of a name")
        for query in ("zzzz-no-match", "' OR 1=1 --", "%_"):
            self.assertContains(self.search(query), "No results found")
        self.assertEqual(self.search("x" * 201).status_code, 400)
        self.assertNotContains(self.search("<script>unsafe</script>"), "<script>unsafe</script>")

    def test_independent_group_pagination_preserves_query_and_other_pages(self):
        Customer.objects.bulk_create([Customer(name=f"Paged {i:02}") for i in range(24)])
        Contact.objects.bulk_create([Contact(customer=self.customer, full_name=f"Paged {i:02}") for i in range(13)])
        response = self.search("Paged", customers_page=2, contacts_page=2)
        groups = {group["label"]: group for group in response.context["groups"]}
        self.assertEqual(len(groups["Customers"]["results"]), 10)
        self.assertEqual(len(groups["Contacts"]["results"]), 3)
        self.assertContains(response, "q=Paged&amp;contacts_page=2&amp;customers_page=3")
        self.assertEqual(len(self.rows(self.search("Paged", customers_page=3), "Customers")), 4)
        self.assertEqual(self.search("Paged", customers_page="bad").status_code, 200)

    def test_services_group_paginates_catalog_and_repeated_assignments(self):
        CustomerService.objects.bulk_create([CustomerService(customer=self.customer, service=self.service) for _ in range(13)])
        response = self.search("monitor", services_page=2)
        self.assertEqual(len(self.rows(response, "Services")), 5)
        self.assertEqual(next(g for g in response.context["groups"] if g["label"] == "Services")["page"].paginator.count, 15)

    def test_roles_authentication_methods_and_cache(self):
        for role in self.users:
            self.client.force_login(self.users[role])
            response = self.search("Example")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.context["groups"]), 3)
            self.assertIn("no-store", response["Cache-Control"])
            self.assertEqual(self.client.post(reverse("search:index"), secure=True).status_code, 405)
        self.client.logout()
        self.assertEqual(self.search("Example").status_code, 302)
        user = User.objects.create_user(username="staff_only", is_staff=True)
        self.client.force_login(user)
        self.assertEqual(self.search("Example").status_code, 403)

    def test_custom_read_permissions_do_not_leak_records_or_counts(self):
        user = User.objects.create_user(username="limited")
        for app, code in (("accounts", "access_portal"), ("services", "view_service")):
            user.user_permissions.add(Permission.objects.get(content_type__app_label=app, codename=code))
        self.client.force_login(user)
        response = self.search("telemetry")
        self.assertEqual(len(response.context["groups"]), 1)
        self.assertEqual(response.context["total"], 1)
        self.assertNotContains(response, self.customer.name)
        user.user_permissions.add(Permission.objects.get(content_type__app_label="customers", codename="view_customer"))
        response = self.search("Example")
        self.assertEqual([g["label"] for g in response.context["groups"]], ["Customers", "Services"])
        self.assertNotContains(response, self.person.full_name)
        self.assertNotContains(response, self.assignment.get_absolute_url())
        self.assertNotContains(response, self.general.value)

    def test_contact_view_alone_does_not_leak_contact_details(self):
        user = User.objects.create_user(username="partial_contact")
        for app, code in (("accounts", "access_portal"), ("customers", "view_customer"), ("contacts", "view_contact")):
            user.user_permissions.add(Permission.objects.get(content_type__app_label=app, codename=code))
        self.client.force_login(user)
        response = self.search("private@example.invalid")
        self.assertNotIn("Contacts", [g["label"] for g in response.context["groups"]])

    def test_matching_multiple_points_does_not_duplicate_person(self):
        ContactPoint.objects.create(customer=self.customer, contact=self.person, kind="email", value="alice.two@example.invalid", normalized_value="alice.two@example.invalid")
        rows = self.rows(self.search("alice"), "Contacts")
        self.assertEqual(len(rows), 1)
