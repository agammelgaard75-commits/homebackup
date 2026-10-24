from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from unittest.mock import patch
import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from apps.contacts.models import Contact, ContactPoint
from apps.customers.models import Customer
from apps.customers.services import archive_customer

from .forms import AssignmentForm, ServiceForm
from .models import CustomerService, Service
from .selectors import active_service_count
from .services import create_assignment, create_service, set_service_active, terminate_assignment, update_assignment, update_service

User = get_user_model()


class ServiceFixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.users = {}
        for role in ("Viewer", "Editor", "Administrator"):
            user = User.objects.create_user(username=role.lower())
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.customer = Customer.objects.create(name="Synthetic Alpha")
        cls.other_customer = Customer.objects.create(name="Synthetic Beta")
        cls.service = create_service(actor=cls.users["Administrator"], name="Monitoring", category="Operations", description="System insights")
        cls.other_service = create_service(actor=cls.users["Administrator"], name="Consulting")
        cls.assignment = create_assignment(actor=cls.users["Editor"], customer_id=cls.customer.pk, service_id=cls.service.pk)

    def assign(self, **changes):
        return create_assignment(**{"actor": self.users["Editor"], "customer_id": self.customer.pk, "service_id": self.service.pk, **changes})

    def catalog_url(self, name):
        return reverse(f"services:{name}", args=[] if name in ("list", "create") else [self.service.pk])

    def assignment_url(self, name, customer=None):
        args = [(customer or self.customer).pk]
        if name not in ("list", "create"):
            args.append(self.assignment.pk)
        return reverse(f"customer_services:{name}", args=args)

    def payload(self, **changes):
        return {"service": str(self.service.pk), "status": "active", "start_date": "", "end_date": "", "notes": "", **changes}


