"""Contact write boundary. Memberships and contact detail edits are atomic."""
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.audit import services as audit
from apps.customers.models import Customer

from .models import Contact, ContactCustomer, ContactPoint
from .permissions import require_access
from .selectors import active_customer_ids, is_associated


def _contact(customer_id, contact_id):
    contact = Contact.objects.select_for_update().get(pk=contact_id)
    if not is_associated(contact, customer_id):
        raise ValidationError("Contact not found for this customer.")
    return contact


def _point(contact, point_id):
    try:
        return ContactPoint.objects.get(pk=point_id, customer_id=contact.customer_id if contact else None,
                                        contact_id=contact.pk if contact else None)
    except ContactPoint.DoesNotExist:
        raise ValidationError("Contact detail not found for this owner.") from None


def _general_point(customer_id, point_id):
    try:
        return ContactPoint.objects.get(pk=point_id, customer_id=customer_id, contact__isnull=True)
    except ContactPoint.DoesNotExist:
        raise ValidationError("Contact detail not found for this owner.") from None


def _customer_ids(ids):
    result = {value.pk if isinstance(value, Customer) else value for value in ids}
    if not result or Customer.objects.filter(pk__in=result).count() != len(result):
        raise ValidationError({"customers": "Select at least one existing customer."})
    return result


def _record_contact(actor, contact, before=None):
    for customer_id in active_customer_ids(contact):
        audit.record_change(actor=actor, instance=contact, before=before, customer_id_override=customer_id)


def _record_point(actor, point, before=None):
    customer_ids = active_customer_ids(point.contact) if point.contact_id else [point.customer_id]
    for customer_id in customer_ids:
        audit.record_change(actor=actor, instance=point, before=before, customer_id_override=customer_id)


def _set_links(actor, contact, ids):
    target = _customer_ids(ids)
    # The contact lock is held by every caller. New links and restorations are
    # serialized with removal and contact-detail changes.
    existing = {link.customer_id: link for link in ContactCustomer.objects.filter(contact=contact)}
    if not existing:
        # Compatibility for old ORM-created rows, including tests. The real
        # upgrade backfills every persisted preexisting contact before use.
        existing[contact.customer_id] = ContactCustomer.objects.create(contact=contact, customer_id=contact.customer_id)
    for customer_id in target - existing.keys():
        link = ContactCustomer.objects.create(contact=contact, customer_id=customer_id)
        audit.record_change(actor=actor, instance=link)
    for customer_id, link in existing.items():
        desired = customer_id in target
        if link.is_active != desired:
            before = audit.snapshot(link)
            link.is_active = desired
            link.full_clean()
            link.save(update_fields=["is_active", "updated_at"])
            audit.record_change(actor=actor, instance=link, before=before)
    return contact


@transaction.atomic
def create_contact(*, actor, customer_id, full_name, job_title="", department="", contact_type=Contact.Type.OTHER,
                   notes="", customer_ids=None, customers=None):
    require_access(actor, "contacts.add_contact")
    if customer_ids is None and customers:
        customer_ids = customers
    selected = _customer_ids(customer_ids if customer_ids is not None else [customer_id])
    if customer_id not in selected:
        raise ValidationError({"customers": "Include the selected customer."})
    Customer.objects.select_for_update().get(pk=customer_id)
    contact = Contact(customer_id=customer_id, full_name=full_name, job_title=job_title,
                      department=department, contact_type=contact_type, notes=notes)
    contact.full_clean()
    contact.save()
    initial_link = ContactCustomer.objects.create(contact=contact, customer_id=customer_id)
    _record_contact(actor, contact)
    audit.record_change(actor=actor, instance=initial_link)
    if len(selected) > 1:
        _set_links(actor, contact, selected)
    return contact


@transaction.atomic
def update_contact(*, actor, customer_id, contact_id, full_name, job_title="", department="", contact_type=Contact.Type.OTHER,
                   notes="", customer_ids=None, customers=None):
    require_access(actor, "contacts.change_contact")
    if customer_ids is None and customers:
        customer_ids = customers
    contact = _contact(customer_id, contact_id)
    before = audit.snapshot(contact)
    contact.full_name, contact.job_title, contact.department = full_name, job_title, department
    contact.contact_type, contact.notes = contact_type, notes
    contact.full_clean()
    contact.save()
    _record_contact(actor, contact, before)
    if customer_ids is not None:
        _set_links(actor, contact, customer_ids)
    return contact


@transaction.atomic
def set_contact_customers(*, actor, customer_id, contact_id, customer_ids):
    require_access(actor, "contacts.change_contact")
    contact = _contact(customer_id, contact_id)
    return _set_links(actor, contact, customer_ids)


@transaction.atomic
def set_contact_active(*, actor, customer_id, contact_id, is_active):
    require_access(actor, "contacts.change_contact")
    contact = _contact(customer_id, contact_id)
    if contact.is_active != is_active:
        before = audit.snapshot(contact)
        contact.is_active = is_active
        contact.full_clean()
        contact.save(update_fields=["is_active", "updated_at"])
        _record_contact(actor, contact, before)
    return contact


@transaction.atomic
def save_contact_point(*, actor, customer_id, contact_id=None, point_id=None,
                       kind, value, label=ContactPoint.Label.OTHER, is_primary=False):
    require_access(actor, "contacts.change_contactpoint" if point_id else "contacts.add_contactpoint")
    contact = _contact(customer_id, contact_id) if contact_id else None
    if not contact:
        Customer.objects.select_for_update().get(pk=customer_id)
    owner_id = contact.customer_id if contact else customer_id
    point = (_point(contact, point_id) if contact else _general_point(customer_id, point_id)) if point_id else ContactPoint(customer_id=owner_id, contact=contact)
    before = audit.snapshot(point) if point_id else None
    point.kind, point.value, point.label, point.is_primary = kind, value, label, is_primary
    point.full_clean(validate_constraints=False)
    if point.is_active and point.is_primary:
        previous = ContactPoint.objects.filter(customer_id=owner_id, contact=contact, kind=kind,
                                               is_active=True, is_primary=True).exclude(pk=point.pk)
        if previous.exists():
            require_access(actor, "contacts.change_contactpoint")
            for old_primary in previous:
                previous_state = audit.snapshot(old_primary)
                old_primary.is_primary = False
                old_primary.save(update_fields=["is_primary", "updated_at"])
                _record_point(actor, old_primary, previous_state)
    point.full_clean()
    point.save()
    _record_point(actor, point, before)
    return point


@transaction.atomic
def set_point_active(*, actor, customer_id, point_id, contact_id=None, is_active):
    require_access(actor, "contacts.change_contactpoint")
    contact = _contact(customer_id, contact_id) if contact_id else None
    if not contact:
        Customer.objects.select_for_update().get(pk=customer_id)
    point = _point(contact, point_id) if contact else _general_point(customer_id, point_id)
    if point.is_active != is_active:
        before = audit.snapshot(point)
        point.is_active = is_active
        point.is_primary = False
        point.full_clean()
        point.save(update_fields=["is_active", "is_primary", "updated_at"])
        _record_point(actor, point, before)
    return point
