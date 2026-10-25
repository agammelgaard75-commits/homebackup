import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from .forms import CustomerForm
from .models import Customer
from .services import archive_customer, create_customer, update_customer

User = get_user_model()


class CustomerFixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.users = {}
        for role in ("Viewer", "Editor", "Administrator"):
            user = User.objects.create_user(username=role.lower())
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.customer = create_customer(
            actor=cls.users["Editor"], name="Example Company", reference_code="DK-0012", notes="Internal example note",
        )

    def customer_data(self, **changes):
        return {
            "name": "Updated Company", "reference_code": "DK-0012", "status": "active",
            "address": "Example street", "notes": "Updated internal note", **changes,
        }


class CustomerModelTests(CustomerFixtures):
    def test_uuid_timestamps_and_defaults(self):
        customer = create_customer(actor=self.users["Editor"], name="Second customer")
        self.assertIsInstance(customer.pk, uuid.UUID)
        self.assertEqual(customer.status, "active")
        self.assertEqual(customer.reference_code, "")
        self.assertIsNotNone(customer.created_at)
        self.assertIsNotNone(customer.updated_at)

    def test_normalization_preserves_leading_zeros_and_optional_ids(self):
        customer = create_customer(actor=self.users["Editor"], name="  Acme  ", reference_code="  000abc  ")
        self.assertEqual(customer.name, "Acme")
        self.assertEqual(customer.reference_code, "000ABC")
        for name in ("No identifier one", "No identifier two"):
            self.assertEqual(create_customer(actor=self.users["Editor"], name=name, reference_code="  ").reference_code, "")

    def test_validation_rejects_invalid_fields(self):
        invalid = [
            {"name": " \t\n "}, {"name": None}, {"name": "x" * 201},
            {"reference_code": "bad id"}, {"reference_code": "<script>"}, {"reference_code": "x" * 65},
            {"status": "deleted"}, {"notes": "x" * 10001}, {"address": "x" * 2001},
        ]
        for changes in invalid:
            with self.subTest(fields=list(changes)), self.assertRaises(ValidationError):
                create_customer(actor=self.users["Editor"], **{**self.customer_data(reference_code=""), **changes})
        self.assertEqual(Customer.objects.count(), 1)

    def test_case_insensitive_unique_id_and_archive_keeps_identifier(self):
        archive_customer(actor=self.users["Editor"], customer_id=self.customer.pk)
        with self.assertRaises(ValidationError):
            create_customer(actor=self.users["Editor"], name="Duplicate", reference_code=" dk-0012 ")
        self.assertEqual(Customer.objects.count(), 1)

    def test_database_enforces_uniqueness_without_model_validation(self):
        for reference in ("dk-0012", " DK-0012 "):
            with self.subTest(reference=reference), self.assertRaises(IntegrityError), transaction.atomic():
                Customer.objects.create(name="Duplicate", reference_code=reference)

    def test_database_enforces_name_and_status(self):
        for data in ({"name": "  \t "}, {"name": "Name", "status": "removed"}):
            with self.subTest(data=data), self.assertRaises(IntegrityError), transaction.atomic():
                Customer.objects.create(**data)

    def test_form_validates_and_normalizes_without_saving(self):
        form = CustomerForm(self.customer_data(name="  New name ", reference_code=" abc-123 "))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.instance.name, "New name")
        self.assertEqual(form.instance.reference_code, "ABC-123")
        self.assertEqual(Customer.objects.count(), 1)

    def test_form_rejects_duplicates_and_missing_name(self):
        self.assertFalse(CustomerForm(self.customer_data()).is_valid())
        self.assertFalse(CustomerForm(self.customer_data(name=" ", reference_code="")).is_valid())
        self.assertFalse(CustomerForm(self.customer_data(status="deleted", reference_code="NEW")).is_valid())

    def test_valid_edit_does_not_conflict_with_own_identifier(self):
        form = CustomerForm(self.customer_data(), instance=self.customer)
        self.assertTrue(form.is_valid(), form.errors)