class ServiceModelTests(ServiceFixtures):
    def test_minimal_catalog_and_optional_fields(self):
        form = ServiceForm({"name": "  Managed Infrastructure  "})
        self.assertTrue(form.is_valid(), form.errors)
        service = create_service(actor=self.users["Administrator"], **form.cleaned_data)
        self.assertEqual(service.name, "Managed Infrastructure")
        self.assertEqual(service.category, "")
        self.assertTrue(service.is_active)
        self.assertIsInstance(service.pk, uuid.UUID)
        self.assertIsNotNone(service.created_at)
        self.assertIsNotNone(service.updated_at)

    def test_catalog_validation_and_case_insensitive_uniqueness(self):
        for data in ({"name": " \t "}, {"name": "x" * 201}, {"name": " monitoring "},
                     {"description": "x" * 1001}, {"category": "x" * 101}):
            with self.subTest(fields=list(data)), self.assertRaises(ValidationError):
                create_service(actor=self.users["Administrator"], **{"name": "New", **data})
        set_service_active(actor=self.users["Administrator"], service_id=self.service.pk, is_active=False)
        with self.assertRaises(ValidationError):
            create_service(actor=self.users["Administrator"], name="MONITORING")
        self.assertFalse(ServiceForm({"name": "Monitoring"}).is_valid())

    def test_catalog_database_constraints(self):
        for name in (" \n ", "MONITORING", "  Monitoring  "):
            with self.subTest(name=name), self.assertRaises(IntegrityError), transaction.atomic():
                Service.objects.create(name=name)

    def test_catalog_edit_archive_restore_idempotence(self):
        service = update_service(actor=self.users["Administrator"], service_id=self.service.pk,
                                 name="  New Name  ", category=" Ops ", description="Description")
        self.assertEqual((service.name, service.category), ("New Name", "Ops"))
        created = service.created_at
        service = set_service_active(actor=self.users["Administrator"], service_id=service.pk, is_active=False)
        archived_at = service.updated_at
        service = set_service_active(actor=self.users["Administrator"], service_id=service.pk, is_active=False)
        self.assertEqual(service.updated_at, archived_at)
        service = set_service_active(actor=self.users["Administrator"], service_id=service.pk, is_active=True)
        self.assertEqual(service.created_at, created)
        self.assertTrue(service.is_active)

    def test_multiple_agreements_and_multiple_customers(self):
        repeated = self.assign(notes="Separate agreement", start_date=date(2026, 1, 1))
        another_service = self.assign(service_id=self.other_service.pk)
        another_customer = self.assign(customer_id=self.other_customer.pk)
        self.assertNotEqual(repeated.pk, self.assignment.pk)
        self.assertEqual(CustomerService.objects.filter(customer=self.customer).count(), 3)
        self.assertEqual(self.service.assignments.count(), 3)
        self.assertEqual(another_service.service, self.other_service)
        self.assertEqual(another_customer.customer, self.other_customer)

    def test_optional_dates_equal_dates_and_every_status(self):
        for status in CustomerService.Status.values:
            for start, end in ((None, None), (date(2026, 1, 1), None), (None, date(2026, 1, 1)),
                               (date(2026, 1, 1), date(2026, 1, 1))):
                record = self.assign(status=status, start_date=start, end_date=end)
                self.assertEqual(record.status, status)
                self.assertEqual(record.start_date, start)

    def test_assignment_validation_and_database_constraints(self):
        for fields in ({"status": "ended"}, {"notes": "x" * 10001},
                       {"start_date": "invalid"}, {"start_date": date(2026, 2, 1), "end_date": date(2026, 1, 1)}):
            with self.subTest(fields=list(fields)), self.assertRaises(ValidationError):
                self.assign(**fields)
        for fields in ({"status": "invalid"}, {"start_date": date(2026, 2, 1), "end_date": date(2026, 1, 1)}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                CustomerService.objects.create(customer=self.customer, service=self.service, **fields)
        self.assertEqual(CustomerService.objects.count(), 1)

    def test_immutable_assignment_relationships(self):
        for field, value in (("customer", self.other_customer), ("service", self.other_service)):
            record = CustomerService.objects.get(pk=self.assignment.pk)
            setattr(record, field, value)
            with self.assertRaises(ValidationError):
                record.full_clean()
        with self.assertRaises(CustomerService.DoesNotExist):
            update_assignment(actor=self.users["Editor"], customer_id=self.other_customer.pk,
                              assignment_id=self.assignment.pk, status="suspended")
        with self.assertRaises(CustomerService.DoesNotExist):
            terminate_assignment(actor=self.users["Editor"], customer_id=self.other_customer.pk, assignment_id=self.assignment.pk)

    def test_archived_service_blocks_new_assignments_but_preserves_existing(self):
        before = CustomerService.objects.values().get(pk=self.assignment.pk)
        set_service_active(actor=self.users["Administrator"], service_id=self.service.pk, is_active=False)
        with self.assertRaises(ValidationError):
            self.assign()
        self.assertEqual(before, CustomerService.objects.values().get(pk=self.assignment.pk))
        form = AssignmentForm(self.payload(), instance=CustomerService(customer=self.customer))
        self.assertFalse(form.is_valid())
        record = update_assignment(actor=self.users["Editor"], customer_id=self.customer.pk,
                                   assignment_id=self.assignment.pk, status="suspended", notes="Existing agreement")
        self.assertEqual(record.status, "suspended")
        form = AssignmentForm(self.payload(status="expired"), instance=record)
        self.assertTrue(form.is_valid(), form.errors)
        set_service_active(actor=self.users["Administrator"], service_id=self.service.pk, is_active=True)
        self.assign()

    def test_termination_retains_fields_and_is_idempotent(self):
        record = update_assignment(actor=self.users["Editor"], customer_id=self.customer.pk, assignment_id=self.assignment.pk,
                                   status="active", start_date=date(2026, 1, 1), end_date=date(2027, 1, 1), notes="Retain")
        before = CustomerService.objects.values().get(pk=record.pk)
        terminated = terminate_assignment(actor=self.users["Editor"], customer_id=self.customer.pk, assignment_id=record.pk)
        for field in ("id", "customer_id", "service_id", "notes", "start_date", "end_date", "created_at"):
            self.assertEqual(getattr(terminated, field), before[field])
        again = terminate_assignment(actor=self.users["Editor"], customer_id=self.customer.pk, assignment_id=record.pk)
        self.assertEqual(again.updated_at, terminated.updated_at)
        self.assertEqual(again.status, "terminated")

    def test_archive_customer_preserves_assignments_and_protected_relationships(self):
        before = CustomerService.objects.values().get(pk=self.assignment.pk)
        archive_customer(actor=self.users["Editor"], customer_id=self.customer.pk)
        self.assertEqual(before, CustomerService.objects.values().get(pk=self.assignment.pk))
        for record in (self.customer, self.service):
            with self.assertRaises(ProtectedError):
                record.delete()

    def test_failed_updates_preserve_stored_data(self):
        with self.assertRaises(ValidationError):
            update_assignment(actor=self.users["Editor"], customer_id=self.customer.pk,
                              assignment_id=self.assignment.pk, status="invalid", notes="Do not save")
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.notes, "")
        self.assertEqual(self.assignment.status, "active")
        with self.assertRaises(ValidationError):
            update_service(actor=self.users["Administrator"], service_id=self.service.pk, name="Consulting")
        self.service.refresh_from_db()
        self.assertEqual(self.service.name, "Monitoring")

    def test_active_count_tracks_agreements_not_catalog_or_dates(self):
        self.assign(start_date=date(2000, 1, 1), end_date=date(2001, 1, 1))
        self.assign(status="suspended")
        self.assign(status="expired")
        self.assign(status="terminated")
        self.assign(customer_id=self.other_customer.pk)
        set_service_active(actor=self.users["Administrator"], service_id=self.service.pk, is_active=False)
        self.assertEqual(active_service_count(self.customer), 2)
        terminate_assignment(actor=self.users["Editor"], customer_id=self.customer.pk, assignment_id=self.assignment.pk)
        self.assertEqual(active_service_count(self.customer), 1)

    def test_assignment_forms_dates_forged_owners_and_disabled_service(self):
        form = AssignmentForm(self.payload(start_date="2026-02-01", end_date="2026-01-01"), instance=CustomerService(customer=self.customer))
        self.assertFalse(form.is_valid())
        self.assertIn("end_date", form.errors)
        form = AssignmentForm(self.payload(service=str(self.other_service.pk), customer=str(self.other_customer.pk)), instance=self.assignment)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["service"], self.service)
        self.assertNotIn("customer", form.cleaned_data)


