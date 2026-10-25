import importlib
from types import SimpleNamespace
import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.customers.models import Customer
from .models import Contact, ContactCustomer, ContactPoint
from .services import create_contact, set_contact_customers, update_contact, save_contact_point, set_contact_active

User = get_user_model()


class SharedContactTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.users = {}
        for role in ("Viewer", "Editor", "Administrator"):
            user = User.objects.create_user(username=role.lower())
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.first = Customer.objects.create(name="Acme One")
        cls.second = Customer.objects.create(name="Beacon Two")
        cls.third = Customer.objects.create(name="Cedar Three")
        cls.person = create_contact(actor=cls.users["Editor"], customer_id=cls.first.pk, full_name="Shared Person", notes="Private note",
                                    methods=[{"kind": "email", "value": "shared@example.invalid", "is_primary": True}])
        cls.email = cls.person.points.get(kind="email")

    def test_add_second_customer_reuses_record_and_preserves_details(self):
        person_before = Contact.objects.values().get(pk=self.person.pk)
        point_before = ContactPoint.objects.values().get(pk=self.email.pk)
        set_contact_customers(actor=self.users["Editor"], customer_id=self.first.pk, contact_id=self.person.pk,
                              customer_ids=[self.first.pk, self.second.pk])
        self.assertEqual(Contact.objects.count(), 1)
        self.assertEqual(ContactCustomer.objects.filter(contact=self.person, is_active=True).count(), 2)
        self.assertEqual(AuditEvent.objects.get(object_type="contact_customer", customer=self.first, action="created").actor_id,
                         self.users["Editor"].pk)
        self.assertEqual(Contact.objects.values().get(pk=self.person.pk), person_before)
        self.assertEqual(ContactPoint.objects.values().get(pk=self.email.pk), point_before)
        self.client.force_login(self.users["Viewer"])
        for customer in (self.first, self.second):
            self.assertContains(self.client.get(reverse("contacts:list", args=[customer.pk]), secure=True),
                                reverse("contacts:detail", args=[customer.pk, self.person.pk]))
            self.assertContains(self.client.get(reverse("contacts:detail", args=[customer.pk, self.person.pk]), secure=True), "shared@example.invalid")
        self.assertEqual(AuditEvent.objects.get(object_type="contact_customer", customer=self.second).actor_id,
                         self.users["Editor"].pk)

    def test_remove_original_customer_retains_contact_and_old_detail_owner(self):
        actor = self.users["Editor"]
        set_contact_customers(actor=actor, customer_id=self.first.pk, contact_id=self.person.pk,
                              customer_ids=[self.first.pk, self.second.pk])
        set_contact_customers(actor=actor, customer_id=self.first.pk, contact_id=self.person.pk,
                              customer_ids=[self.second.pk])
        self.person.refresh_from_db()
        self.email.refresh_from_db()
        self.assertEqual(self.person.customer_id, self.first.pk)
        self.assertEqual(self.email.customer_id, self.first.pk)
        self.assertEqual(self.person.get_absolute_url(), reverse("contacts:detail", args=[self.second.pk, self.person.pk]))
        self.client.force_login(self.users["Viewer"])
        self.assertNotContains(self.client.get(reverse("contacts:list", args=[self.first.pk]), secure=True), "Shared Person")
        self.assertContains(self.client.get(reverse("contacts:list", args=[self.second.pk]), secure=True), "Shared Person")
        stale = self.client.get(reverse("contacts:detail", args=[self.first.pk, self.person.pk]), secure=True)
        self.assertEqual(stale.status_code, 302)
        self.assertEqual(stale.url, self.person.get_absolute_url())
        self.client.force_login(actor)
        self.assertEqual(self.client.post(reverse("contacts:edit", args=[self.first.pk, self.person.pk]), {}, secure=True).status_code, 404)
        self.client.force_login(self.users["Viewer"])
        self.assertContains(self.client.get(self.person.get_absolute_url(), secure=True), "shared@example.invalid")
        self.assertEqual(AuditEvent.objects.filter(object_type="contact_customer", customer=self.first, action="archived").count(), 1)

    def test_duplicate_links_blocked_and_last_association_cannot_be_removed(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContactCustomer.objects.create(contact=self.person, customer=self.first)
        with self.assertRaises(ValidationError):
            set_contact_customers(actor=self.users["Editor"], customer_id=self.first.pk, contact_id=self.person.pk, customer_ids=[])
        self.assertEqual(ContactCustomer.objects.filter(contact=self.person, is_active=True).count(), 1)
        set_contact_customers(actor=self.users["Editor"], customer_id=self.first.pk, contact_id=self.person.pk,
                              customer_ids=[self.first.pk, self.second.pk])
        set_contact_customers(actor=self.users["Editor"], customer_id=self.first.pk, contact_id=self.person.pk,
                              customer_ids=[self.first.pk])
        link = ContactCustomer.objects.get(contact=self.person, customer=self.second)
        self.assertFalse(link.is_active)
        set_contact_customers(actor=self.users["Editor"], customer_id=self.first.pk, contact_id=self.person.pk,
                              customer_ids=[self.first.pk, self.second.pk])
        self.assertEqual(ContactCustomer.objects.filter(contact=self.person, customer=self.second).count(), 1)
        self.assertTrue(ContactCustomer.objects.get(pk=link.pk).is_active)

    def test_shared_detail_write_keeps_origin_and_audits_each_current_customer(self):
        actor = self.users["Editor"]
        set_contact_customers(actor=actor, customer_id=self.first.pk, contact_id=self.person.pk,
                              customer_ids=[self.first.pk, self.second.pk])
        value = "new@example.invalid"
        changed = save_contact_point(actor=actor, customer_id=self.second.pk, contact_id=self.person.pk, point_id=self.email.pk,
                                     kind="email", value=value, is_primary=True)
        self.assertEqual(changed.customer_id, self.first.pk)
        events = AuditEvent.objects.filter(object_type="contact_point", object_id=self.email.pk, action="updated")
        self.assertCountEqual(events.values_list("customer_id", flat=True), [self.first.pk, self.second.pk])
        self.assertNotIn(value, str(list(events.values("description", "changed_fields"))))
        self.client.force_login(self.users["Viewer"])
        self.assertContains(self.client.get(reverse("contacts:detail", args=[self.second.pk, self.person.pk]), secure=True), value)
        self.assertEqual(self.client.get(reverse("contacts:detail", args=[self.third.pk, self.person.pk]), secure=True).status_code, 404)

    def test_shared_contact_metadata_archive_and_restore_audited_for_each_customer(self):
        actor = self.users["Editor"]
        set_contact_customers(actor=actor, customer_id=self.first.pk, contact_id=self.person.pk,
                              customer_ids=[self.first.pk, self.second.pk])
        update_contact(actor=actor, customer_id=self.second.pk, contact_id=self.person.pk, full_name="Updated shared", notes="New private note")
        set_contact_active(actor=actor, customer_id=self.second.pk, contact_id=self.person.pk, is_active=False)
        set_contact_active(actor=actor, customer_id=self.second.pk, contact_id=self.person.pk, is_active=True)
        for action in ("updated", "archived", "restored"):
            self.assertEqual(AuditEvent.objects.filter(object_type="contact", object_id=self.person.pk, action=action).count(), 2)
        self.assertNotIn("New private note", str(list(AuditEvent.objects.filter(object_id=self.person.pk).values("description", "changed_fields"))))

    def test_global_list_search_filter_pagination_and_roles(self):
        for i in range(27):
            Contact.objects.create(customer=self.first, full_name=f"Page Person {i:02}")
        self.client.force_login(self.users["Viewer"])
        url = reverse("global_contacts:list")
        response = self.client.get(url, {"q": "page", "page": 2}, secure=True)
        self.assertEqual(response.context["page_obj"].paginator.count, 27)
        self.assertEqual(len(response.context["page_obj"]), 2)
        self.assertContains(response, "Page 2 of 2")
        self.assertContains(response, "q=page&amp;status=active")
        self.assertEqual(self.client.get(reverse("global_contacts:create"), secure=True).status_code, 403)
        self.assertEqual(self.client.post(reverse("global_contacts:create"), {"full_name": "No"}, secure=True).status_code, 403)
        for role in ("Editor", "Administrator"):
            self.client.force_login(self.users[role])
            self.assertEqual(self.client.get(url, secure=True).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(url, secure=True).status_code, 302)

    def test_global_search_by_email_phone_customer_and_type(self):
        editor = self.users["Editor"]
        save_contact_point(actor=editor, customer_id=self.first.pk, contact_id=self.person.pk,
                           kind="phone", value="+45 12 34 56 78")
        self.client.force_login(self.users["Viewer"])
        url = reverse("global_contacts:list")
        for query in ("Shared Person", "shared@example.invalid", "12345678", "Acme One"):
            response = self.client.get(url, {"q": query}, secure=True)
            self.assertEqual(response.context["page_obj"].paginator.count, 1)
            self.assertContains(response, self.person.full_name)
        self.assertEqual(self.client.get(url, {"contact_type": "technical"}, secure=True).context["page_obj"].paginator.count, 1)
        set_contact_active(actor=editor, customer_id=self.first.pk, contact_id=self.person.pk, is_active=False)
        self.assertEqual(self.client.get(url, secure=True).context["page_obj"].paginator.count, 0)
        self.assertEqual(self.client.get(url, {"status": "archived"}, secure=True).context["page_obj"].paginator.count, 1)

    def test_global_create_edit_and_status_workflow(self):
        self.client.force_login(self.users["Editor"])
        create_url = reverse("global_contacts:create")
        self.assertEqual(self.client.post(create_url, {"full_name": "No owner"}, secure=True).status_code, 200)
        response = self.client.post(create_url, {"full_name": "Global Person", "customers": [self.first.pk, self.second.pk],
            "methods-TOTAL_FORMS": "1", "methods-INITIAL_FORMS": "0", "methods-MIN_NUM_FORMS": "0",
            "methods-MAX_NUM_FORMS": "1000", "methods-0-kind": "phone", "methods-0-value": "12345678"}, secure=True)
        self.assertEqual(response.status_code, 302)
        person = Contact.objects.get(full_name="Global Person")
        self.assertEqual(ContactCustomer.objects.filter(contact=person, is_active=True).count(), 2)
        edit_url = reverse("contacts:edit", args=[self.first.pk, person.pk])
        response = self.client.post(edit_url, {"full_name": "Renamed Person", "customers": [self.second.pk],
                                                    "customers_present": "1", "job_title": "Architect"}, secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("contacts:detail", args=[self.second.pk, person.pk]))
        person.refresh_from_db()
        self.assertEqual(person.job_title, "Architect")
        self.assertFalse(ContactCustomer.objects.get(contact=person, customer=self.first).is_active)
        self.assertEqual(self.client.get(reverse("global_contacts:detail", args=[person.pk]), secure=True).status_code, 302)
        self.assertEqual(self.client.get(reverse("global_contacts:archive", args=[person.pk]), secure=True).status_code, 302)
        self.assertEqual(self.client.post(reverse("global_contacts:archive", args=[person.pk]), secure=True).status_code, 405)
        self.assertEqual(self.client.post(reverse("contacts:archive", args=[self.second.pk, person.pk]), secure=True).status_code, 302)
        self.assertEqual(self.client.post(reverse("contacts:restore", args=[self.second.pk, person.pk]), secure=True).status_code, 302)

    def test_invalid_association_change_rolls_back_contact_edit_and_audit(self):
        actor = self.users["Editor"]
        before = (self.person.full_name, AuditEvent.objects.count())
        with self.assertRaises(ValidationError):
            update_contact(actor=actor, customer_id=self.first.pk, contact_id=self.person.pk,
                           full_name="Should rollback", customer_ids=[self.third.pk, uuid.uuid4()])
        self.person.refresh_from_db()
        self.assertEqual((self.person.full_name, AuditEvent.objects.count()), before)

    def test_migration_backfill_preserves_all_legacy_links_and_points(self):
        # Exercise the actual RunPython forward function with historical model
        # state, without downgrading a populated test database.
        raw = Contact.objects.create(customer=self.third, full_name="Raw legacy", is_active=False)
        point = ContactPoint.objects.create(customer=self.third, contact=raw, kind="email",
                                            value="legacy@example.invalid", normalized_value="legacy@example.invalid")
        before = (Contact.objects.values().get(pk=raw.pk), ContactPoint.objects.values().get(pk=point.pk))
        ContactCustomer.objects.filter(contact=self.person).delete()
        migration = importlib.import_module("apps.contacts.migrations.0003_contact_customers")
        from django.db.migrations.executor import MigrationExecutor
        old_apps = MigrationExecutor(connection).loader.project_state([("contacts", "0003_contact_customers")]).apps
        migration.backfill_legacy_links(old_apps, SimpleNamespace(connection=connection))
        self.assertEqual(ContactCustomer.objects.get(contact=raw).customer_id, self.third.pk)
        self.assertEqual(ContactCustomer.objects.get(contact=self.person).customer_id, self.first.pk)
        self.assertTrue(ContactCustomer.objects.get(contact=raw).is_active)
        self.assertEqual((Contact.objects.values().get(pk=raw.pk), ContactPoint.objects.values().get(pk=point.pk)), before)