class CustomerServiceTests(CustomerFixtures):
    def test_editor_and_administrator_can_create_edit_archive_and_reactivate(self):
        for role in ("Editor", "Administrator"):
            with self.subTest(role=role):
                actor = self.users[role]
                customer = create_customer(actor=actor, name=f"{role} example")
                created_at = customer.created_at
                updated_at = customer.updated_at
                customer = update_customer(actor=actor, customer_id=customer.pk, **self.customer_data(reference_code=""))
                self.assertEqual(customer.name, "Updated Company")
                self.assertGreater(customer.updated_at, updated_at)
                archived = archive_customer(actor=actor, customer_id=customer.pk)
                self.assertEqual(archived.status, "inactive")
                self.assertEqual(archived.notes, "Updated internal note")
                archived_again = archive_customer(actor=actor, customer_id=customer.pk)
                self.assertEqual(archived_again.updated_at, archived.updated_at)
                restored = update_customer(actor=actor, customer_id=customer.pk, **self.customer_data(reference_code=""))
                self.assertEqual(restored.status, "active")
                self.assertEqual(restored.created_at, created_at)

    def test_service_rejects_viewer_anonymous_unassigned_and_inactive_actors(self):
        inactive = User.objects.create_user(username="inactive", is_active=False)
        inactive.groups.add(Group.objects.get(name="Administrator"))
        actors = [self.users["Viewer"], AnonymousUser(), inactive, User.objects.create_user(username="unassigned")]
        for actor in actors:
            for operation in ("create", "update", "archive"):
                with self.subTest(actor=type(actor).__name__, operation=operation), self.assertRaises(PermissionDenied):
                    if operation == "create":
                        create_customer(actor=actor, name="Unauthorized")
                    elif operation == "update":
                        update_customer(actor=actor, customer_id=self.customer.pk, **self.customer_data())
                    else:
                        archive_customer(actor=actor, customer_id=self.customer.pk)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.name, "Example Company")
        self.assertEqual(self.customer.status, "active")
        self.assertEqual(Customer.objects.count(), 1)

    def test_role_gate_and_model_permission_are_both_required(self):
        user = User.objects.create_user(username="custom-grants")
        grants = ["accounts.access_portal", "accounts.edit_portal", "customers.view_customer", "customers.add_customer"]
        for missing in grants:
            user.user_permissions.clear()
            for grant in grants:
                if grant != missing:
                    app, codename = grant.split(".")
                    user.user_permissions.add(Permission.objects.get(content_type__app_label=app, codename=codename))
            actor = User.objects.get(pk=user.pk)
            with self.subTest(missing=missing), self.assertRaises(PermissionDenied):
                create_customer(actor=actor, name="Unauthorized")

    def test_invalid_edit_rolls_back(self):
        with self.assertRaises(ValidationError):
            update_customer(actor=self.users["Editor"], customer_id=self.customer.pk, **self.customer_data(status="invalid"))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.name, "Example Company")
        self.assertEqual(self.customer.notes, "Internal example note")

    def test_database_uniqueness_race_becomes_validation_error(self):
        # Simulate another request winning after application-level validation.
        with patch.object(Customer, "full_clean"):
            with self.assertRaisesMessage(ValidationError, "already exists"):
                create_customer(actor=self.users["Editor"], name="Race loser", reference_code="dk-0012")
        self.assertEqual(Customer.objects.count(), 1)

    def test_managed_roles_never_receive_delete_permission(self):
        for role, actor in self.users.items():
            self.assertTrue(actor.has_perm("customers.view_customer"))
            self.assertEqual(actor.has_perm("customers.add_customer"), role != "Viewer")
            self.assertEqual(actor.has_perm("customers.change_customer"), role != "Viewer")
            self.assertFalse(actor.has_perm("customers.delete_customer"))


