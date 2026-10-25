import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.customers.models import Customer

from .models import Contact, ContactCustomer, ContactPoint


class ContactImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.users = {}
        for role in ("Viewer", "Editor", "Administrator"):
            user = get_user_model().objects.create_user(username=f"contact-import-{role.lower()}")
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.customer = Customer.objects.create(name="Alpha", import_id="customer-alpha")
        cls.other = Customer.objects.create(name="Beta", import_id="customer-beta")

    @staticmethod
    def payload(*records):
        return {"schema_version": 1, "contacts": list(records)}

    @staticmethod
    def record(**changes):
        return {"import_id": "contact-one", "name": "Support Desk", "kind": "general",
                "customer_import_ids": ["customer-alpha"], "emails": [{"address": "support@example.invalid"}], **changes}

    def preview(self, payload):
        file = SimpleUploadedFile("contacts.json", json.dumps(payload).encode(), content_type="application/json")
        return self.client.post(reverse("global_contacts:import"), {"action": "preview", "file": file}, secure=True)

    def confirm(self, response):
        return self.client.post(reverse("global_contacts:import"), {
            "action": "confirm", "confirm_token": response.context["confirm_token"], "confirm_import": "on",
        }, secure=True)

    def test_general_contact_multiple_customers_methods_and_repeat(self):
        self.client.force_login(self.users["Administrator"])
        record = self.record(customer_import_ids=["customer-alpha", "customer-beta"],
                             emails=[{"address": "support@example.invalid", "primary": True},
                                     {"address": "other@example.invalid"}],
                             phones=[{"number": "+45 12 34 56 78"}])
        preview = self.preview(self.payload(record))
        self.assertEqual(preview.context["counts"]["create"], 1)
        self.assertEqual(self.confirm(preview).status_code, 302)
        contact = Contact.objects.get(import_id="contact-one")
        self.assertTrue(contact.is_general)
        self.assertEqual(contact.contact_type, "technical")
        self.assertEqual(set(ContactCustomer.objects.filter(contact=contact, is_active=True).values_list("customer_id", flat=True)),
                         {self.customer.pk, self.other.pk})
        self.assertEqual(contact.points.filter(is_active=True).count(), 3)
        self.assertEqual(contact.points.get(kind="email", is_primary=True).value, "support@example.invalid")
        repeat = self.preview(self.payload(record))
        self.assertEqual(repeat.context["counts"]["unchanged"], 1)
        self.assertEqual(self.confirm(repeat).status_code, 302)
        self.assertEqual(Contact.objects.count(), 1)
        self.assertEqual(ContactPoint.objects.count(), 3)
        self.assertTrue(AuditEvent.objects.filter(actor=self.users["Administrator"], object_type="json_import").exists())

    def test_additive_update_preserves_existing_methods_and_links(self):
        self.client.force_login(self.users["Administrator"])
        self.confirm(self.preview(self.payload(self.record())))
        contact = Contact.objects.get(import_id="contact-one")
        updated = self.record(name="Help Desk", customer_import_ids=["customer-beta"],
                              emails=[{"address": "new@example.invalid"}], phones=[{"number": "12345678"}])
        preview = self.preview(self.payload(updated))
        self.assertEqual(preview.context["counts"]["update"], 1)
        self.assertEqual(self.confirm(preview).status_code, 302)
        contact.refresh_from_db()
        self.assertEqual(contact.full_name, "Help Desk")
        self.assertEqual(contact.points.filter(is_active=True).count(), 3)
        self.assertEqual(ContactCustomer.objects.filter(contact=contact, is_active=True).count(), 2)
        self.assertEqual(self.preview(self.payload(updated)).context["counts"]["unchanged"], 1)

    def test_phone_only_person_and_explicit_primary_change(self):
        self.client.force_login(self.users["Administrator"])
        phone_only = self.record(name="Phone Person", kind="person", emails=[],
                                 phones=[{"number": "12345678", "primary": True}])
        self.assertEqual(self.confirm(self.preview(self.payload(phone_only))).status_code, 302)
        contact = Contact.objects.get(import_id="contact-one")
        self.assertFalse(contact.is_general)
        self.assertEqual(contact.points.filter(kind="phone", is_primary=True).count(), 1)
        second = self.record(name="Phone Person", kind="person", emails=[],
                             phones=[{"number": "87654321", "primary": True}, {"number": "12345678"}])
        self.assertEqual(self.confirm(self.preview(self.payload(second))).status_code, 302)
        self.assertEqual(contact.points.get(is_primary=True).normalized_value, "87654321")
        self.assertEqual(self.preview(self.payload(second)).context["counts"]["unchanged"], 1)

    def test_missing_method_reference_duplicate_and_mapping(self):
        self.client.force_login(self.users["Administrator"])
        no_method = self.preview(self.payload(self.record(emails=[])))
        self.assertEqual(no_method.context["counts"]["reject"], 1)
        self.assertContains(no_method, "At least one email address or phone number is required.")
        unknown = self.preview(self.payload(self.record(customer_import_ids=["missing"])))
        self.assertEqual(unknown.context["counts"]["reject"], 1)
        self.assertContains(unknown, "Unknown customer import_id: missing.")
        duplicate = self.preview(self.payload(self.record(), self.record(name="Second")))
        self.assertEqual(duplicate.context["counts"]["reject"], 2)
        malformed_type = self.preview(self.payload(self.record(contact_type=["technical"])))
        self.assertEqual(malformed_type.context["counts"]["reject"], 1)
        existing = Contact.objects.create(customer=self.customer, full_name="Support Desk")
        ContactCustomer.objects.create(customer=self.customer, contact=existing)
        ContactPoint.objects.create(customer=self.customer, contact=existing, kind="email",
                                    value="old@example.invalid", normalized_value="old@example.invalid")
        candidate = self.preview(self.payload(self.record()))
        self.assertEqual(candidate.context["counts"]["reject"], 1)
        review = self.client.post(reverse("global_contacts:import"), {
            "action": "review", "draft_token": candidate.context["draft_token"], "map_1": str(existing.pk),
        }, secure=True)
        self.assertEqual(review.context["counts"]["update"], 1)
        self.assertEqual(self.confirm(review).status_code, 302)
        existing.refresh_from_db()
        self.assertEqual(existing.import_id, "contact-one")
        self.assertEqual(Contact.objects.count(), 1)
        self.assertEqual(existing.points.filter(is_active=True).count(), 2)

    def test_permissions_downloads_and_atomic_audit_failure(self):
        url = reverse("global_contacts:import")
        self.assertEqual(self.client.get(url, secure=True).status_code, 302)
        for role in ("Viewer", "Editor"):
            self.client.force_login(self.users[role])
            self.assertEqual(self.client.get(url, secure=True).status_code, 403)
            self.assertEqual(self.client.get(reverse("global_contacts:import_example"), secure=True).status_code, 403)
        self.client.force_login(self.users["Administrator"])
        for name in ("import_example", "import_schema", "import_guide"):
            self.assertEqual(self.client.get(reverse(f"global_contacts:{name}"), secure=True).status_code, 200)
        preview = self.preview(self.payload(self.record()))
        with patch("apps.contacts.imports.record_import_summary", side_effect=ValidationError("Audit unavailable")):
            response = self.confirm(preview)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Contact.objects.count(), 0)
        self.assertEqual(ContactPoint.objects.count(), 0)
        self.assertEqual(ContactCustomer.objects.count(), 0)
