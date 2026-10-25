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

from .models import Customer


class CustomerImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.users = {}
        for role in ("Viewer", "Editor", "Administrator"):
            user = get_user_model().objects.create_user(username=f"customer-import-{role.lower()}")
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user

    @staticmethod
    def payload(*records):
        return {"schema_version": 1, "customers": list(records)}

    def preview(self, payload):
        file = SimpleUploadedFile("customers.json", json.dumps(payload).encode(), content_type="application/json")
        return self.client.post(reverse("customers:import"), {"action": "preview", "file": file}, secure=True)

    def confirm(self, response):
        return self.client.post(reverse("customers:import"), {
            "action": "confirm", "confirm_token": response.context["confirm_token"], "confirm_import": "on",
        }, secure=True)

    def test_create_update_repeat_and_audit(self):
        self.client.force_login(self.users["Administrator"])
        payload = self.payload({"import_id": "cust-a", "name": "Alpha", "company_id": " 0012 "})
        preview = self.preview(payload)
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.context["counts"]["create"], 1)
        self.assertEqual(self.confirm(preview).status_code, 302)
        customer = Customer.objects.get(import_id="cust-a")
        self.assertEqual(customer.reference_code, "0012")
        self.assertTrue(AuditEvent.objects.filter(actor=self.users["Administrator"], object_type="json_import").exists())
        repeat = self.preview(payload)
        self.assertEqual(repeat.context["counts"]["unchanged"], 1)
        self.assertEqual(self.confirm(repeat).status_code, 302)
        self.assertEqual(Customer.objects.filter(import_id="cust-a").count(), 1)
        changed = self.preview(self.payload({"import_id": "cust-a", "name": "Alpha Updated", "notes": "new"}))
        self.assertEqual(changed.context["counts"]["update"], 1)
        self.assertEqual(self.confirm(changed).status_code, 302)
        customer.refresh_from_db()
        self.assertEqual((customer.name, customer.notes, customer.reference_code), ("Alpha Updated", "new", "0012"))

    def test_mapping_is_explicit_and_duplicate_file_rejected(self):
        self.client.force_login(self.users["Administrator"])
        existing = Customer.objects.create(name="Existing")
        preview = self.preview(self.payload({"import_id": "existing-key", "name": "Existing"}))
        self.assertEqual(preview.context["counts"]["reject"], 1)
        review = self.client.post(reverse("customers:import"), {
            "action": "review", "draft_token": preview.context["draft_token"], "map_1": str(existing.pk),
        }, secure=True)
        self.assertEqual(review.context["counts"]["update"], 1)
        self.assertEqual(self.confirm(review).status_code, 302)
        existing.refresh_from_db()
        self.assertEqual(existing.import_id, "existing-key")
        self.assertEqual(Customer.objects.count(), 1)
        duplicate = self.preview(self.payload({"import_id": "same", "name": "A"}, {"import_id": "same", "name": "B"}))
        self.assertEqual(duplicate.context["counts"]["reject"], 2)
        self.assertNotIn("confirm_token", duplicate.context)

    def test_invalid_file_permissions_and_references(self):
        url = reverse("customers:import")
        self.assertEqual(self.client.get(url, secure=True).status_code, 302)
        for role in ("Viewer", "Editor"):
            self.client.force_login(self.users[role])
            self.assertEqual(self.client.get(url, secure=True).status_code, 403)
            self.assertEqual(self.client.get(reverse("customers:import_example"), secure=True).status_code, 403)
        self.client.force_login(self.users["Administrator"])
        self.assertEqual(self.client.get(reverse("customers:import_example"), secure=True).status_code, 200)
        self.assertEqual(self.client.get(reverse("customers:import_schema"), secure=True).status_code, 200)
        self.assertEqual(self.client.get(reverse("customers:import_guide"), secure=True).status_code, 200)
        invalid = self.preview(self.payload({"import_id": "bad", "name": ""}))
        self.assertEqual(invalid.context["counts"]["reject"], 1)
        self.assertNotIn("confirm_token", invalid.context)
        malformed = SimpleUploadedFile("customers.json", b'{"schema_version":1,"customers":[],"customers":[]}')
        response = self.client.post(url, {"action": "preview", "file": malformed}, secure=True)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Customer.objects.count(), 0)

    def test_confirm_rolls_back_all_records_if_audit_fails(self):
        self.client.force_login(self.users["Administrator"])
        preview = self.preview(self.payload({"import_id": "one", "name": "One"}, {"import_id": "two", "name": "Two"}))
        with patch("apps.customers.imports.record_import_summary", side_effect=ValidationError("Audit unavailable")):
            response = self.confirm(preview)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Customer.objects.count(), 0)

    def test_stale_preview_cannot_overwrite_later_edit(self):
        self.client.force_login(self.users["Administrator"])
        customer = Customer.objects.create(name="Original", import_id="stable")
        preview = self.preview(self.payload({"import_id": "stable", "name": "Imported"}))
        self.assertEqual(preview.context["counts"]["update"], 1)
        Customer.objects.filter(pk=customer.pk).update(name="Later edit")
        response = self.confirm(preview)
        self.assertEqual(response.status_code, 400)
        customer.refresh_from_db()
        self.assertEqual(customer.name, "Later edit")
