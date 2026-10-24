from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from apps.customers.models import Customer
from apps.customers.services import archive_customer

from .forms import ContactForm, ContactPointForm
from .models import Contact, ContactPoint
from .selectors import directory_results
from .services import create_contact, update_contact, set_contact_active, save_contact_point, set_point_active
from .validation import normalize_contact_value

User = get_user_model()


class ContactFixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.users = {}
        for role in ("Viewer", "Editor", "Administrator"):
            actor = User.objects.create_user(username=role.lower())
            actor.groups.add(Group.objects.get(name=role))
            cls.users[role] = actor
        cls.customer = Customer.objects.create(name="Synthetic Alpha")
        cls.other_customer = Customer.objects.create(name="Synthetic Beta")
        cls.person = create_contact(actor=cls.users["Editor"], customer_id=cls.customer.pk, full_name="Alice Example")
        cls.second_person = create_contact(actor=cls.users["Editor"], customer_id=cls.customer.pk, full_name="Bob Example")
        cls.foreign_person = create_contact(actor=cls.users["Editor"], customer_id=cls.other_customer.pk, full_name="Foreign Example")
        cls.email = save_contact_point(actor=cls.users["Editor"], customer_id=cls.customer.pk,
                                      contact_id=cls.person.pk, kind="email", value="alice@example.invalid", is_primary=True)
        cls.general = save_contact_point(actor=cls.users["Editor"], customer_id=cls.customer.pk,
                                        kind="phone", value="+45 12 34 56 78", is_primary=True)

    def point(self, **changes):
        return save_contact_point(**{
            "actor": self.users["Editor"], "customer_id": self.customer.pk, "contact_id": self.person.pk,
            "kind": "email", "value": "second@example.invalid", **changes,
        })

    def point_payload(self, **changes):
        return {"kind": "email", "label": "work", "value": "new@example.invalid", **changes}

    def route(self, name):
        args = [self.customer.pk]
        if name in ("detail", "edit", "archive", "restore", "point_create", "point_edit", "point_archive", "point_restore"):
            args.append(self.person.pk)
        if name in ("point_edit", "point_archive", "point_restore"):
            args.append(self.email.pk)
        if name in ("general_edit", "general_archive", "general_restore"):
            args.append(self.general.pk)
        return reverse(f"contacts:{name}", args=args)