class CustomerViewTests(CustomerFixtures):
    def route(self, name):
        return reverse(f"customers:{name}", args=[self.customer.pk] if name in ("detail", "edit", "archive") else [])

    def test_all_routes_require_login(self):
        for name in ("list", "detail", "create", "edit", "archive"):
            for method in (self.client.get, self.client.post):
                response = method(self.route(name), secure=True)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith("/accounts/login/?next="))
        self.assertEqual(Customer.objects.count(), 1)

    def test_unassigned_and_staff_only_users_cannot_read_or_write(self):
        actor = User.objects.create_user(username="staff-only", is_staff=True)
        self.client.force_login(actor)
        for name in ("list", "detail", "create", "edit", "archive"):
            self.assertEqual(self.client.get(self.route(name), secure=True).status_code, 403)
            self.assertEqual(self.client.post(self.route(name), secure=True).status_code, 403)

    def test_viewer_reads_but_cannot_write_through_direct_requests(self):
        self.client.force_login(self.users["Viewer"])
        for name in ("list", "detail"):
            response = self.client.get(self.route(name), secure=True)
            self.assertContains(response, "Example Company")
            self.assertNotContains(response, "Add customer")
            self.assertNotContains(response, "Edit customer")
            self.assertNotContains(response, "Archive customer")
            self.assertIn("no-store", response["Cache-Control"])
        for name in ("create", "edit", "archive"):
            self.assertEqual(self.client.get(self.route(name), secure=True).status_code, 403)
            self.assertEqual(self.client.post(self.route(name), self.customer_data(), secure=True).status_code, 403)
        self.customer.refresh_from_db()
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(self.customer.status, "active")
        self.assertEqual(self.customer.name, "Example Company")

    def test_editor_and_administrator_full_http_workflow(self):
        for role in ("Editor", "Administrator"):
            self.client.force_login(self.users[role])
            self.assertContains(self.client.get(self.route("list"), secure=True), "Add customer")
            self.assertEqual(self.client.get(self.route("create"), secure=True).status_code, 200)
            response = self.client.post(self.route("create"), self.customer_data(name=role, reference_code=""), secure=True)
            customer = Customer.objects.get(name=role)
            self.assertRedirects(response, customer.get_absolute_url(), fetch_redirect_response=False)
            edit_url = reverse("customers:edit", args=[customer.pk])
            self.assertEqual(self.client.get(edit_url, secure=True).status_code, 200)
            response = self.client.post(edit_url, self.customer_data(name=f"Updated {role}", reference_code=""), secure=True)
            self.assertEqual(response.status_code, 302)
            archive_url = reverse("customers:archive", args=[customer.pk])
            self.assertEqual(self.client.get(archive_url, secure=True).status_code, 200)
            customer.refresh_from_db()
            self.assertEqual(customer.status, "active")  # confirmation GET is safe
            self.assertEqual(self.client.post(archive_url, secure=True).status_code, 302)
            customer.refresh_from_db()
            self.assertEqual(customer.status, "inactive")
            self.assertContains(self.client.get(customer.get_absolute_url(), secure=True), "This customer is archived")
            self.assertEqual(self.client.post(edit_url, self.customer_data(name=role, reference_code=""), secure=True).status_code, 302)
            customer.refresh_from_db()
            self.assertEqual(customer.status, "active")

    def test_invalid_forms_keep_input_without_writing(self):
        self.client.force_login(self.users["Editor"])
        response = self.client.post(self.route("create"), self.customer_data(name=" ", reference_code="", notes="Retain this draft"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertContains(response, "Retain this draft")
        self.assertEqual(Customer.objects.count(), 1)
        response = self.client.post(self.route("edit"), self.customer_data(status="invalid"), secure=True)
        self.assertTrue(response.context["form"].errors)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.name, "Example Company")

    def test_service_validation_error_is_rendered_as_field_error(self):
        self.client.force_login(self.users["Editor"])
        with patch("apps.customers.views.create_customer", side_effect=ValidationError({"reference_code": "Identifier already exists."})):
            response = self.client.post(self.route("create"), self.customer_data(reference_code="NEW"), secure=True)
        self.assertContains(response, "Identifier already exists.")
        self.assertEqual(Customer.objects.count(), 1)

    def test_csrf_is_required_for_create_edit_and_archive(self):
        client = Client(enforce_csrf_checks=True, HTTP_ORIGIN="https://testserver")
        client.force_login(self.users["Editor"])
        for name in ("create", "edit", "archive"):
            self.assertEqual(client.post(self.route(name), self.customer_data(), secure=True).status_code, 403)
        client.get(self.route("create"), secure=True)
        response = client.post(self.route("create"), {
            **self.customer_data(reference_code="CSRF-OK"), "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
        }, secure=True)
        self.assertEqual(response.status_code, 302)

    def test_names_addresses_and_notes_are_escaped(self):
        customer = create_customer(actor=self.users["Editor"], name='<script>alert("name")</script>',
                                   address="<b>address</b>", notes="<script>privateNote()</script>")
        self.client.force_login(self.users["Viewer"])
        response = self.client.get(customer.get_absolute_url(), secure=True)
        self.assertNotContains(response, "<script>")
        self.assertContains(response, "&lt;script&gt;privateNote()&lt;/script&gt;")
        self.assertContains(response, "&lt;b&gt;address&lt;/b&gt;")

    def test_unknown_customer_and_unsupported_methods(self):
        self.client.force_login(self.users["Editor"])
        for name in ("detail", "edit", "archive"):
            self.assertEqual(self.client.get(reverse(f"customers:{name}", args=[uuid.uuid4()]), secure=True).status_code, 404)
        self.assertEqual(self.client.get("/customers/not-a-uuid/", secure=True).status_code, 404)
        for name in ("list", "detail", "create", "edit", "archive"):
            self.assertEqual(self.client.delete(self.route(name), secure=True).status_code, 405)
        for name in ("list", "detail"):
            self.assertEqual(self.client.post(self.route(name), secure=True).status_code, 405)
        self.assertEqual(self.client.get(f"/customers/{self.customer.pk}/delete/", secure=True).status_code, 404)

    def test_read_only_admin_cannot_bypass_customer_services_or_delete(self):
        self.client.force_login(self.users["Administrator"])
        self.assertEqual(self.client.get(reverse("admin:customers_customer_changelist"), secure=True).status_code, 200)
        url = reverse("admin:customers_customer_change", args=[self.customer.pk])
        self.assertContains(self.client.get(url, secure=True), "Open customer")
        self.assertEqual(self.client.post(url, self.customer_data(), secure=True).status_code, 403)
        self.assertEqual(self.client.post(reverse("admin:customers_customer_add"), self.customer_data(), secure=True).status_code, 403)
        self.assertEqual(self.client.post(reverse("admin:customers_customer_delete", args=[self.customer.pk]), secure=True).status_code, 403)


class CustomerDirectoryTests(CustomerFixtures):
    def setUp(self):
        self.client.force_login(self.users["Viewer"])
        self.url = reverse("customers:list")

    def test_search_name_or_identifier_case_insensitively(self):
        for query in ("  eXaMpLe ", "dk-0012", "0012"):
            self.assertContains(self.client.get(self.url, {"q": query}, secure=True), "Example Company")
        self.assertContains(self.client.get(self.url, {"q": "nothing-matches"}, secure=True), "No customers found")
        self.assertContains(self.client.get(self.url, {"q": "' OR 1=1 --"}, secure=True), "No customers found")

    def test_status_filter_and_archive_visibility(self):
        archive_customer(actor=self.users["Editor"], customer_id=self.customer.pk)
        self.assertNotContains(self.client.get(self.url, secure=True), "Example Company")
        for status in ("inactive", ""):
            response = self.client.get(self.url, {"status": status, "q": "Example"}, secure=True)
            self.assertContains(response, "Example Company")
        response = self.client.get(self.customer.get_absolute_url(), secure=True)
        self.assertContains(response, "Internal example note")

    def test_invalid_filters_return_errors(self):
        for query in ({"status": "invalid"}, {"sort": "notes"}, {"q": "x" * 201}):
            response = self.client.get(self.url, query, secure=True)
            self.assertEqual(response.status_code, 400)
            self.assertTrue(response.context["filter_form"].errors)

    def test_pagination_retains_search_status_and_sort(self):
        Customer.objects.bulk_create([Customer(name=f"Page & Example {index:02}") for index in range(28)])
        query = {"q": "Page & Example", "status": "active", "sort": "name"}
        response = self.client.get(self.url, query, secure=True)
        self.assertEqual(len(response.context["page_obj"]), 25)
        self.assertContains(response, "q=Page+%26+Example&amp;status=active&amp;sort=name&amp;page=2")
        second = self.client.get(self.url, {**query, "page": 2}, secure=True)
        self.assertEqual(len(second.context["page_obj"]), 3)
        first_ids = {customer.pk for customer in response.context["page_obj"]}
        self.assertTrue(first_ids.isdisjoint(customer.pk for customer in second.context["page_obj"]))
        self.assertEqual(self.client.get(self.url, {**query, "page": "invalid"}, secure=True).context["page_obj"].number, 1)
        self.assertEqual(self.client.get(self.url, {**query, "page": 999}, secure=True).context["page_obj"].number, 2)

    def test_sorting_and_navigation(self):
        newest = create_customer(actor=self.users["Editor"], name="A company")
        response = self.client.get(self.url, secure=True)
        self.assertEqual(response.context["page_obj"][0], newest)
        self.assertContains(response, 'aria-current="page">Customers</a>')
        update_customer(actor=self.users["Editor"], customer_id=self.customer.pk, **self.customer_data())
        response = self.client.get(self.url, {"sort": "updated"}, secure=True)
        self.assertEqual(response.context["page_obj"][0].pk, self.customer.pk)