class ServicePermissionTests(ServiceFixtures):
    def test_service_layer_role_matrix(self):
        for role in ("Viewer", "Editor"):
            actor = self.users[role]
            for operation in (
                lambda: create_service(actor=actor, name="Forbidden"),
                lambda: update_service(actor=actor, service_id=self.service.pk, name="Forbidden"),
                lambda: set_service_active(actor=actor, service_id=self.service.pk, is_active=False),
            ):
                with self.subTest(role=role), self.assertRaises(PermissionDenied):
                    operation()
        for operation in (
            lambda: self.assign(actor=self.users["Viewer"]),
            lambda: update_assignment(actor=self.users["Viewer"], customer_id=self.customer.pk, assignment_id=self.assignment.pk, status="suspended"),
            lambda: terminate_assignment(actor=self.users["Viewer"], customer_id=self.customer.pk, assignment_id=self.assignment.pk),
        ):
            with self.assertRaises(PermissionDenied):
                operation()
        for role in ("Editor", "Administrator"):
            self.assign(actor=self.users[role])

    def test_anonymous_inactive_staff_and_unassigned_users_denied(self):
        unassigned = User.objects.create_user(username="unassigned")
        staff = User.objects.create_user(username="staff", is_staff=True)
        inactive = User.objects.create_user(username="inactive", is_active=False)
        inactive.groups.add(Group.objects.get(name="Administrator"))
        for actor in (AnonymousUser(), unassigned, staff, inactive):
            with self.assertRaises(PermissionDenied):
                self.assign(actor=actor)
            with self.assertRaises(PermissionDenied):
                create_service(actor=actor, name="No access")
        for actor in (unassigned, staff):
            self.client.force_login(actor)
            for url in (self.catalog_url("list"), self.assignment_url("list")):
                self.assertEqual(self.client.get(url, secure=True).status_code, 403)

    def test_model_permissions_and_portal_gates_required_independently(self):
        grants = ["accounts.access_portal", "accounts.edit_portal", "services.view_service",
                  "customers.view_customer", "services.view_customerservice", "services.add_customerservice"]
        for omitted in grants:
            user = User.objects.create_user(username=omitted)
            for permission in set(grants) - {omitted}:
                app, code = permission.split(".")
                user.user_permissions.add(Permission.objects.get(content_type__app_label=app, codename=code))
            with self.subTest(missing=omitted), self.assertRaises(PermissionDenied):
                self.assign(actor=user)
        editor = self.users["Editor"]
        editor.user_permissions.add(Permission.objects.get(content_type__app_label="services", codename="add_service"))
        with self.assertRaises(PermissionDenied):
            create_service(actor=editor, name="Requires administration gate")

    def test_role_setup_idempotent_and_no_delete_grants(self):
        call_command("setup_roles", verbosity=0)
        call_command("setup_roles", verbosity=0)
        for role in self.users:
            self.assertFalse(Group.objects.get(name=role).permissions.filter(content_type__app_label="services", codename__startswith="delete_").exists())
        self.assertFalse(self.users["Editor"].has_perm("services.change_service"))
        self.assertTrue(self.users["Administrator"].has_perm("services.change_service"))


