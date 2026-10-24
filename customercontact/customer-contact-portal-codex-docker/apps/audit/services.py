"""Audit write boundary: synchronous metadata-only events in business transactions.

Snapshots are ephemeral and never persisted. Descriptions and field names come
from this allowlist; callers cannot supply free text or old/new field values.
"""
from django.core.exceptions import PermissionDenied
from django.db import connection

from .models import AuditEvent

TRACKED_FIELDS = {
    "customers.customer": ("name", "reference_code", "status", "address", "notes"),
    "contacts.contact": ("customer_id", "full_name", "job_title", "department", "contact_type", "notes", "is_active"),
    "contacts.contactpoint": ("customer_id", "contact_id", "kind", "label", "value", "is_primary", "is_active"),
    "contacts.contactcustomer": ("customer_id", "contact_id", "is_active"),
    "services.service": ("name", "description", "category", "is_active"),
    "services.customerservice": ("customer_id", "service_id", "status", "start_date", "end_date", "notes"),
}
OBJECT_TYPES = {
    "customers.customer": "customer", "contacts.contact": "contact", "contacts.contactpoint": "contact_point",
    "contacts.contactcustomer": "contact_customer",
    "services.service": "service", "services.customerservice": "customer_service",
}


def snapshot(instance):
    return {field: getattr(instance, field) for field in TRACKED_FIELDS[instance._meta.label_lower]}


def record_change(*, actor, instance, before=None, customer_id_override=None):
    """Call after save inside the owning write transaction. Errors must propagate."""
    if not connection.in_atomic_block:
        raise RuntimeError("Audit recording requires the business transaction.")
    if not actor.is_authenticated or not actor.is_active or not actor.has_perms(("accounts.access_portal", "accounts.edit_portal")):
        raise PermissionDenied
    after = snapshot(instance)
    changed = sorted(after if before is None else [field for field in after if before[field] != after[field]])
    if not changed:
        return None
    object_type = OBJECT_TYPES[instance._meta.label_lower]
    if before is None:
        action = "assigned" if object_type == "customer_service" else "created"
    elif "is_active" in changed:
        action = "restored" if after["is_active"] else "archived"
    elif "status" in changed and object_type == "customer":
        action = "restored" if after["status"] == "active" else "archived"
    elif "status" in changed and object_type == "customer_service":
        action = {"active": "activated", "suspended": "suspended", "expired": "expired", "terminated": "terminated"}[after["status"]]
    else:
        action = "updated"
    customer_id = instance.pk if object_type == "customer" else getattr(instance, "customer_id", None)
    if customer_id_override is not None and object_type in ("contact", "contact_point"):
        customer_id = customer_id_override
    description = f"{AuditEvent.ObjectType(object_type).label} {AuditEvent.Action(action).label.lower()}."
    return AuditEvent.objects.create(actor=actor, action=action, object_type=object_type, object_id=instance.pk,
                                     customer_id=customer_id, description=description, changed_fields=changed)
