from datetime import datetime, timezone
from unittest.mock import patch
import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from apps.customers.models import Customer
from apps.customers.services import create_customer, update_customer, archive_customer
from apps.contacts.models import Contact, ContactPoint
from apps.contacts.services import create_contact, update_contact, set_contact_active, save_contact_point, set_point_active
from apps.services.models import Service, CustomerService
from apps.services.services import create_service, update_service, set_service_active, create_assignment, update_assignment, terminate_assignment
from .models import AuditEvent
from .services import record_change, snapshot

User = get_user_model()


class AuditFixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.users = {}
        for role in ("Viewer", "Editor", "Administrator"):
            user = User.objects.create_user(username=role.lower())
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.editor, cls.admin = cls.users["Editor"], cls.users["Administrator"]
        cls.customer = create_customer(actor=cls.editor, name="Private customer", notes="Secret customer note")
        cls.person = create_contact(actor=cls.editor, customer_id=cls.customer.pk, full_name="Private person", job_title="Operator")
        cls.point = save_contact_point(actor=cls.editor, customer_id=cls.customer.pk, contact_id=cls.person.pk,
                                      kind="email", value="private@example.invalid", is_primary=True)
        cls.service = create_service(actor=cls.admin, name="Private service", description="Private description")
        cls.assignment = create_assignment(actor=cls.editor, customer_id=cls.customer.pk, service_id=cls.service.pk)

    def change_customer(self, **kwargs):
        return update_customer(actor=self.editor, customer_id=self.customer.pk, **{
            "name": self.customer.name, "reference_code": "", "status": "active", "address": "", "notes": self.customer.notes, **kwargs})

    def events(self, record):
        return AuditEvent.objects.filter(object_id=record.pk).order_by("created_at", "id")

    def activity_url(self):
        return reverse("customer_activity:list", args=[self.customer.pk])