class ContactModelTests(ContactFixtures):
    def test_name_only_and_optional_fields(self):
        form = ContactForm({"full_name": "  Minimal Person  "}, instance=Contact(customer=self.customer))
        self.assertTrue(form.is_valid(), form.errors)
        person = create_contact(actor=self.users["Editor"], customer_id=self.customer.pk, **form.cleaned_data)
        self.assertEqual(person.full_name, "Minimal Person")
        self.assertEqual(person.contact_type, "other")
        self.assertEqual(person.department, "")
        self.assertTrue(person.is_active)
        self.assertFalse(person.points.exists())
        self.assertIsInstance(person.pk, uuid.UUID)
        self.assertIsNotNone(person.created_at)

    def test_contact_field_validation(self):
        for invalid in ({"full_name": " \n "}, {"full_name": "x" * 201}, {"contact_type": "unknown"},
                        {"job_title": "x" * 201}, {"department": "x" * 201}, {"notes": "x" * 10001}):
            with self.subTest(fields=list(invalid)), self.assertRaises(ValidationError):
                create_contact(actor=self.users["Editor"], customer_id=self.customer.pk, **{"full_name": "Valid", **invalid})
        self.assertEqual(Contact.objects.count(), 3)

    def test_all_requested_types_and_metadata(self):
        for contact_type in ("technical", "management", "billing", "support", "other"):
            person = create_contact(actor=self.users["Editor"], customer_id=self.customer.pk, full_name="Example",
                                    contact_type=contact_type, department="Operations", job_title="Manager", notes="Synthetic notes")
            self.assertEqual(person.department, "Operations")
            self.assertEqual(person.contact_type, contact_type)

    def test_database_name_and_type_constraints(self):
        for data in ({"full_name": " \t "}, {"full_name": "Name", "contact_type": "invalid"}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                Contact.objects.create(customer=self.customer, **data)

    def test_model_and_database_reject_mismatched_customer(self):
        point = ContactPoint(customer=self.other_customer, contact=self.person, kind="email", value="mismatch@example.invalid")
        with self.assertRaises(ValidationError):
            point.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContactPoint.objects.create(customer=self.other_customer, contact=self.person, kind="email",
                                        value="mismatch@example.invalid", normalized_value="mismatch@example.invalid")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Contact.objects.filter(pk=self.person.pk).update(customer=self.other_customer)

    def test_owners_are_immutable_and_protected(self):
        self.person.customer = self.other_customer
        with self.assertRaises(ValidationError):
            self.person.full_clean()
        self.email.contact = self.second_person
        with self.assertRaises(ValidationError):
            self.email.full_clean()
        with self.assertRaises(ProtectedError):
            self.customer.delete()
        with self.assertRaises(ProtectedError):
            Contact.objects.get(pk=self.person.pk).delete()

    def test_general_points_are_not_assigned_to_person(self):
        self.assertIsNone(self.general.contact_id)
        self.assertEqual(self.general.customer_id, self.customer.pk)
        self.assertEqual(self.person.points.count(), 1)

    def test_email_and_danish_international_phone_normalization(self):
        self.assertEqual(self.point(value=" Alice.Work@Example.Invalid ").normalized_value, "alice.work@example.invalid")
        for raw, expected in (("12 34 56 78", "12345678"), ("+45 12-34-56-78", "4512345678"),
                              ("0045 12345678", "4512345678"), ("+44 (20) 7946 0958", "442079460958")):
            point = self.point(kind="phone", value=raw)
            self.assertEqual(point.value, raw)
            self.assertEqual(point.normalized_value, expected)

    def test_invalid_emails_and_phones(self):
        for kind, value in (("email", "not-an-email"), ("email", "a@example.invalid\nBcc: x"),
                            ("phone", "123"), ("phone", "+1234567890123456"), ("phone", "call me"),
                            ("phone", "12+345678"), ("phone", "12345678 ext 9"), ("email", "")):
            with self.subTest(kind=kind), self.assertRaises(ValidationError):
                self.point(kind=kind, value=value)

    def test_detail_form_validates_owner_and_values(self):
        valid = ContactPointForm(self.point_payload(value=" test@example.invalid "), customer=self.customer, contact=self.person)
        self.assertTrue(valid.is_valid(), valid.errors)
        invalid = ContactPointForm(self.point_payload(), customer=self.other_customer, contact=self.person)
        self.assertFalse(invalid.is_valid())
        for changes in ({"value": "not an email"}, {"label": "invalid"}, {"kind": "fax"}):
            self.assertFalse(ContactPointForm(self.point_payload(**changes), customer=self.customer, contact=self.person).is_valid())

    def test_database_point_constraints(self):
        for changes in ({"kind": "fax"}, {"label": "wrong"}, {"value": " "}, {"normalized_value": ""}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                ContactPoint.objects.create(**{"customer": self.customer, "kind": "email", "value": "test@example.invalid",
                                              "normalized_value": "test@example.invalid", **changes})

    def test_string_representation_does_not_contain_contact_values(self):
        self.assertNotIn(self.email.value, str(self.email))
        self.assertNotIn(self.person.full_name, str(self.person))


class ContactServiceTests(ContactFixtures):
    def test_multiple_emails_and_phones_with_primary_switching(self):
        secondary = self.point()
        primary = self.point(value="primary@example.invalid", is_primary=True)
        first_phone = self.point(kind="phone", value="+45 11 22 33 44", is_primary=True, label="work")
        second_phone = self.point(kind="phone", value="+45 55 66 77 88", label="mobile")
        self.email.refresh_from_db()
        self.assertFalse(self.email.is_primary)
        self.assertFalse(secondary.is_primary)
        self.assertTrue(primary.is_primary)
        self.assertTrue(first_phone.is_primary)
        self.assertFalse(second_phone.is_primary)
        self.assertEqual(self.person.points.count(), 5)
        self.assertEqual(self.person.points.filter(kind="email", is_primary=True).count(), 1)
        self.assertEqual(self.person.points.filter(kind="phone", is_primary=True).count(), 1)

    def test_database_rejects_two_primary_details_for_each_owner_kind(self):
        for owner in ({"contact": self.person, "kind": "email", "value": "other@example.invalid"},
                      {"contact": None, "kind": "phone", "value": "+45 99 88 77 66"}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                ContactPoint.objects.create(customer=self.customer, normalized_value="synthetic", is_primary=True, **owner)

    def test_general_and_person_primary_are_independent(self):
        general_email = self.point(contact_id=None, is_primary=True)
        bob_email = self.point(contact_id=self.second_person.pk, is_primary=True)
        other = self.point(customer_id=self.other_customer.pk, contact_id=self.foreign_person.pk, is_primary=True)
        self.email.refresh_from_db()
        self.assertTrue(all(point.is_primary for point in (self.email, general_email, bob_email, other)))
        self.point(contact_id=None, value="replacement@example.invalid", is_primary=True)
        general_email.refresh_from_db()
        self.assertFalse(general_email.is_primary)
        self.email.refresh_from_db()
        self.assertTrue(self.email.is_primary)

    def test_invalid_primary_change_rolls_back(self):
        with self.assertRaises(ValidationError):
            self.point(value="invalid", is_primary=True)
        self.email.refresh_from_db()
        self.assertTrue(self.email.is_primary)
        self.assertEqual(self.person.points.count(), 1)

    def test_point_edit_kind_and_primary_transitions(self):
        phone = self.point(kind="phone", value="12345678", is_primary=True)
        edited = self.point(point_id=self.email.pk, kind="phone", value="87654321", is_primary=True)
        phone.refresh_from_db()
        self.assertFalse(phone.is_primary)
        self.assertEqual(edited.kind, "phone")
        self.assertEqual(edited.pk, self.email.pk)
        self.assertEqual(edited.created_at, self.email.created_at)

    def test_archiving_and_restoring_contact_preserves_details(self):
        before = list(self.person.points.values())
        archived = set_contact_active(actor=self.users["Editor"], customer_id=self.customer.pk, contact_id=self.person.pk, is_active=False)
        self.assertFalse(archived.is_active)
        self.assertEqual(list(self.person.points.values()), before)
        again = set_contact_active(actor=self.users["Editor"], customer_id=self.customer.pk, contact_id=self.person.pk, is_active=False)
        self.assertEqual(again.updated_at, archived.updated_at)
        restored = set_contact_active(actor=self.users["Editor"], customer_id=self.customer.pk, contact_id=self.person.pk, is_active=True)
        self.assertTrue(restored.is_active)
        self.assertEqual(restored.created_at, self.person.created_at)
        self.assertEqual(list(self.person.points.values()), before)

    def test_detail_archive_restore_preserves_value_and_clears_primary(self):
        point = set_point_active(actor=self.users["Editor"], customer_id=self.customer.pk, contact_id=self.person.pk,
                                 point_id=self.email.pk, is_active=False)
        self.assertFalse(point.is_active)
        self.assertFalse(point.is_primary)
        self.assertEqual(point.value, self.email.value)
        self.point(value="current@example.invalid", is_primary=True)
        point = set_point_active(actor=self.users["Editor"], customer_id=self.customer.pk, contact_id=self.person.pk,
                                 point_id=self.email.pk, is_active=True)
        self.assertTrue(point.is_active)
        self.assertFalse(point.is_primary)

    def test_customer_archive_does_not_erase_contacts(self):
        archive_customer(actor=self.users["Editor"], customer_id=self.customer.pk)
        self.person.refresh_from_db()
        self.assertTrue(self.person.is_active)
        self.assertEqual(self.person.points.count(), 1)

    def test_cross_customer_and_cross_person_service_calls_refused(self):
        operations = [
            lambda: self.point(contact_id=self.foreign_person.pk),
            lambda: self.point(point_id=self.email.pk, contact_id=self.second_person.pk),
            lambda: self.point(point_id=self.email.pk, contact_id=None),
            lambda: update_contact(actor=self.users["Editor"], customer_id=self.other_customer.pk, contact_id=self.person.pk, full_name="Changed"),
            lambda: set_contact_active(actor=self.users["Editor"], customer_id=self.other_customer.pk, contact_id=self.person.pk, is_active=False),
            lambda: set_point_active(actor=self.users["Editor"], customer_id=self.customer.pk, contact_id=None, point_id=self.email.pk, is_active=False),
        ]
        for operation in operations:
            with self.assertRaises(ValidationError):
                operation()
        self.person.refresh_from_db()
        self.assertEqual(self.person.full_name, "Alice Example")
        self.assertTrue(self.person.is_active)

    def test_service_permissions_and_no_delete_grants(self):
        inactive = User.objects.create_user(username="inactive", is_active=False)
        inactive.groups.add(Group.objects.get(name="Administrator"))
        actors = [self.users["Viewer"], AnonymousUser(), inactive, User.objects.create_user(username="no-role")]
        for actor in actors:
            for action in (
                lambda: create_contact(actor=actor, customer_id=self.customer.pk, full_name="Unauthorized"),
                lambda: update_contact(actor=actor, customer_id=self.customer.pk, contact_id=self.person.pk, full_name="Unauthorized"),
                lambda: set_contact_active(actor=actor, customer_id=self.customer.pk, contact_id=self.person.pk, is_active=False),
                lambda: self.point(actor=actor),
                lambda: self.point(actor=actor, point_id=self.email.pk),
                lambda: set_point_active(actor=actor, customer_id=self.customer.pk, contact_id=self.person.pk, point_id=self.email.pk, is_active=False),
            ):
                with self.assertRaises(PermissionDenied):
                    action()
        for actor in self.users.values():
            self.assertFalse(actor.has_perm("contacts.delete_contact"))
            self.assertFalse(actor.has_perm("contacts.delete_contactpoint"))

    def test_individual_grants_required_and_primary_demotion_needs_change(self):
        grants = ["accounts.access_portal", "accounts.edit_portal", "customers.view_customer",
                  "contacts.view_contact", "contacts.view_contactpoint", "contacts.add_contactpoint"]
        actor = User.objects.create_user(username="granular")
        for missing in grants:
            permissions = []
            for name in grants:
                if name != missing:
                    app, code = name.split(".")
                    permissions.append(Permission.objects.get(content_type__app_label=app, codename=code))
            actor.user_permissions.set(permissions)
            with self.assertRaises(PermissionDenied):
                self.point(actor=User.objects.get(pk=actor.pk))
        actor.user_permissions.add(Permission.objects.get(content_type__app_label="contacts", codename="add_contactpoint"))
        self.point(actor=User.objects.get(pk=actor.pk))  # add-only can add a secondary
        with self.assertRaises(PermissionDenied):
            self.point(actor=User.objects.get(pk=actor.pk), is_primary=True)
        self.email.refresh_from_db()
        self.assertTrue(self.email.is_primary)


class ContactViewTests(ContactFixtures):
    read_routes = ("list", "detail")
    write_routes = ("create", "edit", "archive", "restore", "point_create", "point_edit", "point_archive", "point_restore",
                    "general_create", "general_edit", "general_archive", "general_restore")

    def test_every_route_requires_authentication(self):
        for name in (*self.read_routes, *self.write_routes):
            for method in (self.client.get, self.client.post):
                response = method(self.route(name), secure=True)
                self.assertEqual(response.status_code, 302, name)
                self.assertTrue(response["Location"].startswith("/accounts/login/"))

    def test_viewer_reads_and_all_direct_writes_are_denied(self):
        self.client.force_login(self.users["Viewer"])
        for name in self.read_routes:
            response = self.client.get(self.route(name), secure=True)
            self.assertContains(response, "Alice Example")
            self.assertContains(response, self.email.value)
            self.assertIn("no-store", response["Cache-Control"])
            for control in ("Add contact</a>", "Edit contact</a>", "Archive contact</a>", "Add email or phone</a>"):
                self.assertNotContains(response, control)
        for name in self.write_routes:
            self.assertEqual(self.client.get(self.route(name), secure=True).status_code, 403, name)
            self.assertEqual(self.client.post(self.route(name), {"full_name": "Forged", **self.point_payload()}, secure=True).status_code, 403, name)
        self.assertEqual(Contact.objects.count(), 3)
        self.assertEqual(ContactPoint.objects.count(), 2)

    def test_unassigned_and_staff_flag_do_not_grant_access(self):
        user = User.objects.create_user(username="staff", is_staff=True)
        self.client.force_login(user)
        for name in (*self.read_routes, *self.write_routes):
            self.assertEqual(self.client.get(self.route(name), secure=True).status_code, 403)
            self.assertEqual(self.client.post(self.route(name), secure=True).status_code, 403)

    def test_editor_administrator_create_edit_details_archive_restore(self):
        for role in ("Editor", "Administrator"):
            self.client.force_login(self.users[role])
            self.assertEqual(self.client.get(self.route("create"), secure=True).status_code, 200)
            response = self.client.post(self.route("create"), {"full_name": role}, secure=True)
            person = Contact.objects.get(full_name=role)
            self.assertRedirects(response, person.get_absolute_url(), fetch_redirect_response=False)
            edit = reverse("contacts:edit", args=[self.customer.pk, person.pk])
            self.assertEqual(self.client.get(edit, secure=True).status_code, 200)
            response = self.client.post(edit, {"full_name": f"Updated {role}", "department": "Helpdesk", "contact_type": "support"}, secure=True)
            self.assertEqual(response.status_code, 302)
            person.refresh_from_db()
            self.assertEqual(person.department, "Helpdesk")
            point_url = reverse("contacts:point_create", args=[self.customer.pk, person.pk])
            for payload in (self.point_payload(value="work@example.invalid", is_primary="on"),
                            self.point_payload(value="other@example.invalid", label="other"),
                            self.point_payload(kind="phone", value="+45 12 34 56 78", label="mobile", is_primary="on"),
                            self.point_payload(kind="phone", value="+44 20 7946 0958", label="direct")):
                self.assertEqual(self.client.post(point_url, payload, secure=True).status_code, 302)
            self.assertEqual(person.points.count(), 4)
            for action, expected in (("archive", False), ("restore", True)):
                url = reverse(f"contacts:{action}", args=[self.customer.pk, person.pk])
                previous = Contact.objects.get(pk=person.pk).is_active
                self.assertEqual(self.client.get(url, secure=True).status_code, 200)
                self.assertEqual(Contact.objects.get(pk=person.pk).is_active, previous)
                self.assertEqual(self.client.post(url, secure=True).status_code, 302)
                self.assertEqual(Contact.objects.get(pk=person.pk).is_active, expected)
                self.assertEqual(person.points.count(), 4)

    def test_general_and_person_detail_forms_and_status_actions(self):
        self.client.force_login(self.users["Editor"])
        for name in ("point_create", "point_edit", "general_create", "general_edit"):
            self.assertEqual(self.client.get(self.route(name), secure=True).status_code, 200, name)
        for name in ("point_edit", "general_edit"):
            self.assertEqual(self.client.post(self.route(name), self.point_payload(value="edited@example.invalid"), secure=True).status_code, 302)
        self.email.refresh_from_db()
        self.general.refresh_from_db()
        self.assertEqual(self.email.value, "edited@example.invalid")
        self.assertIsNone(self.general.contact_id)
        for prefix, point in (("point", self.email), ("general", self.general)):
            for action, expected in (("archive", False), ("restore", True)):
                self.assertEqual(self.client.get(self.route(f"{prefix}_{action}"), secure=True).status_code, 200)
                self.assertEqual(self.client.post(self.route(f"{prefix}_{action}"), secure=True).status_code, 302)
                point.refresh_from_db()
                self.assertEqual(point.is_active, expected)

    def test_cross_customer_urls_and_cross_owner_details_are_not_found(self):
        self.client.force_login(self.users["Editor"])
        urls = []
        for name in ("detail", "edit", "archive", "restore"):
            urls.append(reverse(f"contacts:{name}", args=[self.other_customer.pk, self.person.pk]))
        for name in ("point_edit", "point_archive", "point_restore"):
            urls.append(reverse(f"contacts:{name}", args=[self.customer.pk, self.second_person.pk, self.email.pk]))
            urls.append(reverse(f"contacts:{name}", args=[self.other_customer.pk, self.person.pk, self.email.pk]))
        for name in ("general_edit", "general_archive", "general_restore"):
            urls.append(reverse(f"contacts:{name}", args=[self.customer.pk, self.email.pk]))
        for url in urls:
            self.assertEqual(self.client.get(url, secure=True).status_code, 404)
            expected_post = 405 if url == reverse("contacts:detail", args=[self.other_customer.pk, self.person.pk]) else 404
            self.assertEqual(self.client.post(url, self.point_payload(), secure=True).status_code, expected_post)

    def test_posted_owner_and_status_fields_cannot_reparent_records(self):
        self.client.force_login(self.users["Editor"])
        self.client.post(self.route("edit"), {"full_name": "Safe", "customer": self.other_customer.pk, "is_active": "False"}, secure=True)
        self.person.refresh_from_db()
        self.assertEqual(self.person.customer_id, self.customer.pk)
        self.assertTrue(self.person.is_active)
        self.client.post(self.route("point_edit"), {**self.point_payload(), "customer": self.other_customer.pk,
                                                   "contact": self.foreign_person.pk}, secure=True)
        self.email.refresh_from_db()
        self.assertEqual(self.email.customer_id, self.customer.pk)
        self.assertEqual(self.email.contact_id, self.person.pk)

    def test_invalid_forms_retain_inputs_and_do_not_write(self):
        self.client.force_login(self.users["Editor"])
        response = self.client.post(self.route("create"), {"full_name": " ", "notes": "Preserve this draft"}, secure=True)
        self.assertContains(response, "Preserve this draft")
        self.assertTrue(response.context["form"].errors)
        response = self.client.post(self.route("point_create"), self.point_payload(value="invalid email"), secure=True)
        self.assertContains(response, "invalid email")
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(Contact.objects.count(), 3)
        self.assertEqual(ContactPoint.objects.count(), 2)

    def test_csrf_required_for_every_write_route(self):
        client = Client(enforce_csrf_checks=True, HTTP_ORIGIN="https://testserver")
        client.force_login(self.users["Editor"])
        for name in self.write_routes:
            self.assertEqual(client.post(self.route(name), self.point_payload(), secure=True).status_code, 403)
        client.get(self.route("create"), secure=True)
        self.assertEqual(client.post(self.route("create"), {"full_name": "CSRF valid", "csrfmiddlewaretoken": client.cookies["csrftoken"].value}, secure=True).status_code, 302)

    def test_customer_overview_integration_and_separate_read_permissions(self):
        self.client.force_login(self.users["Viewer"])
        response = self.client.get(self.customer.get_absolute_url(), secure=True)
        self.assertContains(response, self.route("list"))
        self.assertContains(response, self.general.value)
        self.assertNotContains(response, "Foreign Example")
        user = User.objects.create_user(username="customer-only")
        for app, code in (("accounts", "access_portal"), ("customers", "view_customer")):
            user.user_permissions.add(Permission.objects.get(content_type__app_label=app, codename=code))
        self.client.force_login(user)
        response = self.client.get(self.customer.get_absolute_url(), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.general.value)
        self.assertEqual(self.client.get(self.route("list"), secure=True).status_code, 403)

    def test_contact_content_is_escaped(self):
        person = create_contact(actor=self.users["Editor"], customer_id=self.customer.pk, full_name="<b>Example</b>", notes="<script>synthetic()</script>")
        self.client.force_login(self.users["Viewer"])
        response = self.client.get(person.get_absolute_url(), secure=True)
        self.assertContains(response, "&lt;b&gt;Example&lt;/b&gt;")
        self.assertContains(response, "&lt;script&gt;synthetic()&lt;/script&gt;")
        self.assertNotContains(response, "<script>")

    def test_missing_records_unsupported_methods_and_no_delete_route(self):
        self.client.force_login(self.users["Editor"])
        self.assertEqual(self.client.get(reverse("contacts:detail", args=[self.customer.pk, uuid.uuid4()]), secure=True).status_code, 404)
        for name in (*self.read_routes, *self.write_routes):
            self.assertEqual(self.client.delete(self.route(name), secure=True).status_code, 405)
        for name in self.read_routes:
            self.assertEqual(self.client.post(self.route(name), secure=True).status_code, 405)
        self.assertEqual(self.client.get(self.person.get_absolute_url() + "delete/", secure=True).status_code, 404)

    def test_admin_is_read_only(self):
        self.client.force_login(self.users["Administrator"])
        for model, obj in (("contact", self.person), ("contactpoint", self.email)):
            url = reverse(f"admin:contacts_{model}_change", args=[obj.pk])
            self.assertEqual(self.client.get(url, secure=True).status_code, 200)
            self.assertEqual(self.client.post(url, {}, secure=True).status_code, 403)
            self.assertEqual(self.client.post(reverse(f"admin:contacts_{model}_delete", args=[obj.pk]), {}, secure=True).status_code, 403)


class ContactSearchTests(ContactFixtures):
    def setUp(self):
        self.client.force_login(self.users["Viewer"])

    def test_name_email_and_formatted_phone_search(self):
        self.point(kind="phone", value="+45 12 34 56 78")
        for query in ("aLiCe", "ALICE@EXAMPLE", "12345678", "+45 12-34-56-78", "0045 12345678"):
            response = self.client.get(self.route("list"), {"q": query}, secure=True)
            self.assertContains(response, "Alice Example")
            self.assertNotContains(response, "Bob Example")
        self.assertContains(self.client.get(self.route("list"), {"q": "12345678"}, secure=True), self.general.value)

    def test_search_is_customer_scoped_and_has_no_join_duplicates(self):
        self.point(value="alice.second@example.invalid")
        self.point(contact_id=self.foreign_person.pk, customer_id=self.other_customer.pk, value="alice.foreign@example.invalid")
        people, _ = directory_results(self.customer, "alice")
        self.assertEqual(list(people), [self.person])
        self.assertContains(self.client.get(self.route("list"), {"q": "' OR 1=1 --"}, secure=True), "No contacts found")

    def test_archived_contacts_and_details_search_behavior(self):
        set_contact_active(actor=self.users["Editor"], customer_id=self.customer.pk, contact_id=self.person.pk, is_active=False)
        self.assertNotContains(self.client.get(self.route("list"), secure=True), "Alice Example")
        for status in ("archived", ""):
            self.assertContains(self.client.get(self.route("list"), {"status": status, "q": "alice@example"}, secure=True), "Alice Example")
        self.assertContains(self.client.get(self.person.get_absolute_url(), secure=True), self.email.value)
        set_contact_active(actor=self.users["Editor"], customer_id=self.customer.pk, contact_id=self.person.pk, is_active=True)
        set_point_active(actor=self.users["Editor"], customer_id=self.customer.pk, contact_id=self.person.pk, point_id=self.email.pk, is_active=False)
        self.assertNotContains(self.client.get(self.route("list"), {"q": "alice@example"}, secure=True), "Alice Example")

    def test_general_detail_archive_filter(self):
        set_point_active(actor=self.users["Editor"], customer_id=self.customer.pk, point_id=self.general.pk, is_active=False)
        self.assertNotContains(self.client.get(self.route("list"), secure=True), self.general.value)
        self.assertContains(self.client.get(self.route("list"), {"status": "archived"}, secure=True), self.general.value)

    def test_pagination_and_invalid_filter(self):
        Contact.objects.bulk_create([Contact(customer=self.customer, full_name=f"Page Person {i:02}") for i in range(28)])
        response = self.client.get(self.route("list"), {"q": "Page Person", "status": "active"}, secure=True)
        self.assertEqual(len(response.context["page_obj"]), 25)
        self.assertContains(response, "q=Page+Person&amp;status=active&amp;page=2")
        self.assertEqual(len(self.client.get(self.route("list"), {"q": "Page Person", "page": 2}, secure=True).context["page_obj"]), 3)
        for query in ({"q": "x" * 201}, {"status": "invalid"}):
            self.assertEqual(self.client.get(self.route("list"), query, secure=True).status_code, 400)


class PrimaryConcurrencyTests(TransactionTestCase):
    def test_concurrent_primary_selection_serializes_on_owner(self):
        call_command("setup_roles", verbosity=0)
        actor = User.objects.create_user(username="concurrent-editor")
        actor.groups.add(Group.objects.get(name="Editor"))
        customer = Customer.objects.create(name="Concurrent synthetic customer")
        person = create_contact(actor=actor, customer_id=customer.pk, full_name="Concurrent synthetic contact")
        start = Barrier(2)

        def create_primary(index):
            close_old_connections()
            try:
                user = User.objects.get(pk=actor.pk)
                start.wait(timeout=10)
                return save_contact_point(actor=user, customer_id=customer.pk, contact_id=person.pk,
                                          kind="email", value=f"concurrent{index}@example.invalid", is_primary=True).pk
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(create_primary, index) for index in range(2)]
            ids = [future.result(timeout=20) for future in futures]
        self.assertEqual(person.points.count(), 2)
        self.assertEqual(person.points.filter(is_primary=True, is_active=True).count(), 1)
        self.assertIn(person.points.get(is_primary=True).pk, ids)
