"""Administrator-only permanent cleanup with explicit dependency planning."""
import hashlib
import json
import uuid

from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.db.models.deletion import ProtectedError

from apps.audit.models import AuditEvent
from apps.audit.services import record_cleanup
from apps.contacts.models import Contact, ContactCustomer, ContactPoint
from apps.customers.models import Customer
from apps.services.models import CustomerService

from .models import CleanupOperation

TOKEN_SALT = "portal-cleanup-preview-v1"
MAX_SELECTED = 50


class StaleCleanupPreview(ValidationError):
    """The selected dependency state changed after preview."""


def require_cleanup(actor):
    if not actor.is_authenticated or not actor.is_active or not actor.has_perms((
        "accounts.access_portal", "accounts.administer_portal", "customers.view_customer",
        "contacts.view_contact", "cleanup.view_cleanupoperation", "cleanup.execute_cleanup",
    )):
        raise PermissionDenied


def _ids(values, label):
    if not isinstance(values, list):
        raise ValidationError({label: "Select a list of record IDs."})
    try:
        parsed = [uuid.UUID(str(value)) for value in values]
    except (ValueError, TypeError, AttributeError):
        raise ValidationError({label: "Every ID must be a valid UUID."}) from None
    if len(parsed) != len(set(parsed)):
        raise ValidationError({label: "Select each record only once."})
    return parsed


def cleanup_plan(*, actor, customer_ids, contact_ids):
    require_cleanup(actor)
    customer_ids, contact_ids = _ids(customer_ids, "customer_ids"), _ids(contact_ids, "contact_ids")
    if not customer_ids and not contact_ids:
        raise ValidationError("Select at least one archived customer or contact.")
    if len(customer_ids) + len(contact_ids) > MAX_SELECTED:
        raise ValidationError(f"Select at most {MAX_SELECTED} records at a time.")
    customers = list(Customer.objects.filter(pk__in=customer_ids).order_by("pk"))
    contacts = list(Contact.objects.filter(pk__in=contact_ids).order_by("pk"))
    if len(customers) != len(customer_ids) or len(contacts) != len(contact_ids):
        raise ValidationError("A selected record no longer exists. Preview again.")
    selected_contact_ids = set(contact_ids)
    blockers = []
    for customer in customers:
        if customer.status != Customer.Status.INACTIVE:
            blockers.append({"type": "customer", "id": str(customer.pk), "reason": "Customer is active."})
    for contact in contacts:
        if contact.is_active:
            blockers.append({"type": "contact", "id": str(contact.pk), "reason": "Contact is active."})
    assignments = list(CustomerService.objects.filter(customer_id__in=customer_ids).order_by("id"))
    for assignment in assignments:
        blockers.append({"type": "assignment", "id": str(assignment.pk),
                         "customer_id": str(assignment.customer_id), "reason": "Service agreement history must be retained."})
    original_contacts = list(Contact.objects.filter(customer_id__in=customer_ids).order_by("id"))
    for contact in original_contacts:
        if contact.pk not in selected_contact_ids:
            blockers.append({"type": "contact", "id": str(contact.pk), "customer_id": str(contact.customer_id),
                             "reason": "This customer's original contact must be selected separately while archived."})
    links_to_delete = list(ContactCustomer.objects.filter(contact_id__in=contact_ids).order_by("id"))
    detached_links = list(ContactCustomer.objects.filter(customer_id__in=customer_ids).exclude(
        contact_id__in=contact_ids).order_by("id"))
    points_to_delete = list(ContactPoint.objects.filter(contact_id__in=contact_ids).order_by("id"))
    preserved = list(Contact.objects.filter(pk__in=[link.contact_id for link in detached_links]).order_by("id"))
    audit_refs = AuditEvent.objects.filter(customer_id__in=customer_ids).count()
    state = {
        "audit_refs": audit_refs,
        "customers": [(str(row.pk), row.status, row.updated_at.isoformat()) for row in customers],
        "contacts": [(str(row.pk), str(row.customer_id), row.is_active, row.updated_at.isoformat())
                     for row in sorted({row.pk: row for row in contacts + original_contacts}.values(), key=lambda row: str(row.pk))],
        "assignments": [(str(row.pk), row.status, row.updated_at.isoformat()) for row in assignments],
        "links": [(str(row.pk), str(row.contact_id), str(row.customer_id), row.is_active, row.updated_at.isoformat())
                  for row in sorted({row.pk: row for row in links_to_delete + detached_links}.values(), key=lambda row: str(row.pk))],
        "points": [(str(row.pk), row.kind, row.value, row.is_active, row.updated_at.isoformat())
                   for row in points_to_delete],
    }
    fingerprint = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
    counts = {"customers": len(customers), "contacts": len(contacts), "contact_methods": len(points_to_delete),
              "contact_links_deleted": len(links_to_delete), "contact_links_detached": len(detached_links),
              "contacts_preserved": len(preserved), "audit_events_preserved": audit_refs,
              "service_assignments_blocking": len(assignments)}
    return {
        "customers_to_delete": [{"id": str(row.pk), "name": row.name} for row in customers],
        "contacts_to_delete": [{"id": str(row.pk), "name": row.full_name} for row in contacts],
        "methods_to_delete": [str(row.pk) for row in points_to_delete],
        "links_to_delete": [str(row.pk) for row in links_to_delete],
        "links_to_detach": [{"id": str(row.pk), "contact_id": str(row.contact_id),
                             "customer_id": str(row.customer_id)} for row in detached_links],
        "contacts_preserved": [{"id": str(row.pk), "name": row.full_name} for row in preserved],
        "blockers": blockers, "counts": counts, "fingerprint": fingerprint,
        "customer_ids": [str(value) for value in sorted(customer_ids)],
        "contact_ids": [str(value) for value in sorted(contact_ids)],
    }


