"""Public, permission-checked contact writes; no signals or cross-app mutations.

Lock the customer row first for every mutation to serialize primary selection,
including general details. Customer rows are read/locked, never modified here.
Owners are immutable; all IDs are checked against their customer on every call.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.customers.models import Customer

from .models import Contact, ContactPoint
from .permissions import require_access


def _lock_customer(customer_id):
    return Customer.objects.select_for_update().get(pk=customer_id)


def _contact(customer_id, contact_id):
    try:
        return Contact.objects.get(pk=contact_id, customer_id=customer_id)
    except Contact.DoesNotExist:
        raise ValidationError("Contact not found for this customer.") from None


def _point(customer_id, contact_id, point_id):
    try:
        return ContactPoint.objects.get(pk=point_id, customer_id=customer_id, contact_id=contact_id)
    except ContactPoint.DoesNotExist:
        raise ValidationError("Contact detail not found for this owner.") from None


@transaction.atomic
def create_contact(*, actor, customer_id, full_name, job_title="", department="", contact_type=Contact.Type.OTHER, notes=""):
    require_access(actor, "contacts.add_contact")
    _lock_customer(customer_id)
    contact = Contact(customer_id=customer_id, full_name=full_name, job_title=job_title,
                      department=department, contact_type=contact_type, notes=notes)
    contact.full_clean()
    contact.save()
    return contact


@transaction.atomic
def update_contact(*, actor, customer_id, contact_id, full_name, job_title="", department="", contact_type=Contact.Type.OTHER, notes=""):
    require_access(actor, "contacts.change_contact")
    _lock_customer(customer_id)
    contact = _contact(customer_id, contact_id)
    contact.full_name, contact.job_title, contact.department = full_name, job_title, department
    contact.contact_type, contact.notes = contact_type, notes
    contact.full_clean()
    contact.save()
    return contact


@transaction.atomic
def set_contact_active(*, actor, customer_id, contact_id, is_active):
    require_access(actor, "contacts.change_contact")
    _lock_customer(customer_id)
    contact = _contact(customer_id, contact_id)
    if contact.is_active != is_active:
        contact.is_active = is_active
        contact.full_clean()
        contact.save(update_fields=["is_active", "updated_at"])
    return contact


@transaction.atomic
def save_contact_point(*, actor, customer_id, contact_id=None, point_id=None,
                       kind, value, label=ContactPoint.Label.OTHER, is_primary=False):
    require_access(actor, "contacts.change_contactpoint" if point_id else "contacts.add_contactpoint")
    _lock_customer(customer_id)
    if contact_id:
        _contact(customer_id, contact_id)
    point = _point(customer_id, contact_id, point_id) if point_id else ContactPoint(customer_id=customer_id, contact_id=contact_id)
    point.kind, point.value, point.label, point.is_primary = kind, value, label, is_primary
    # Validate content/ownership before demoting any existing primary.
    point.full_clean(validate_constraints=False)
    if point.is_active and point.is_primary:
        previous = ContactPoint.objects.filter(customer_id=customer_id, contact_id=contact_id, kind=kind,
                                               is_active=True, is_primary=True).exclude(pk=point.pk)
        if previous.exists():
            require_access(actor, "contacts.change_contactpoint")
            previous.update(is_primary=False, updated_at=timezone.now())
    point.full_clean()
    point.save()
    return point


@transaction.atomic
def set_point_active(*, actor, customer_id, point_id, contact_id=None, is_active):
    require_access(actor, "contacts.change_contactpoint")
    _lock_customer(customer_id)
    if contact_id:
        _contact(customer_id, contact_id)
    point = _point(customer_id, contact_id, point_id)
    if point.is_active != is_active:
        point.is_active = is_active
        # Retire the primary designation; restoring does not replace a new primary.
        point.is_primary = False
        point.full_clean()
        point.save(update_fields=["is_active", "is_primary", "updated_at"])
    return point
