"""Customer and global interfaces use the same associated contact records."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.customers.models import Customer
from apps.services.models import CustomerService, Service

from .models import Contact, ContactCustomer, ContactPoint
from .services import save_contact_point


class UnifiedContactWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.users = {}
        for role in ("Viewer", "Editor", "Administrator"):
            user = get_user_model().objects.create_user(username=f"unified-{role.lower()}")
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.first = Customer.objects.create(name="Unified Alpha")
        cls.second = Customer.objects.create(name="Unified Bravo")
        cls.service = Service.objects.create(name="Unified Monitoring")
        for customer in (cls.first, cls.second):
            CustomerService.objects.create(customer=customer, service=cls.service)

    def create_desk(self):
        self.client.force_login(self.users["Editor"])
        response = self.client.post(reverse("contacts:create", args=[self.first.pk]), {
            "full_name": "Support Desk", "is_general": "on", "contact_type": "support",
            "customers_present": "1", "customers": [str(self.first.pk)],
        }, secure=True)
        self.assertEqual(response.status_code, 302)
        person = Contact.objects.get(full_name="Support Desk")
        self.assertTrue(person.is_general)
        self.assertTrue(ContactCustomer.objects.get(contact=person, customer=self.first).is_active)
        return person

    def test_customer_create_global_edit_and_contact_details_are_shared(self):
        person = self.create_desk()
        self.assertContains(self.client.get(reverse("global_contacts:list"), secure=True), person.full_name)
        self.assertContains(self.client.get(reverse("contacts:list", args=[self.first.pk]), secure=True), person.full_name)
        edit = self.client.get(reverse("global_contacts:edit", args=[person.pk]), secure=True)
        self.assertEqual(edit.status_code, 302)
        self.assertEqual(edit.url, reverse("contacts:edit", args=[self.first.pk, person.pk]))
        response = self.client.post(edit.url, {
            "full_name": "Support Desk Updated", "is_general": "on", "contact_type": "support",
            "notes": "Synthetic internal note", "customers_present": "1", "customers": [str(self.first.pk)],
        }, secure=True)
        self.assertEqual(response.status_code, 302)
        person.refresh_from_db()
        self.assertEqual(person.full_name, "Support Desk Updated")
        self.assertTrue(person.is_general)
        self.assertContains(self.client.get(reverse("contacts:list", args=[self.first.pk]), secure=True), person.full_name)
        self.assertContains(self.client.get(self.first.get_absolute_url(), secure=True), person.full_name)

        add_detail = reverse("contacts:point_create", args=[self.first.pk, person.pk])
        for kind, value in (("email", "desk@example.invalid"), ("email", "team@example.invalid"),
                            ("phone", "+45 12 34 56 78"), ("phone", "+45 87 65 43 21")):
            self.assertEqual(self.client.post(add_detail, {"kind": kind, "value": value}, secure=True).status_code, 302)
        self.assertEqual(person.points.count(), 4)
        customer_page = self.client.get(reverse("contacts:list", args=[self.first.pk]), secure=True)
        global_page = self.client.get(reverse("global_contacts:list"), secure=True)
        service_page = self.client.get(reverse("search:services"), {"services": [str(self.service.pk)]}, secure=True)
        for value in ("desk@example.invalid", "team@example.invalid", "+45 12 34 56 78", "+45 87 65 43 21"):
            for page in (customer_page, global_page, service_page):
                self.assertContains(page, value)
        exported = self.client.get(reverse("search:service_emails"), {"services": [str(self.service.pk)]}, secure=True).json()
        self.assertEqual(exported["count"], 2)
        self.assertCountEqual(exported["emails"].split("; "), ["desk@example.invalid", "team@example.invalid"])
        self.assertEqual(ContactPoint.objects.filter(contact__isnull=True).count(), 0)

    def test_shared_contact_removal_changes_both_pages_and_email_scope(self):
        person = self.create_desk()
        save_contact_point(actor=self.users["Editor"], customer_id=self.first.pk, contact_id=person.pk,
                           kind="email", value="shared@example.invalid")
        edit = reverse("contacts:edit", args=[self.first.pk, person.pk])
        self.assertEqual(self.client.post(edit, {"full_name": person.full_name, "is_general": "on",
                                                 "customers_present": "1", "customers": [str(self.first.pk), str(self.second.pk)]},
                                          secure=True).status_code, 302)
        for customer in (self.first, self.second):
            self.assertContains(self.client.get(reverse("contacts:list", args=[customer.pk]), secure=True), person.full_name)
        self.assertEqual(Contact.objects.filter(pk=person.pk).count(), 1)
        self.assertEqual(self.client.post(edit, {"full_name": person.full_name, "is_general": "on",
                                                 "customers_present": "1", "customers": [str(self.second.pk)]},
                                          secure=True).status_code, 302)
        self.assertNotContains(self.client.get(reverse("contacts:list", args=[self.first.pk]), secure=True), person.full_name)
        self.assertContains(self.client.get(reverse("contacts:list", args=[self.second.pk]), secure=True), person.full_name)
        self.assertEqual(ContactPoint.objects.get(contact=person).customer_id, self.first.pk)
        self.assertFalse(ContactCustomer.objects.get(contact=person, customer=self.first).is_active)
        self.assertEqual(self.client.get(reverse("search:service_emails"), {"services": [str(self.service.pk)]}, secure=True).json()["count"], 1)

    def test_permissions_and_database_disallow_personless_details(self):
        person = self.create_desk()
        self.client.force_login(self.users["Viewer"])
        self.assertContains(self.client.get(reverse("contacts:list", args=[self.first.pk]), secure=True), "Support Desk")
        self.assertContains(self.client.get(reverse("global_contacts:list"), secure=True), "Support Desk")
        self.assertEqual(self.client.get(reverse("contacts:point_create", args=[self.first.pk, person.pk]), secure=True).status_code, 403)
        self.assertEqual(self.client.post(reverse("contacts:point_create", args=[self.first.pk, person.pk]),
                                          {"kind": "email", "value": "forged@example.invalid"}, secure=True).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("global_contacts:list"), secure=True).status_code, 302)
        with self.assertRaises(ValidationError):
            save_contact_point(actor=self.users["Editor"], customer_id=self.first.pk,
                               kind="email", value="orphan@example.invalid")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContactPoint.objects.create(customer=self.first, contact=None, kind="email",
                                        value="orphan@example.invalid", normalized_value="orphan@example.invalid")
