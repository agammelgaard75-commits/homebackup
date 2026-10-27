import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase

from apps.audit.models import AuditEvent
from apps.contacts.models import Contact, ContactCustomer, ContactPoint
from apps.contacts.services import create_contact, set_contact_active, set_contact_customers
from apps.customers.models import Customer
from apps.customers.services import archive_customer
from apps.services.models import CustomerService, Service
from apps.services.services import create_assignment

from .models import CleanupOperation


class CleanupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.users = {}
        for role in ("Viewer", "Editor", "Administrator"):
            user = get_user_model().objects.create_user(username=f"cleanup-{role.lower()}")
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.customer = Customer.objects.create(name="Cleanup Alpha")
        cls.other = Customer.objects.create(name="Cleanup Beta")
        cls.contact = create_contact(actor=cls.users["Editor"], customer_id=cls.customer.pk,
            full_name="Archived Person", methods=[{"kind": "phone", "value": "12345678"}])

    def post_json(self, path, data):
        return self.client.post(path, json.dumps(data), content_type="application/json", secure=True)

    def preview(self, customers=(), contacts=()):
        return self.post_json("/api/v1/cleanup/preview/", {"customer_ids": [str(pk) for pk in customers],
            "contact_ids": [str(pk) for pk in contacts]})

    def test_only_administrators_can_view_and_preview(self):
        path = "/api/v1/cleanup/archived-contacts/"
        self.assertEqual(self.client.get(path, secure=True).status_code, 401)
        for role in ("Viewer", "Editor"):
            self.client.force_login(self.users[role])
            self.assertEqual(self.client.get(path, secure=True).status_code, 403)
            self.assertEqual(self.preview(contacts=[self.contact.pk]).status_code, 403)
        self.client.force_login(self.users["Administrator"])
        self.assertEqual(self.client.get(path, secure=True).json()["count"], 0)
        self.assertEqual(self.preview(contacts=[self.contact.pk]).json()["plan"]["blockers"][0]["reason"],
                         "Contact is active.")
        self.assertTrue(any(item["reason"] == "Customer is active." for item in
            self.preview(customers=[self.customer.pk]).json()["plan"]["blockers"]))
        self.assertEqual(self.client.get("/admin/data-cleanup/", secure=True).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/cleanup/confirm/", secure=True).status_code, 405)

    def test_archived_contact_deletes_explicit_relations_and_preserves_customer_and_audit(self):
        set_contact_active(actor=self.users["Editor"], customer_id=self.customer.pk,
                           contact_id=self.contact.pk, is_active=False)
        self.client.force_login(self.users["Administrator"])
        self.assertEqual(self.client.get("/api/v1/cleanup/archived-contacts/",
            {"contact_type": "technical"}, secure=True).json()["count"], 1)
        self.assertEqual(self.client.get("/api/v1/cleanup/archived-contacts/",
            {"contact_type": "billing"}, secure=True).json()["count"], 0)
        result = self.preview(contacts=[self.contact.pk])
        self.assertEqual(result.status_code, 200, result.content)
        plan = result.json()["plan"]
        self.assertFalse(plan["blockers"])
        self.assertEqual(plan["counts"]["contact_methods"], 1)
        self.assertEqual(plan["counts"]["contact_links_deleted"], 1)
        self.assertTrue(Contact.objects.filter(pk=self.contact.pk).exists())
        no_confirmation = self.post_json("/api/v1/cleanup/confirm/", {
            "confirmation_token": result.json()["confirmation_token"], "confirm": False})
        self.assertEqual(no_confirmation.status_code, 400)
        response = self.post_json("/api/v1/cleanup/confirm/", {
            "confirmation_token": result.json()["confirmation_token"], "confirm": True})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(Contact.objects.filter(pk=self.contact.pk).exists())
        self.assertFalse(ContactPoint.objects.filter(contact_id=self.contact.pk).exists())
        self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())
        operation = CleanupOperation.objects.get(pk=response.json()["id"])
        self.assertEqual(operation.actor, self.users["Administrator"])
        self.assertTrue(AuditEvent.objects.filter(object_id=operation.pk, action="deleted").exists())
        self.assertEqual(self.client.get(f"/api/v1/cleanup/operations/{operation.pk}/", secure=True).status_code, 200)

    def test_shared_contact_is_preserved_when_customer_deleted(self):
        shared = create_contact(actor=self.users["Editor"], customer_id=self.other.pk,
            full_name="Shared Person", methods=[{"kind": "email", "value": "shared@example.invalid"}])
        set_contact_customers(actor=self.users["Editor"], customer_id=self.other.pk,
            contact_id=shared.pk, customer_ids=[self.other.pk, self.customer.pk])
        archive_customer(actor=self.users["Editor"], customer_id=self.customer.pk)
        set_contact_active(actor=self.users["Editor"], customer_id=self.customer.pk,
                           contact_id=self.contact.pk, is_active=False)
        self.client.force_login(self.users["Administrator"])
        blocked = self.preview(customers=[self.customer.pk]).json()["plan"]
        self.assertTrue(any(row["type"] == "contact" for row in blocked["blockers"]))
        response = self.preview(customers=[self.customer.pk], contacts=[self.contact.pk])
        self.assertEqual(response.status_code, 200)
        plan = response.json()["plan"]
        self.assertEqual(plan["counts"]["contacts_preserved"], 1)
        self.assertEqual(plan["counts"]["contact_links_detached"], 1)
        self.assertFalse(plan["blockers"])
        completed = self.post_json("/api/v1/cleanup/confirm/", {
            "confirmation_token": response.json()["confirmation_token"], "confirm": True})
        self.assertEqual(completed.status_code, 200, completed.content)
        self.assertFalse(Customer.objects.filter(pk=self.customer.pk).exists())
        self.assertTrue(Contact.objects.filter(pk=shared.pk).exists())
        self.assertTrue(ContactCustomer.objects.filter(contact=shared, customer=self.other).exists())
        self.assertFalse(ContactCustomer.objects.filter(contact=shared, customer_id=self.customer.pk).exists())
        self.assertTrue(AuditEvent.objects.filter(related_customer_id=self.customer.pk).exists())

    def test_service_assignment_blocks_customer_deletion(self):
        service = Service.objects.create(name="Cleanup Service")
        create_assignment(actor=self.users["Editor"], customer_id=self.customer.pk, service_id=service.pk)
        archive_customer(actor=self.users["Editor"], customer_id=self.customer.pk)
        set_contact_active(actor=self.users["Editor"], customer_id=self.customer.pk,
                           contact_id=self.contact.pk, is_active=False)
        self.client.force_login(self.users["Administrator"])
        result = self.preview(customers=[self.customer.pk], contacts=[self.contact.pk]).json()
        self.assertTrue(any(row["type"] == "assignment" for row in result["plan"]["blockers"]))
        self.assertIsNone(result["confirmation_token"])
        self.assertEqual(CustomerService.objects.count(), 1)

    def test_stale_preview_is_rejected_and_failed_attempt_audited(self):
        set_contact_active(actor=self.users["Editor"], customer_id=self.customer.pk,
                           contact_id=self.contact.pk, is_active=False)
        self.client.force_login(self.users["Administrator"])
        token = self.preview(contacts=[self.contact.pk]).json()["confirmation_token"]
        ContactPoint.objects.filter(contact=self.contact).update(value="87654321")
        response = self.post_json("/api/v1/cleanup/confirm/", {"confirmation_token": token, "confirm": True})
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Contact.objects.filter(pk=self.contact.pk).exists())
        self.assertTrue(CleanupOperation.objects.filter(result="failed", actor=self.users["Administrator"]).exists())
        self.assertTrue(AuditEvent.objects.filter(action="failed", object_type="data_cleanup").exists())

    def test_cleanup_rollback_if_audit_write_fails(self):
        set_contact_active(actor=self.users["Editor"], customer_id=self.customer.pk,
                           contact_id=self.contact.pk, is_active=False)
        self.client.force_login(self.users["Administrator"])
        token = self.preview(contacts=[self.contact.pk]).json()["confirmation_token"]
        with patch("apps.cleanup.services.record_cleanup", side_effect=RuntimeError("test audit failure")):
            response = self.post_json("/api/v1/cleanup/confirm/", {"confirmation_token": token, "confirm": True})
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.json()["error"]["code"], "server_error")
        self.assertTrue(Contact.objects.filter(pk=self.contact.pk).exists())
        self.assertTrue(ContactPoint.objects.filter(contact=self.contact).exists())
        self.assertFalse(CleanupOperation.objects.filter(result="completed").exists())