class AuditRecordingTests(AuditFixtures):
    def test_creation_identifiers_actor_customer_and_safe_metadata(self):
        self.assertEqual(AuditEvent.objects.count(), 6)
        for instance, object_type, actor in ((self.customer, "customer", self.editor), (self.person, "contact", self.editor),
                                           (self.point, "contact_point", self.editor), (self.service, "service", self.admin),
                                           (self.assignment, "customer_service", self.editor)):
            event = self.events(instance).get()
            self.assertEqual(event.actor_id, actor.pk)
            self.assertEqual(event.object_type, object_type)
            self.assertEqual(event.customer_id, None if object_type == "service" else self.customer.pk)
            self.assertEqual(event.action, "assigned" if object_type == "customer_service" else "created")
            self.assertIsNotNone(event.created_at.tzinfo)
            self.assertEqual(set(event.changed_fields), set(snapshot(instance)))
        stored = json.dumps(list(AuditEvent.objects.values()), default=str)
        for private in ("Private customer", "Secret customer note", "Private person", "private@example.invalid", "Private service", "Private description"):
            self.assertNotIn(private, stored)
        for secret_field in ("password", "session", "token", "normalized_value"):
            self.assertNotIn(secret_field, stored)

    def test_customer_create_edit_archive_restore_fields(self):
        self.change_customer(name="Changed", notes="Changed private note")
        event = self.events(self.customer).last()
        self.assertEqual(event.changed_fields, ["name", "notes"])
        self.assertEqual(event.description, "Customer updated.")
        archive_customer(actor=self.editor, customer_id=self.customer.pk)
        self.change_customer()
        self.assertEqual(list(self.events(self.customer).values_list("action", flat=True)), ["created", "updated", "archived", "restored"])
        self.change_customer(status="inactive")
        self.assertEqual(self.events(self.customer).last().action, "archived")

    def test_contact_edit_archive_restore(self):
        update_contact(actor=self.editor, customer_id=self.customer.pk, contact_id=self.person.pk,
                       full_name=self.person.full_name, job_title="Manager", department="Ops")
        self.assertEqual(self.events(self.person).last().changed_fields, ["department", "job_title"])
        for active in (False, True):
            set_contact_active(actor=self.editor, customer_id=self.customer.pk, contact_id=self.person.pk, is_active=active)
        self.assertEqual(list(self.events(self.person).values_list("action", flat=True)), ["created", "updated", "archived", "restored"])

    def test_person_and_general_details_changes_and_primary_demotion(self):
        second = save_contact_point(actor=self.editor, customer_id=self.customer.pk, contact_id=self.person.pk,
                                    kind="email", value="second@example.invalid", is_primary=True)
        self.assertEqual(self.events(self.point).last().changed_fields, ["is_primary"])
        self.assertEqual(self.events(self.point).last().actor, self.editor)
        desk = create_contact(actor=self.editor, customer_id=self.customer.pk, full_name="Support Desk", is_general=True)
        general = save_contact_point(actor=self.editor, customer_id=self.customer.pk, contact_id=desk.pk,
                                     kind="phone", value="+45 12 34 56 78")
        save_contact_point(actor=self.editor, customer_id=self.customer.pk, contact_id=desk.pk,
                           point_id=general.pk, kind="phone", value="+45 87 65 43 21", label="work")
        self.assertEqual(self.events(general).last().changed_fields, ["label", "value"])
        for active in (False, True):
            set_point_active(actor=self.editor, customer_id=self.customer.pk, contact_id=self.person.pk, point_id=second.pk, is_active=active)
        self.assertEqual(list(self.events(second).values_list("action", flat=True)), ["created", "archived", "restored"])
        self.assertNotIn("87654321", json.dumps(list(AuditEvent.objects.values()), default=str))

    def test_catalog_and_assignment_lifecycles(self):
        update_service(actor=self.admin, service_id=self.service.pk, name=self.service.name, description="Updated")
        for active in (False, True):
            set_service_active(actor=self.admin, service_id=self.service.pk, is_active=active)
        self.assertEqual(list(self.events(self.service).values_list("action", flat=True)), ["created", "updated", "archived", "restored"])
        for status in ("active", "suspended", "expired", "active"):
            update_assignment(actor=self.editor, customer_id=self.customer.pk, assignment_id=self.assignment.pk, status=status, notes="Changed note")
        terminate_assignment(actor=self.editor, customer_id=self.customer.pk, assignment_id=self.assignment.pk)
        self.assertEqual(list(self.events(self.assignment).values_list("action", flat=True)), ["assigned", "updated", "suspended", "expired", "activated", "terminated"])
        self.assertEqual(self.events(self.assignment).last().changed_fields, ["status"])

    def test_noop_edits_and_repeated_archive_do_not_create_events(self):
        before = AuditEvent.objects.count()
        self.change_customer()
        update_contact(actor=self.editor, customer_id=self.customer.pk, contact_id=self.person.pk, full_name=self.person.full_name, job_title=self.person.job_title)
        update_service(actor=self.admin, service_id=self.service.pk, name=self.service.name, description=self.service.description)
        update_assignment(actor=self.editor, customer_id=self.customer.pk, assignment_id=self.assignment.pk, status="active")
        self.assertEqual(AuditEvent.objects.count(), before)
        archive_customer(actor=self.editor, customer_id=self.customer.pk)
        archive_customer(actor=self.editor, customer_id=self.customer.pk)
        self.assertEqual(AuditEvent.objects.count(), before + 1)

    def test_invalid_or_unauthorized_changes_do_not_record_success(self):
        count = AuditEvent.objects.count()
        with self.assertRaises(ValidationError):
            self.change_customer(name=" ")
        with self.assertRaises(PermissionDenied):
            archive_customer(actor=self.users["Viewer"], customer_id=self.customer.pk)
        with self.assertRaises(ValidationError):
            create_assignment(actor=self.editor, customer_id=self.customer.pk, service_id=self.service.pk, status="invalid")
        self.assertEqual(AuditEvent.objects.count(), count)

    def test_audit_failure_rolls_back_every_creation_type(self):
        operations = [
            lambda: create_customer(actor=self.editor, name="Rollback"),
            lambda: create_contact(actor=self.editor, customer_id=self.customer.pk, full_name="Rollback"),
            lambda: save_contact_point(actor=self.editor, customer_id=self.customer.pk,
                                       contact_id=self.person.pk, kind="phone", value="12345678"),
            lambda: create_service(actor=self.admin, name="Rollback"),
            lambda: create_assignment(actor=self.editor, customer_id=self.customer.pk, service_id=self.service.pk),
        ]
        models = (Customer, Contact, ContactPoint, Service, CustomerService, AuditEvent)
        counts = [model.objects.count() for model in models]
        for operation in operations:
            with self.subTest(operation=operation), patch("apps.audit.services.AuditEvent.objects.create", side_effect=RuntimeError("Audit unavailable")):
                with self.assertRaises(RuntimeError):
                    operation()
            self.assertEqual([model.objects.count() for model in models], counts)

    def test_audit_failure_rolls_back_updates_and_archive_for_every_type(self):
        operations = [
            lambda: self.change_customer(name="Rollback"),
            lambda: archive_customer(actor=self.editor, customer_id=self.customer.pk),
            lambda: update_contact(actor=self.editor, customer_id=self.customer.pk, contact_id=self.person.pk, full_name="Rollback"),
            lambda: set_contact_active(actor=self.editor, customer_id=self.customer.pk, contact_id=self.person.pk, is_active=False),
            lambda: save_contact_point(actor=self.editor, customer_id=self.customer.pk, contact_id=self.person.pk, point_id=self.point.pk, kind="email", value="rollback@example.invalid"),
            lambda: set_point_active(actor=self.editor, customer_id=self.customer.pk, contact_id=self.person.pk, point_id=self.point.pk, is_active=False),
            lambda: update_service(actor=self.admin, service_id=self.service.pk, name="Rollback"),
            lambda: set_service_active(actor=self.admin, service_id=self.service.pk, is_active=False),
            lambda: update_assignment(actor=self.editor, customer_id=self.customer.pk, assignment_id=self.assignment.pk, status="suspended"),
            lambda: terminate_assignment(actor=self.editor, customer_id=self.customer.pk, assignment_id=self.assignment.pk),
        ]
        models = (Customer, Contact, ContactPoint, Service, CustomerService, AuditEvent)
        before = [list(model.objects.order_by("pk").values()) for model in models]
        for operation in operations:
            with patch("apps.audit.services.AuditEvent.objects.create", side_effect=RuntimeError("Audit unavailable")):
                with self.assertRaises(RuntimeError):
                    operation()
            self.assertEqual([list(model.objects.order_by("pk").values()) for model in models], before)

    def test_primary_change_failure_rolls_back_demotion_and_its_event(self):
        original_create = AuditEvent.objects.create
        def fail_new_point(**kwargs):
            if kwargs["action"] == "created":
                raise RuntimeError("Audit unavailable")
            return original_create(**kwargs)
        count = AuditEvent.objects.count()
        with patch("apps.audit.services.AuditEvent.objects.create", side_effect=fail_new_point), self.assertRaises(RuntimeError):
            save_contact_point(actor=self.editor, customer_id=self.customer.pk, contact_id=self.person.pk,
                               kind="email", value="rollback@example.invalid", is_primary=True)
        self.point.refresh_from_db()
        self.assertTrue(self.point.is_primary)
        self.assertEqual(ContactPoint.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.count(), count)

    def test_outer_transaction_failure_rolls_back_business_and_event(self):
        before = (Customer.objects.count(), AuditEvent.objects.count())
        with self.assertRaises(RuntimeError), transaction.atomic():
            create_customer(actor=self.editor, name="Rollback outer")
            raise RuntimeError("Outer operation failed")
        self.assertEqual((Customer.objects.count(), AuditEvent.objects.count()), before)

    def test_events_survive_archive_and_cannot_be_edited_or_deleted(self):
        event = self.events(self.customer).get()
        archive_customer(actor=self.editor, customer_id=self.customer.pk)
        self.assertTrue(AuditEvent.objects.filter(pk=event.pk).exists())
        for operation in (lambda: event.save(), lambda: event.delete(), lambda: AuditEvent.objects.filter(pk=event.pk).update(description="Forged"),
                          lambda: AuditEvent.objects.filter(pk=event.pk).delete(), lambda: AuditEvent.objects.bulk_update([event], ["description"])):
            with self.assertRaises(ValidationError):
                operation()
        for record in (self.customer, self.editor):
            with self.assertRaises(ProtectedError):
                record.delete()

    def test_database_checks_reject_invalid_action_type_or_customer_scope(self):
        base = dict(actor=self.editor, action="updated", object_type="customer", object_id=self.customer.pk,
                    customer=self.customer, description="Customer updated.", changed_fields=["name"])
        for invalid in ({"action": "invalid"}, {"object_type": "password"}, {"customer": None}, {"object_type": "service"}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                AuditEvent.objects.create(**{**base, **invalid})

    def test_new_instance_cannot_overwrite_existing_event_uuid(self):
        event = self.events(self.customer).get()
        row = AuditEvent.objects.values().get(pk=event.pk)
        replacement = AuditEvent(**{**row, "description": "Forged"})
        with self.assertRaises(IntegrityError), transaction.atomic():
            replacement.save()
        self.assertEqual(AuditEvent.objects.values().get(pk=event.pk), row)


class AuditViewTests(AuditFixtures):
    def test_authentication_global_role_gates_and_customer_access(self):
        for url in (reverse("audit:history"), self.activity_url()):
            self.assertEqual(self.client.get(url, secure=True).status_code, 302)
        for role in self.users:
            self.client.force_login(self.users[role])
            response = self.client.get(reverse("audit:history"), secure=True)
            self.assertEqual(response.status_code, 200 if role == "Administrator" else 403)
            response = self.client.get(self.activity_url(), secure=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn("no-store", response["Cache-Control"])
            self.assertNotContains(response, "Private service")
            self.assertNotContains(response, "private@example.invalid")
            self.assertNotContains(response, "Secret customer note")
            self.assertContains(response, "UTC")
        user = User.objects.create_user(username="no_customer")
        for app, codename in (("accounts", "access_portal"), ("audit", "view_customer_activity"), ("audit", "view_auditevent")):
            user.user_permissions.add(Permission.objects.get(content_type__app_label=app, codename=codename))
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.activity_url(), secure=True).status_code, 403)
        self.assertEqual(self.client.get(reverse("audit:history"), secure=True).status_code, 403)

    def test_partial_permissions_filter_events_and_actor_choices(self):
        user = User.objects.create_user(username="customer_reader")
        for app, codename in (("accounts", "access_portal"), ("customers", "view_customer"), ("audit", "view_customer_activity")):
            user.user_permissions.add(Permission.objects.get(content_type__app_label=app, codename=codename))
        other = create_customer(actor=self.admin, name="Other customer")
        self.client.force_login(user)
        response = self.client.get(self.activity_url(), secure=True)
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertNotContains(response, str(self.person.pk))
        self.assertNotContains(response, str(self.assignment.pk))
        self.assertNotContains(response, other.name)
        self.assertEqual(list(response.context["filter_form"].fields["actor"].queryset), [self.editor])

    def test_global_read_permission_does_not_bypass_business_permissions(self):
        user = User.objects.create_user(username="catalog_auditor")
        for app, code in (("accounts", "access_portal"), ("accounts", "administer_portal"), ("audit", "view_auditevent"), ("services", "view_service")):
            user.user_permissions.add(Permission.objects.get(content_type__app_label=app, codename=code))
        self.client.force_login(user)
        response = self.client.get(reverse("audit:history"), secure=True)
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertNotContains(response, self.customer.name)

    def test_filters_utc_inclusive_dates_actor_action_and_validation(self):
        with patch("django.utils.timezone.now", return_value=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)):
            self.change_customer(name="First")
        with patch("django.utils.timezone.now", return_value=datetime(2025, 1, 1, 23, 59, 59, tzinfo=timezone.utc)):
            self.change_customer(name="Second")
        with patch("django.utils.timezone.now", return_value=datetime(2025, 1, 2, 0, 0, tzinfo=timezone.utc)):
            self.change_customer(name="Third")
        self.client.force_login(self.admin)
        params = {"date_from": "2025-01-01", "date_to": "2025-01-01", "actor": self.editor.pk, "action": "updated"}
        response = self.client.get(self.activity_url(), params, secure=True)
        self.assertEqual(response.context["page_obj"].paginator.count, 2)
        self.assertContains(response, "2025-01-01 23:59:59")
        for invalid in ({"date_from": "wrong"}, {"date_from": "2025-02-01", "date_to": "2025-01-01"}, {"action": "wrong"}, {"actor": 999999}):
            self.assertEqual(self.client.get(self.activity_url(), invalid, secure=True).status_code, 400)

    def test_newest_first_pagination_preserves_filters_and_empty_state(self):
        for i in range(27):
            self.change_customer(name=f"Change {i}")
        self.client.force_login(self.admin)
        response = self.client.get(self.activity_url(), {"action": "updated"}, secure=True)
        self.assertEqual(len(response.context["page_obj"]), 25)
        self.assertContains(response, "action=updated&amp;page=2")
        self.assertEqual(response.context["page_obj"][0].pk, self.events(self.customer).last().pk)
        self.assertEqual(len(self.client.get(self.activity_url(), {"action": "updated", "page": 2}, secure=True).context["page_obj"]), 2)
        self.assertContains(self.client.get(self.activity_url(), {"action": "expired"}, secure=True), "No activity found")

    def test_history_routes_and_admin_are_read_only_even_for_admin(self):
        self.client.force_login(self.admin)
        event = self.events(self.customer).get()
        for url in (self.activity_url(), reverse("audit:history")):
            for method in (self.client.post, self.client.put, self.client.delete):
                self.assertEqual(method(url, secure=True).status_code, 405)
        self.assertEqual(self.client.get(reverse("admin:audit_auditevent_change", args=[event.pk]), secure=True).status_code, 200)
        for action in ("change", "delete"):
            self.assertEqual(self.client.post(reverse(f"admin:audit_auditevent_{action}", args=[event.pk]), {}, secure=True).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:audit_auditevent_add"), secure=True).status_code, 403)
        self.assertEqual(self.client.get(f"/audit/{event.pk}/edit/", secure=True).status_code, 404)
        self.assertFalse(Permission.objects.filter(content_type__app_label="audit", codename__in=["add_auditevent", "change_auditevent", "delete_auditevent"]).exists())

    def test_customer_edit_archive_confirmation_is_safe(self):
        self.client.force_login(self.editor)
        url = reverse("customers:edit", args=[self.customer.pk])
        data = {"name": self.customer.name, "status": "inactive", "notes": "Retained notes", "reference_code": "", "address": ""}
        count = AuditEvent.objects.count()
        response = self.client.post(url, data, secure=True)
        self.assertContains(response, "Archive customer and save changes?")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, "active")
        self.assertEqual(AuditEvent.objects.count(), count)
        self.assertEqual(self.client.post(url, {**data, "confirm_archive": "yes"}, secure=True).status_code, 302)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, "inactive")
        self.assertEqual(self.events(self.customer).last().action, "archived")


class AuditTransactionContractTests(TransactionTestCase):
    def test_recorder_rejects_use_outside_business_transaction(self):
        with self.assertRaises(RuntimeError):
            record_change(actor=None, instance=None)
