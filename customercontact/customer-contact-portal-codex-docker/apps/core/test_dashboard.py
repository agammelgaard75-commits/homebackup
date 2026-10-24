from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.contacts.models import Contact
from apps.customers.models import Customer
from apps.services.models import Service, CustomerService

User = get_user_model()


class DashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.user = User.objects.create_user(username="viewer")
        cls.user.groups.add(Group.objects.get(name="Viewer"))
        cls.active = Customer.objects.create(name="Active customer")
        cls.archived = Customer.objects.create(name="Archived customer", status="inactive")
        cls.person = Contact.objects.create(customer=cls.active, full_name="Active person")
        Contact.objects.create(customer=cls.archived, full_name="Still active person")
        Contact.objects.create(customer=cls.active, full_name="Archived person", is_active=False)
        cls.service = Service.objects.create(name="Archived catalog", is_active=False)
        for status in ("active", "active", "suspended", "expired", "terminated"):
            CustomerService.objects.create(customer=cls.archived, service=cls.service, status=status)

    def setUp(self):
        self.client.force_login(self.user)

    def test_metrics_match_actual_records_with_explicit_status_semantics(self):
        response = self.client.get("/", secure=True)
        self.assertEqual(response.context["active_customers"], Customer.objects.filter(status="active").count())
        self.assertEqual(response.context["active_contacts"], 2)
        self.assertEqual(response.context["active_assignments"], 2)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.client.post("/", secure=True).status_code, 405)

    def test_recent_lists_order_limit_and_direct_links(self):
        for i in range(8):
            Customer.objects.create(name=f"Recent customer {i}")
            Contact.objects.create(customer=self.active, full_name=f"Recent person {i}")
        response = self.client.get("/", secure=True)
        customers = list(response.context["recent_customers"])
        people = list(response.context["recent_contacts"])
        self.assertEqual(len(customers), 5)
        self.assertEqual(len(people), 5)
        self.assertEqual(customers[0].name, "Recent customer 7")
        self.assertEqual(people[0].full_name, "Recent person 7")
        self.assertContains(response, people[0].get_absolute_url())
        self.assertContains(response, customers[0].get_absolute_url())

    def test_permissions_hide_metrics_and_recent_records(self):
        user = User.objects.create_user(username="minimal")
        user.user_permissions.add(Permission.objects.get(content_type__app_label="accounts", codename="access_portal"))
        self.client.force_login(user)
        response = self.client.get("/", secure=True)
        for key in ("active_customers", "active_contacts", "active_assignments", "recent_contacts", "recent_customers"):
            self.assertNotIn(key, response.context)
        self.assertNotContains(response, self.active.name)
        self.assertNotContains(response, self.person.full_name)
        self.assertNotContains(response, 'class="metric"')

    def test_shared_tabs_and_keyboard_friendly_controls(self):
        urls = [(self.active.get_absolute_url(), "Overview"), (reverse("contacts:list", args=[self.active.pk]), "Contacts"),
                (reverse("customer_services:list", args=[self.active.pk]), "Services"),
                (reverse("customer_activity:list", args=[self.active.pk]), "Activity")]
        for url, current in urls:
            response = self.client.get(url, secure=True)
            self.assertContains(response, 'aria-label="Customer sections"')
            for label in ("Overview", "Contacts", "Services", "Activity"):
                self.assertContains(response, f'>{label}</a>')
            self.assertContains(response, 'aria-current="page"')
            self.assertContains(response, 'class="skip-link"')
        response = self.client.get(reverse("search:index"), secure=True)
        self.assertContains(response, 'for="id_q"')
        self.assertContains(response, 'type="submit"')
        self.assertNotContains(response, '<script')
