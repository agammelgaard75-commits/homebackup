import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from apps.accounts.models import APICredential
from apps.accounts.credentials import issue_credential
from apps.audit.models import AuditEvent
from apps.contacts.models import Contact, ContactCustomer, ContactPoint
from apps.contacts.services import create_contact
from apps.customers.models import Customer
from apps.services.models import CustomerService, Service
from apps.services.services import create_assignment


class APITests(TestCase):
    def setUp(self):
        cache.clear()

    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.users = {}
        for role in ("Viewer", "Editor", "Administrator"):
            user = get_user_model().objects.create_user(username=f"api-{role.lower()}")
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.customer = Customer.objects.create(name="API Alpha", reference_code="11111111")
        cls.other = Customer.objects.create(name="API Beta")
        cls.contact = create_contact(actor=cls.users["Editor"], customer_id=cls.customer.pk,
            full_name="API Person", methods=[{"kind": "email", "value": "person@example.invalid"},
                                               {"kind": "phone", "value": "12345678"}])
        cls.service = Service.objects.create(name="API Monitoring")
        cls.second_service = Service.objects.create(name="API Support")
        cls.assignment = create_assignment(actor=cls.users["Editor"], customer_id=cls.customer.pk,
                                           service_id=cls.service.pk)

    def login(self, role):
        self.client.force_login(self.users[role])

    def post_json(self, path, data):
        return self.client.post(path, json.dumps(data), content_type="application/json", secure=True)

    def patch_json(self, path, data):
        return self.client.patch(path, json.dumps(data), content_type="application/json", secure=True)

    def test_anonymous_and_role_permissions(self):
        self.assertEqual(self.client.get("/api/v1/customers/", secure=True).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/health/", secure=True).status_code, 200)
        self.login("Viewer")
        self.assertEqual(self.client.get("/api/v1/customers/", secure=True).status_code, 200)
        self.assertEqual(self.post_json("/api/v1/customers/", {"name": "Denied"}).status_code, 403)
        self.assertEqual(self.client.get("/api/v1/audit/", secure=True).status_code, 403)
        self.assertEqual(self.client.get("/api/v1/cleanup/archived-customers/", secure=True).status_code, 403)
        self.login("Editor")
        self.assertEqual(self.post_json("/api/v1/services/", {"name": "Denied"}).status_code, 403)
        self.assertEqual(self.post_json("/api/v1/imports/customers/preview/", {}).status_code, 403)
        self.login("Administrator")
        self.assertEqual(self.client.get("/api/v1/audit/", secure=True).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/schema/", secure=True).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/docs/", secure=True).status_code, 200)

    def test_customer_crud_filter_pagination_and_relations(self):
        self.login("Editor")
        path = "/api/v1/customers/"
        created = self.post_json(path, {"name": "API Gamma", "reference_code": "33333333"})
        self.assertEqual(created.status_code, 201, created.content)
        identifier = created.json()["id"]
        self.assertEqual(self.patch_json(f"{path}{identifier}/", {"notes": "Changed"}).status_code, 200)
        self.assertEqual(self.client.get(f"{path}{identifier}/", secure=True).json()["notes"], "Changed")
        listed = self.client.get(path, {"q": "api", "page_size": 1, "sort": "-name"}, secure=True).json()
        self.assertEqual(listed["count"], 3)
        self.assertEqual(len(listed["results"]), 1)
        self.assertEqual(self.client.get(f"{path}{self.customer.pk}/contacts/", secure=True).json()["count"], 1)
        self.assertEqual(self.client.get(f"{path}{self.customer.pk}/services/", secure=True).json()["count"], 1)
        self.assertEqual(self.post_json(f"{path}{identifier}/archive/", {}).status_code, 200)
        self.assertEqual(self.client.get(path, {"q": "Gamma"}, secure=True).json()["count"], 0)
        self.assertEqual(self.client.get(path, {"q": "Gamma", "status": "all"}, secure=True).json()["count"], 1)
        self.assertEqual(self.post_json(f"{path}{identifier}/restore/", {}).status_code, 200)
        self.assertEqual(self.client.delete(f"{path}{identifier}/", secure=True).status_code, 405)
        self.assertEqual(self.post_json(path, {"name": "Invalid", "reference_code": "11111111"}).status_code, 400)

    def test_contact_crud_methods_and_relationships(self):
        self.login("Editor")
        path = "/api/v1/contacts/"
        payload = {"full_name": "Shared Desk", "is_general": True,
                   "customer_ids": [str(self.customer.pk), str(self.other.pk)],
                   "methods": [{"kind": "email", "value": "desk@example.invalid"}]}
        created = self.post_json(path, payload)
        self.assertEqual(created.status_code, 201, created.content)
        identifier = created.json()["id"]
        detail = f"{path}{identifier}/"
        self.assertEqual(len(created.json()["customer_ids"]), 2)
        self.assertEqual(self.client.get(path, {"q": "desk", "customer_id": self.other.pk}, secure=True).json()["count"], 1)
        point = self.post_json(f"{detail}methods/", {"kind": "phone", "value": "87654321", "label": "work"})
        self.assertEqual(point.status_code, 201, point.content)
        point_id = point.json()["id"]
        self.assertEqual(self.patch_json(f"{detail}methods/{point_id}/", {"value": "87654322"}).status_code, 200)
        self.assertEqual(self.post_json(f"{detail}methods/{point_id}/archive/", {}).status_code, 200)
        self.assertEqual(self.post_json(f"{detail}methods/{point_id}/restore/", {}).status_code, 200)
        self.assertEqual(self.patch_json(detail, {"job_title": "Support"}).status_code, 200)
        self.assertEqual(self.post_json(f"{detail}customers/", {"customer_id": str(self.customer.pk)}).status_code, 200)
        self.assertEqual(self.post_json(f"{detail}customers/{self.other.pk}/remove/", {}).status_code, 200)
        self.assertEqual(len(self.client.get(detail, secure=True).json()["customer_ids"]), 1)
        self.assertEqual(self.post_json(f"{detail}archive/", {}).status_code, 200)
        self.assertEqual(self.post_json(f"{detail}restore/", {}).status_code, 200)
        self.assertTrue(ContactCustomer.objects.filter(contact_id=identifier, customer=self.other, is_active=False).exists())

    def test_contact_validation_rejects_missing_method_and_last_method_archive(self):
        self.login("Editor")
        path = "/api/v1/contacts/"
        invalid = self.post_json(path, {"full_name": "No method", "customer_ids": [str(self.customer.pk)]})
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("At least one email address or phone number is required", invalid.content.decode())
        invalid = self.post_json(path, {"full_name": "Bad email", "customer_ids": [str(self.customer.pk)],
                                        "methods": [{"kind": "email", "value": "wrong"}]})
        self.assertEqual(invalid.status_code, 400)
        email = self.contact.points.get(kind="email")
        phone = self.contact.points.get(kind="phone")
        self.assertEqual(self.post_json(f"{path}{self.contact.pk}/methods/{email.pk}/archive/", {}).status_code, 200)
        self.assertEqual(self.post_json(f"{path}{self.contact.pk}/methods/{phone.pk}/archive/", {}).status_code, 400)
        phone.refresh_from_db()
        self.assertTrue(phone.is_active)
        self.assertEqual(self.patch_json(f"{path}{self.contact.pk}/", {"methods": []}).status_code, 400)

    def test_service_catalog_and_assignments(self):
        self.login("Administrator")
        created = self.post_json("/api/v1/services/", {"name": "API New", "category": "Ops"})
        self.assertEqual(created.status_code, 201, created.content)
        identifier = created.json()["id"]
        self.assertEqual(self.patch_json(f"/api/v1/services/{identifier}/", {"description": "Updated"}).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/services/", {"q": "New"}, secure=True).json()["count"], 1)
        self.assertEqual(self.post_json(f"/api/v1/services/{identifier}/archive/", {}).status_code, 200)
        self.assertEqual(self.post_json(f"/api/v1/services/{identifier}/restore/", {}).status_code, 200)
        self.assertEqual(self.client.get(f"/api/v1/services/{self.service.pk}/customers/", secure=True).json()["count"], 1)
        self.login("Editor")
        created = self.post_json("/api/v1/assignments/", {"customer_id": str(self.other.pk),
            "service_id": str(self.service.pk), "status": "active"})
        self.assertEqual(created.status_code, 201, created.content)
        assignment_id = created.json()["id"]
        self.assertEqual(self.client.get(f"/api/v1/assignments/{assignment_id}/", secure=True).status_code, 200)
        self.assertEqual(self.patch_json(f"/api/v1/assignments/{assignment_id}/", {"status": "suspended"}).status_code, 200)
        self.assertEqual(self.post_json(f"/api/v1/assignments/{assignment_id}/terminate/", {}).status_code, 200)
        self.assertEqual(self.post_json("/api/v1/assignments/", {"customer_id": str(self.other.pk),
            "service_id": str(self.service.pk), "start_date": "2026-05-02", "end_date": "2026-05-01"}).status_code, 400)
        self.assertEqual(self.client.get("/api/v1/assignments/", {"status": "all", "customer_id": self.other.pk}, secure=True).json()["count"], 1)

    def test_global_and_service_search_and_email_export(self):
        self.login("Viewer")
        self.assertGreater(self.client.get("/api/v1/search/", {"q": "Person"}, secure=True).json()["groups"]["contacts"]["count"], 0)
        base = "/api/v1/search/by-service/"
        query = {"services": [str(self.service.pk)]}
        self.assertEqual(self.client.get(base, query, secure=True).json()["count"], 1)
        create_assignment(actor=self.users["Editor"], customer_id=self.customer.pk, service_id=self.second_service.pk)
        query["services"] = [str(self.service.pk), str(self.second_service.pk)]
        self.assertEqual(self.client.get(base, {**query, "mode": "all"}, secure=True).json()["count"], 1)
        self.assertEqual(self.client.get(base, {**query, "mode": "any"}, secure=True).json()["count"], 1)
        email = self.client.get(f"{base}emails/", query, secure=True).json()
        self.assertEqual(email["emails"], ["person@example.invalid"])
        self.assertEqual(email["count"], 1)
        self.assertEqual(self.client.get(base, {"services": [str(self.service.pk)], "mode": "bad"}, secure=True).status_code, 400)

    def test_service_any_all_inactive_and_email_export_across_pages(self):
        self.login("Viewer")
        base = "/api/v1/search/by-service/"
        create_assignment(actor=self.users["Editor"], customer_id=self.other.pk,
                          service_id=self.second_service.pk)
        selected = {"services": [str(self.service.pk), str(self.second_service.pk)]}
        self.assertEqual(self.client.get(base, {**selected, "mode": "any"}, secure=True).json()["count"], 2)
        self.assertEqual(self.client.get(base, {**selected, "mode": "all"}, secure=True).json()["count"], 0)
        create_assignment(actor=self.users["Editor"], customer_id=self.customer.pk,
                          service_id=self.second_service.pk, status="suspended")
        self.assertEqual(self.client.get(base, {**selected, "mode": "all"}, secure=True).json()["count"], 0)
        self.assertEqual(self.client.get(base, {**selected, "mode": "all",
            "include_inactive_assignments": "true"}, secure=True).json()["count"], 1)
        for index in range(26):
            create_contact(actor=self.users["Editor"], customer_id=self.customer.pk,
                full_name=f"Extra {index}", methods=[{"kind": "email", "value": f"extra{index}@example.invalid"}])
        page = self.client.get(base, {"services": [str(self.service.pk)], "page_size": 10}, secure=True).json()
        self.assertEqual(page["count"], 27)
        self.assertEqual(len(page["results"]), 10)
        exported = self.client.get(f"{base}emails/", {"services": [str(self.service.pk)]}, secure=True).json()
        self.assertEqual(exported["count"], 27)
        self.assertIn("extra25@example.invalid", exported["emails"])
        create_contact(actor=self.users["Editor"], customer_id=self.customer.pk,
            full_name="Duplicate Address", methods=[{"kind": "email", "value": "PERSON@example.invalid"}])
        self.assertEqual(self.client.get(f"{base}emails/", {"services": [str(self.service.pk)]},
            secure=True).json()["count"], 27)

    def test_import_preview_execute_idempotency_and_audit(self):
        self.login("Administrator")
        document = {"schema_version": 1, "customers": [{"import_id": "api-new-customer", "name": "Import API"}]}
        url = "/api/v1/imports/customers/"
        preview = self.post_json(f"{url}preview/", {"document": document})
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertEqual(preview.json()["counts"]["create"], 1)
        executed = self.post_json(f"{url}execute/", {"confirm": True,
            "confirmation_token": preview.json()["confirmation_token"]})
        self.assertEqual(executed.status_code, 200, executed.content)
        self.assertEqual(Customer.objects.filter(import_id="api-new-customer").count(), 1)
        repeated = self.post_json(f"{url}preview/", {"document": document}).json()
        self.assertEqual(repeated["counts"]["unchanged"], 1)
        self.assertEqual(self.post_json(f"{url}execute/", {"confirm": True,
            "confirmation_token": repeated["confirmation_token"]}).status_code, 200)
        contact_doc = {"schema_version": 1, "contacts": [{"import_id": "api-import-contact", "name": "API Help",
            "kind": "general", "customer_import_ids": ["api-new-customer"],
            "emails": [{"address": "help@example.invalid"}]}]}
        contact_url = "/api/v1/imports/contacts/"
        contact_preview = self.post_json(f"{contact_url}preview/", {"document": contact_doc})
        self.assertEqual(contact_preview.status_code, 200, contact_preview.content)
        self.assertEqual(self.post_json(f"{contact_url}execute/", {"confirm": True,
            "confirmation_token": contact_preview.json()["confirmation_token"]}).status_code, 200)
        self.assertEqual(Contact.objects.filter(import_id="api-import-contact").count(), 1)
        self.assertEqual(self.post_json(f"{contact_url}preview/", {"document": contact_doc}).json()[
            "counts"]["unchanged"], 1)
        self.assertTrue(AuditEvent.objects.filter(action="imported", actor=self.users["Administrator"]).exists())
        bad = self.post_json(f"{contact_url}preview/", {"document": {"schema_version": 1, "contacts": [
            {"import_id": "invalid", "name": "No method", "customer_import_ids": ["api-new-customer"]}]}})
        self.assertEqual(bad.status_code, 200)
        self.assertEqual(bad.json()["counts"]["reject"], 1)

    def test_contact_import_preserves_multiple_customer_associations(self):
        self.login("Administrator")
        for key, name in (("multi-a", "Multi A"), ("multi-b", "Multi B")):
            Customer.objects.create(import_id=key, name=name)
        document = {"schema_version": 1, "contacts": [{"import_id": "multi-person", "name": "Shared API",
            "kind": "person", "customer_import_ids": ["multi-a", "multi-b"],
            "phones": [{"number": "12345678"}]}]}
        url = "/api/v1/imports/contacts/"
        preview = self.post_json(f"{url}preview/", {"document": document}).json()
        self.assertEqual(preview["counts"]["create"], 1)
        result = self.post_json(f"{url}execute/", {"confirm": True,
            "confirmation_token": preview["confirmation_token"]})
        self.assertEqual(result.status_code, 200, result.content)
        person = Contact.objects.get(import_id="multi-person")
        self.assertEqual(ContactCustomer.objects.filter(contact=person, is_active=True).count(), 2)
        self.assertEqual(self.post_json(f"{url}preview/", {"document": document}).json()[
            "counts"]["unchanged"], 1)

    def test_import_execute_rolls_back_when_audit_fails(self):
        self.login("Administrator")
        document = {"schema_version": 1, "customers": [
            {"import_id": "rollback-one", "name": "Rollback One"},
            {"import_id": "rollback-two", "name": "Rollback Two"}]}
        preview = self.post_json("/api/v1/imports/customers/preview/", {"document": document}).json()
        with patch("apps.customers.imports.record_import_summary", side_effect=RuntimeError("test audit failure")):
            with self.assertRaises(RuntimeError):
                self.post_json("/api/v1/imports/customers/execute/", {"confirm": True,
                    "confirmation_token": preview["confirmation_token"]})
        self.assertFalse(Customer.objects.filter(import_id__in=["rollback-one", "rollback-two"]).exists())

    def test_customer_activity_and_credential_scopes(self):
        self.login("Viewer")
        response = self.client.get(f"/api/v1/customers/{self.customer.pk}/activity/", secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.json()["count"], 0)
        self.login("Administrator")
        expiry = timezone.now() + timedelta(days=1)
        _, read_token = issue_credential(actor=self.users["Administrator"],
            user=self.users["Administrator"], name="Read only", scopes=["read"], expires_at=expiry)
        read_client = Client(HTTP_AUTHORIZATION=f"Bearer {read_token}")
        self.assertEqual(read_client.get("/api/v1/audit/", secure=True).status_code, 403)
        self.assertEqual(read_client.get("/api/v1/cleanup/archived-customers/", secure=True).status_code, 403)
        _, audit_token = issue_credential(actor=self.users["Administrator"],
            user=self.users["Administrator"], name="Audit only", scopes=["audit"], expires_at=expiry)
        audit_client = Client(HTTP_AUTHORIZATION=f"Bearer {audit_token}")
        self.assertEqual(audit_client.get("/api/v1/audit/", secure=True).status_code, 200)
        self.assertEqual(audit_client.get("/api/v1/customers/", secure=True).status_code, 403)

    def test_credentials_are_scoped_expiring_revocable_and_session_csrf(self):
        self.login("Administrator")
        expiry = (timezone.now() + timedelta(days=1)).isoformat()
        response = self.post_json("/api/v1/credentials/", {"user_id": self.users["Editor"].pk,
            "name": "Automation", "scopes": ["read"], "expires_at": expiry})
        self.assertEqual(response.status_code, 201, response.content)
        identifier, token = response.json()["id"], response.json()["token"]
        self.assertNotEqual(APICredential.objects.get(pk=identifier).secret_hash, token)
        api_client = Client(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(api_client.get("/api/v1/customers/", secure=True).status_code, 200)
        self.assertEqual(api_client.post("/api/v1/customers/", json.dumps({"name": "No"}),
            content_type="application/json", secure=True).status_code, 403)
        rotated = self.post_json(f"/api/v1/credentials/{identifier}/rotate/", {})
        self.assertEqual(rotated.status_code, 200)
        self.assertEqual(api_client.get("/api/v1/customers/", secure=True).status_code, 401)
        self.assertEqual(Client(HTTP_AUTHORIZATION=f"Bearer {rotated.json()['token']}").get(
            "/api/v1/customers/", secure=True).status_code, 200)
        self.assertEqual(self.post_json(f"/api/v1/credentials/{identifier}/revoke/", {}).status_code, 200)
        self.assertEqual(Client(HTTP_AUTHORIZATION=f"Bearer {rotated.json()['token']}").get(
            "/api/v1/customers/", secure=True).status_code, 401)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.users["Editor"])
        self.assertEqual(csrf_client.post("/api/v1/customers/", json.dumps({"name": "CSRF"}),
            content_type="application/json", secure=True).status_code, 403)

    def test_dashboard_counts_and_no_hard_delete(self):
        self.login("Viewer")
        summary = self.client.get("/api/v1/dashboard/", secure=True).json()
        self.assertEqual(summary, {"active_customers": 2, "active_contacts": 1, "active_assignments": 1})
        directory = self.client.get("/api/v1/directory/", {"customer_q": "Alpha", "page_size": 1},
                                    secure=True).json()
        self.assertEqual(directory["count"], 1)
        self.assertEqual(directory["results"][0]["customer"]["id"], str(self.customer.pk))
        self.assertEqual(directory["results"][0]["contacts"][0]["id"], str(self.contact.pk))
        self.assertEqual(directory["results"][0]["services"][0]["id"], str(self.service.pk))
        self.assertEqual(self.client.get("/api/v1/directory/", {"page_size": 101}, secure=True).status_code, 400)
        self.assertEqual(self.client.delete(f"/api/v1/contacts/{self.contact.pk}/", secure=True).status_code, 405)
        self.assertEqual(self.client.delete(f"/api/v1/services/{self.service.pk}/", secure=True).status_code, 405)
