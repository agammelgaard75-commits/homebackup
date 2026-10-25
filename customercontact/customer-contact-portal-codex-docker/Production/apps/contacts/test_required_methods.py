"""A contact and its active details are validated as one write."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.customers.models import Customer

from .models import Contact, ContactCustomer, ContactPoint
from .services import create_contact, save_contact_point, set_point_active, update_contact
from .validation import CONTACT_METHOD_REQUIRED


class RequiredContactMethodTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.users = {}
        for role in ("Viewer", "Editor", "Administrator"):
            user = get_user_model().objects.create_user(username=f"required-{role.lower()}")
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.customer = Customer.objects.create(name="Required Methods Alpha")
        cls.second = Customer.objects.create(name="Required Methods Beta")

    def _create(self, methods, *, general=False):
        return create_contact(actor=self.users["Editor"], customer_id=self.customer.pk,
                              full_name="Support Desk" if general else "Named Person",
                              is_general=general, methods=methods)

    @staticmethod
    def _method_payload(rows, *, initial=0):
        data = {"methods-TOTAL_FORMS": str(len(rows)), "methods-INITIAL_FORMS": str(initial),
                "methods-MIN_NUM_FORMS": "0", "methods-MAX_NUM_FORMS": "1000"}
        for index, row in enumerate(rows):
            for key, value in row.items():
                data[f"methods-{index}-{key}"] = value
        return data

    def test_email_phone_both_and_neither_for_named_and_general(self):
        for general in (False, True):
            for methods in ([{"kind": "email", "value": "person@example.invalid"}],
                            [{"kind": "phone", "value": "+45 12 34 56 78"}],
                            [{"kind": "email", "value": "person@example.invalid"},
                             {"kind": "phone", "value": "12345678"}]):
                with self.subTest(general=general, methods=methods):
                    contact = self._create(methods, general=general)
                    self.assertEqual(contact.points.filter(is_active=True).count(), len(methods))
            before = (Contact.objects.count(), ContactCustomer.objects.count(), AuditEvent.objects.count())
            with self.assertRaisesMessage(ValidationError, CONTACT_METHOD_REQUIRED):
                self._create([], general=general)
            self.assertEqual((Contact.objects.count(), ContactCustomer.objects.count(), AuditEvent.objects.count()), before)

    def test_last_method_archive_rejected_without_mutation_or_audit(self):
        for kind, value in (("email", "last@example.invalid"), ("phone", "12345678")):
            contact = self._create([{"kind": kind, "value": value}])
            point = contact.points.get()
            count = AuditEvent.objects.count()
            with self.assertRaisesMessage(ValidationError, CONTACT_METHOD_REQUIRED):
                set_point_active(actor=self.users["Editor"], customer_id=self.customer.pk,
                                 contact_id=contact.pk, point_id=point.pk, is_active=False)
            point.refresh_from_db()
            self.assertTrue(point.is_active)
            self.assertEqual(AuditEvent.objects.count(), count)

    def test_complete_edit_can_replace_last_method_and_reject_removing_all(self):
        contact = self._create([{"kind": "email", "value": "old@example.invalid"}])
        old = contact.points.get()
        update_contact(actor=self.users["Editor"], customer_id=self.customer.pk, contact_id=contact.pk,
                       full_name="Replaced", methods=[{"point_id": old.pk, "remove": True},
                                                        {"kind": "phone", "value": "12345678"}])
        old.refresh_from_db()
        self.assertFalse(old.is_active)
        self.assertEqual(list(contact.points.filter(is_active=True).values_list("kind", flat=True)), ["phone"])
        phone = contact.points.get(kind="phone")
        before = (Contact.objects.get(pk=contact.pk).full_name, AuditEvent.objects.count())
        with self.assertRaisesMessage(ValidationError, CONTACT_METHOD_REQUIRED):
            update_contact(actor=self.users["Editor"], customer_id=self.customer.pk, contact_id=contact.pk,
                           full_name="Must roll back", methods=[{"point_id": phone.pk, "remove": True}])
        self.assertEqual((Contact.objects.get(pk=contact.pk).full_name, AuditEvent.objects.count()), before)
        phone.refresh_from_db()
        self.assertTrue(phone.is_active)

    def test_legacy_incomplete_contact_is_viewable_and_repairable(self):
        legacy = Contact.objects.create(customer=self.customer, full_name="Existing incomplete")
        ContactCustomer.objects.create(customer=self.customer, contact=legacy)
        self.client.force_login(self.users["Viewer"])
        self.assertEqual(self.client.get(legacy.get_absolute_url(), secure=True).status_code, 200)
        self.client.force_login(self.users["Editor"])
        with self.assertRaisesMessage(ValidationError, CONTACT_METHOD_REQUIRED):
            update_contact(actor=self.users["Editor"], customer_id=self.customer.pk,
                           contact_id=legacy.pk, full_name="Still incomplete")
        self.assertEqual(Contact.objects.get(pk=legacy.pk).full_name, "Existing incomplete")
        save_contact_point(actor=self.users["Editor"], customer_id=self.customer.pk,
                           contact_id=legacy.pk, kind="phone", value="12345678")
        update_contact(actor=self.users["Editor"], customer_id=self.customer.pk,
                       contact_id=legacy.pk, full_name="Repaired")
        self.assertEqual(Contact.objects.get(pk=legacy.pk).full_name, "Repaired")

    def test_customer_and_global_forms_enforce_rule_and_accept_multiple_methods(self):
        for url, extra in ((reverse("contacts:create", args=[self.customer.pk]), {}),
                           (reverse("global_contacts:create"), {"customers": [str(self.customer.pk)]})):
            self.client.force_login(self.users["Editor"])
            before = Contact.objects.filter(full_name="Form contact").count()
            empty = {"full_name": "Form contact", **extra, **self._method_payload([{}])}
            response = self.client.post(url, empty, secure=True)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, CONTACT_METHOD_REQUIRED)
            self.assertEqual(Contact.objects.filter(full_name="Form contact").count(), before)
            for rows in ([{"kind": "email", "value": "one@example.invalid"}],
                         [{"kind": "phone", "value": "12345678"}],
                         [{"kind": "email", "value": "one@example.invalid"},
                          {"kind": "phone", "value": "12345678"}]):
                response = self.client.post(url, {"full_name": "Form contact", **extra,
                    **self._method_payload(rows)}, secure=True)
                self.assertEqual(response.status_code, 302)
                contact = Contact.objects.filter(full_name="Form contact").latest("created_at")
                self.assertEqual(contact.points.filter(is_active=True).count(), len(rows))

    def test_invalid_method_values_do_not_create_contacts(self):
        self.client.force_login(self.users["Editor"])
        for kind, value in (("email", "not-an-email"), ("phone", " "), ("phone", "call me")):
            response = self.client.post(reverse("global_contacts:create"), {
                "full_name": "Invalid value", "customers": [str(self.customer.pk)],
                **self._method_payload([{"kind": kind, "value": value}]),
            }, secure=True)
            self.assertContains(response, CONTACT_METHOD_REQUIRED)
            self.assertFalse(Contact.objects.filter(full_name="Invalid value").exists())

    def test_edit_form_removing_last_and_replacing_it(self):
        contact = self._create([{"kind": "email", "value": "old@example.invalid"}], general=True)
        point = contact.points.get()
        self.client.force_login(self.users["Editor"])
        url = reverse("contacts:edit", args=[self.customer.pk, contact.pk])
        rows = [{"point_id": str(point.pk), "kind": "email", "value": point.value, "remove": "on"}]
        response = self.client.post(url, {"full_name": "Support Desk", "is_general": "on",
            **self._method_payload(rows, initial=1)}, secure=True)
        self.assertContains(response, CONTACT_METHOD_REQUIRED)
        point.refresh_from_db()
        self.assertTrue(point.is_active)
        rows.append({"kind": "phone", "value": "12345678"})
        response = self.client.post(url, {"full_name": "Support Desk", "is_general": "on",
            **self._method_payload(rows, initial=1)}, secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ContactPoint.objects.get(pk=point.pk).is_active)
        self.assertEqual(contact.points.filter(is_active=True, kind="phone").count(), 1)

    def test_roles_and_last_method_archive_view(self):
        contact = self._create([{"kind": "phone", "value": "12345678"}])
        point = contact.points.get()
        create_url = reverse("contacts:create", args=[self.customer.pk])
        archive_url = reverse("contacts:point_archive", args=[self.customer.pk, contact.pk, point.pk])
        self.client.force_login(self.users["Viewer"])
        self.assertEqual(self.client.get(contact.get_absolute_url(), secure=True).status_code, 200)
        self.assertEqual(self.client.post(create_url, {"full_name": "Forbidden"}, secure=True).status_code, 403)
        self.assertEqual(self.client.post(archive_url, secure=True).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(contact.get_absolute_url(), secure=True).status_code, 302)
        for role in ("Editor", "Administrator"):
            self.client.force_login(self.users[role])
            response = self.client.post(archive_url, follow=True, secure=True)
            self.assertContains(response, CONTACT_METHOD_REQUIRED)
            self.assertTrue(ContactPoint.objects.get(pk=point.pk).is_active)