def preview_cleanup(*, actor, customer_ids, contact_ids):
    plan = cleanup_plan(actor=actor, customer_ids=customer_ids, contact_ids=contact_ids)
    reference = uuid.uuid4()
    token = None
    if not plan["blockers"]:
        token = signing.dumps({"actor": str(actor.pk), "reference": str(reference),
            "customer_ids": plan["customer_ids"], "contact_ids": plan["contact_ids"],
            "fingerprint": plan["fingerprint"]}, salt=TOKEN_SALT, compress=True)
    return {"plan": plan, "confirmation_ref": str(reference), "confirmation_token": token}


def _open_token(token, actor):
    try:
        data = signing.loads(token, salt=TOKEN_SALT, max_age=900)
        if not isinstance(data, dict) or data.get("actor") != str(actor.pk):
            raise signing.BadSignature
        uuid.UUID(data["reference"])
        if CleanupOperation.objects.filter(confirmation_ref=data["reference"]).exists():
            raise signing.BadSignature
        return data
    except (signing.BadSignature, signing.SignatureExpired, KeyError, ValueError, TypeError):
        raise ValidationError("The cleanup preview expired or is invalid. Preview again.") from None


@transaction.atomic
def _perform_cleanup(*, actor, preview):
    customer_ids, contact_ids = preview["customer_ids"], preview["contact_ids"]
    list(Customer.objects.select_for_update().filter(pk__in=customer_ids))
    list(Contact.objects.select_for_update().filter(pk__in=contact_ids))
    list(ContactCustomer.objects.select_for_update().filter(
        customer_id__in=customer_ids) | ContactCustomer.objects.select_for_update().filter(contact_id__in=contact_ids))
    list(ContactPoint.objects.select_for_update().filter(contact_id__in=contact_ids))
    list(CustomerService.objects.select_for_update().filter(customer_id__in=customer_ids))
    plan = cleanup_plan(actor=actor, customer_ids=customer_ids, contact_ids=contact_ids)
    if plan["blockers"] or plan["fingerprint"] != preview["fingerprint"]:
        raise StaleCleanupPreview("The cleanup preview is stale or blocked. Preview again.")
    ContactPoint.objects.filter(pk__in=plan["methods_to_delete"]).delete()
    ContactCustomer.objects.filter(pk__in=plan["links_to_delete"]).delete()
    ContactCustomer.objects.filter(pk__in=[row["id"] for row in plan["links_to_detach"]]).delete()
    Contact.objects.filter(pk__in=contact_ids).delete()
    Customer.objects.filter(pk__in=customer_ids).delete()
    operation = CleanupOperation.objects.create(
        actor=actor, confirmation_ref=uuid.UUID(preview["reference"]), result=CleanupOperation.Result.COMPLETED,
        customer_ids=customer_ids, contact_ids=contact_ids, counts=plan["counts"],
    )
    record_cleanup(actor=actor, operation=operation)
    return operation


def confirm_cleanup(*, actor, token, confirm):
    require_cleanup(actor)
    if confirm is not True:
        raise ValidationError("Explicit confirmation is required.")
    preview = _open_token(token, actor)
    try:
        return _perform_cleanup(actor=actor, preview=preview)
    except (ValidationError, ProtectedError, DatabaseError) as error:
        # A rejected confirmation is recorded after the business transaction rolls back.
        # If recording itself fails, propagate that failure; no deletion has committed.
        with transaction.atomic():
            operation = CleanupOperation.objects.create(
                actor=actor, confirmation_ref=uuid.UUID(preview["reference"]), result=CleanupOperation.Result.FAILED,
                customer_ids=preview["customer_ids"], contact_ids=preview["contact_ids"], counts={},
                error_code="stale" if isinstance(error, ValidationError) else "protected" if isinstance(error, ProtectedError) else "database",
            )
            record_cleanup(actor=actor, operation=operation)
        raise
