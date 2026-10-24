from django.db.models import Q

from apps.contacts.permissions import READ_PERMISSIONS as CONTACT_READ
from apps.services.permissions import READ_PERMISSIONS as SERVICE_READ

from .models import AuditEvent


def visible_events(actor):
    if not actor.is_active or not actor.has_perm("accounts.access_portal"):
        return AuditEvent.objects.none()
    allowed = Q(pk__in=[])
    if actor.has_perm("customers.view_customer"):
        allowed |= Q(object_type="customer")
    if actor.has_perms(CONTACT_READ):
        allowed |= Q(object_type__in=["contact", "contact_point"])
    if actor.has_perm("services.view_service"):
        allowed |= Q(object_type="service")
    if actor.has_perms(SERVICE_READ):
        allowed |= Q(object_type="customer_service")
    return AuditEvent.objects.filter(allowed).select_related("actor", "customer")