class ServiceViewTests(ServiceFixtures):
    def test_every_route_requires_login(self):
        urls = [self.catalog_url(n) for n in ("list", "detail", "create", "edit", "archive", "restore")]
        urls += [self.assignment_url(n) for n in ("list", "detail", "create", "edit", "terminate")]
        for url in urls:
            for method in (self.client.get, self.client.post):
                with self.subTest(url=url):
                    response = method(url, secure=True)
                    self.assertEqual(response.status_code, 302)
                    self.assertTrue(response.url.startswith("/accounts/login/"))

    def test_viewer_reads_and_all_direct_writes_denied(self):
        self.client.force_login(self.users["Viewer"])
        for url in (self.catalog_url("list"), self.catalog_url("detail"), self.assignment_url("list"), self.assignment_url("detail")):
            response = self.client.get(url, secure=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn("no-store", response["Cache-Control"])
            self.assertNotContains(response, 'class="button"')
        for url in [self.catalog_url(n) for n in ("create", "edit", "archive", "restore")] + [self.assignment_url(n) for n in ("create", "edit", "terminate")]:
            for method in (self.client.get, self.client.post):
                self.assertEqual(method(url, secure=True).status_code, 403)

    def test_editor_cannot_manage_catalog(self):
        self.client.force_login(self.users["Editor"])
        for name in ("create", "edit", "archive", "restore"):
            for method in (self.client.get, self.client.post):
                self.assertEqual(method(self.catalog_url(name), secure=True).status_code, 403)
        self.assertNotContains(self.client.get(self.catalog_url("list"), secure=True), "Create service")

    def test_administrator_catalog_workflow(self):
        self.client.force_login(self.users["Administrator"])
        response = self.client.post(self.catalog_url("create"), {"name": "New Service", "description": "Short", "category": "Cloud", "is_active": False}, secure=True)
        self.assertEqual(response.status_code, 302)
        service = Service.objects.get(name="New Service")
        self.assertTrue(service.is_active)
        self.assertEqual(self.client.post(self.catalog_url("edit"), {"name": "Edited", "category": "Ops"}, secure=True).status_code, 302)
        for name, active in (("archive", False), ("restore", True)):
            self.assertEqual(self.client.get(self.catalog_url(name), secure=True).status_code, 200)
            self.assertEqual(self.client.post(self.catalog_url(name), secure=True).status_code, 302)
            self.service.refresh_from_db()
            self.assertEqual(self.service.is_active, active)

    def test_editor_and_admin_assignment_workflow(self):
        for role in ("Editor", "Administrator"):
            self.client.force_login(self.users[role])
            response = self.client.post(self.assignment_url("create"), self.payload(customer=str(self.other_customer.pk), notes="Agreement"), secure=True)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(CustomerService.objects.get(pk=response.url.rstrip("/").split("/")[-1]).customer, self.customer)
            self.assertEqual(self.client.get(self.assignment_url("edit"), secure=True).status_code, 200)
            for status in CustomerService.Status.values:
                response = self.client.post(self.assignment_url("edit"), self.payload(status=status, service=str(self.other_service.pk)), secure=True)
                self.assertEqual(response.status_code, 302)
                self.assignment.refresh_from_db()
                self.assertEqual(self.assignment.status, status)
                self.assertEqual(self.assignment.service, self.service)
            self.assertEqual(self.client.post(self.assignment_url("terminate"), secure=True).status_code, 302)

    def test_invalid_forms_retain_input_and_do_not_write(self):
        self.client.force_login(self.users["Administrator"])
        response = self.client.post(self.catalog_url("create"), {"name": "monitoring", "description": "Retain input"}, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Retain input")
        self.assertTrue(response.context["form"].errors)
        response = self.client.post(self.assignment_url("create"), self.payload(start_date="2026-12-31", end_date="2026-01-01", notes="Retained"), secure=True)
        self.assertContains(response, "Retained")
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(CustomerService.objects.count(), 1)

    def test_archived_catalog_remains_visible_and_cannot_be_assigned_by_url(self):
        set_service_active(actor=self.users["Administrator"], service_id=self.service.pk, is_active=False)
        self.client.force_login(self.users["Editor"])
        response = self.client.post(self.assignment_url("create"), self.payload(), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("service", response.context["form"].errors)
        self.assertEqual(CustomerService.objects.count(), 1)
        self.assertContains(self.client.get(self.assignment_url("list"), secure=True), "Archived catalog service")
        response = self.client.post(self.assignment_url("edit"), self.payload(status="suspended"), secure=True)
        self.assertEqual(response.status_code, 302)

    def test_catalog_archived_after_form_validation_shows_error_without_assignment(self):
        self.client.force_login(self.users["Editor"])

        def archive_then_create(**kwargs):
            set_service_active(actor=self.users["Administrator"], service_id=self.service.pk, is_active=False)
            return create_assignment(**kwargs)

        with patch("apps.services.views.create_assignment", side_effect=archive_then_create):
            response = self.client.post(self.assignment_url("create"), self.payload(notes="Retained draft"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This catalog service is archived")
        self.assertContains(response, "Retained draft")
        self.assertEqual(CustomerService.objects.count(), 1)

    def test_wrong_customer_missing_records_and_unsupported_methods(self):
        self.client.force_login(self.users["Administrator"])
        for name in ("detail", "edit", "terminate"):
            self.assertEqual(self.client.get(self.assignment_url(name, self.other_customer), secure=True).status_code, 404)
        for name in ("edit", "terminate"):
            self.assertEqual(self.client.post(self.assignment_url(name, self.other_customer), self.payload(), secure=True).status_code, 404)
        self.assertEqual(self.client.get(reverse("services:detail", args=[uuid.uuid4()]), secure=True).status_code, 404)
        self.assertEqual(self.client.get(reverse("customer_services:create", args=[uuid.uuid4()]), secure=True).status_code, 404)
        for url in (self.catalog_url("list"), self.catalog_url("detail"), self.assignment_url("list"), self.assignment_url("detail")):
            self.assertEqual(self.client.post(url, secure=True).status_code, 405)
        for url in (self.catalog_url("edit"), self.assignment_url("edit")):
            self.assertEqual(self.client.delete(url, secure=True).status_code, 405)
        self.assertEqual(self.client.get(f"/services/{self.service.pk}/delete/", secure=True).status_code, 404)

    def test_csrf_for_every_mutation(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.users["Administrator"])
        for url in [self.catalog_url(n) for n in ("create", "edit", "archive", "restore")] + [self.assignment_url(n) for n in ("create", "edit", "terminate")]:
            self.assertEqual(client.post(url, secure=True).status_code, 403)

    def test_customer_overview_counts_navigation_and_existing_contacts(self):
        person = Contact.objects.create(customer=self.customer, full_name="Existing Person")
        ContactPoint.objects.create(customer=self.customer, contact=person, kind="email", value="existing@example.invalid", normalized_value="existing@example.invalid")
        self.client.force_login(self.users["Viewer"])
        response = self.client.get(self.customer.get_absolute_url(), secure=True)
        self.assertEqual(response.context["active_service_count"], 1)
        self.assertContains(response, self.assignment_url("list"))
        self.assertContains(self.client.get(reverse("contacts:list", args=[self.customer.pk]), secure=True), "Existing Person")
        self.assertContains(self.client.get(person.get_absolute_url(), secure=True), "existing@example.invalid")
        self.assertEqual(self.client.get(reverse("customers:list"), secure=True).status_code, 200)

    def test_partial_permissions_do_not_leak_customer_usage_or_counts(self):
        user = User.objects.create_user(username="limited")
        for code, app in (("access_portal", "accounts"), ("view_service", "services")):
            user.user_permissions.add(Permission.objects.get(content_type__app_label=app, codename=code))
        self.client.force_login(user)
        response = self.client.get(self.catalog_url("detail"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.customer.name)
        self.assertEqual(self.client.get(self.assignment_url("list"), secure=True).status_code, 403)
        user.user_permissions.add(Permission.objects.get(content_type__app_label="customers", codename="view_customer"))
        response = self.client.get(self.customer.get_absolute_url(), secure=True)
        self.assertIsNone(response.context["active_service_count"])
        self.assertNotContains(response, self.assignment_url("list"))

    def test_admin_inspection_read_only_and_html_escaped(self):
        update_service(actor=self.users["Administrator"], service_id=self.service.pk, name="<script>Catalog</script>")
        update_assignment(actor=self.users["Editor"], customer_id=self.customer.pk, assignment_id=self.assignment.pk,
                          status="active", notes="<script>Notes</script>")
        self.client.force_login(self.users["Administrator"])
        self.assertContains(self.client.get(self.catalog_url("detail"), secure=True), "&lt;script&gt;Catalog&lt;/script&gt;")
        self.assertContains(self.client.get(self.assignment_url("detail"), secure=True), "&lt;script&gt;Notes&lt;/script&gt;")
        for model, pk in (("service", self.service.pk), ("customerservice", self.assignment.pk)):
            self.assertEqual(self.client.get(reverse(f"admin:services_{model}_change", args=[pk]), secure=True).status_code, 200)
            self.assertEqual(self.client.post(reverse(f"admin:services_{model}_change", args=[pk]), {}, secure=True).status_code, 403)
            self.assertEqual(self.client.get(reverse(f"admin:services_{model}_delete", args=[pk]), secure=True).status_code, 403)
            self.assertEqual(self.client.get(reverse(f"admin:services_{model}_add"), secure=True).status_code, 403)


class ServiceSearchTests(ServiceFixtures):
    def setUp(self):
        self.client.force_login(self.users["Viewer"])

    def test_catalog_name_description_category_and_status_filters(self):
        for q in ("MONITOR", "insights", "operations"):
            response = self.client.get(self.catalog_url("list"), {"q": q}, secure=True)
            self.assertEqual(list(response.context["page_obj"]), [self.service])
        set_service_active(actor=self.users["Administrator"], service_id=self.service.pk, is_active=False)
        response = self.client.get(self.catalog_url("list"), {"status": "archived", "category": "operations"}, secure=True)
        self.assertEqual(list(response.context["page_obj"]), [self.service])
        response = self.client.get(self.catalog_url("list"), {"status": "active"}, secure=True)
        self.assertEqual(list(response.context["page_obj"]), [self.other_service])
        self.assertEqual(self.client.get(self.catalog_url("list"), secure=True).context["page_obj"].paginator.count, 2)

    def test_catalog_pagination_preserves_filters(self):
        Service.objects.bulk_create([Service(name=f"Example {i:02}", category="Test") for i in range(28)])
        response = self.client.get(self.catalog_url("list"), {"q": "Example", "category": "Test", "status": "active"}, secure=True)
        self.assertEqual(len(response.context["page_obj"]), 25)
        self.assertContains(response, "q=Example&amp;status=active&amp;category=Test&amp;page=2")
        response = self.client.get(self.catalog_url("list"), {"q": "Example", "page": 2}, secure=True)
        self.assertEqual(len(response.context["page_obj"]), 3)

    def test_assignment_filter_customer_scope_and_catalog_usage(self):
        suspended = self.assign(status="suspended")
        self.assign(customer_id=self.other_customer.pk)
        self.assign(service_id=self.other_service.pk)
        response = self.client.get(self.assignment_url("list"), {"status": "suspended"}, secure=True)
        self.assertEqual(list(response.context["page_obj"]), [suspended])
        response = self.client.get(self.catalog_url("detail"), secure=True)
        self.assertEqual(response.context["page_obj"].paginator.count, 3)
        self.assertContains(response, self.other_customer.name)
        self.assertContains(response, self.customer.name)
        terminate_assignment(actor=self.users["Editor"], customer_id=self.customer.pk, assignment_id=self.assignment.pk)
        self.assertContains(self.client.get(self.catalog_url("detail"), secure=True), "Terminated")

    def test_assignment_and_usage_pagination(self):
        CustomerService.objects.bulk_create([CustomerService(customer=self.customer, service=self.service) for _ in range(26)])
        for url in (self.assignment_url("list"), self.catalog_url("detail")):
            response = self.client.get(url, {"page": 2}, secure=True)
            self.assertEqual(len(response.context["page_obj"]), 2)
            self.assertEqual(response.context["page_obj"].paginator.count, 27)

    def test_invalid_filters_rejected(self):
        for query in ({"status": "invalid"}, {"q": "x" * 201}, {"category": "x" * 101}):
            self.assertEqual(self.client.get(self.catalog_url("list"), query, secure=True).status_code, 400)
        self.assertEqual(self.client.get(self.assignment_url("list"), {"status": "invalid"}, secure=True).status_code, 400)


class CatalogConcurrencyTests(TransactionTestCase):
    def test_concurrent_case_insensitive_names_return_validation_error(self):
        call_command("setup_roles", verbosity=0)
        actor = User.objects.create_user(username="concurrency")
        actor.groups.add(Group.objects.get(name="Administrator"))
        barrier = Barrier(2)
        original_clean = Service.full_clean

        def clean_and_wait(instance, *args, **kwargs):
            original_clean(instance, *args, **kwargs)
            barrier.wait(timeout=10)

        def create(name):
            close_old_connections()
            try:
                try:
                    create_service(actor=User.objects.get(pk=actor.pk), name=name)
                    return "created"
                except ValidationError:
                    return "validation"
            finally:
                close_old_connections()

        with patch.object(Service, "full_clean", clean_and_wait), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, ["Concurrent", "CONCURRENT"]))
        self.assertCountEqual(results, ["created", "validation"])
        self.assertEqual(Service.objects.count(), 1)
