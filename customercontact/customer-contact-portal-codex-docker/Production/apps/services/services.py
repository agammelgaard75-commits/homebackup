"""Public, permission-checked write API. Catalog and assignments retain history."""
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.customers.models import Customer
from apps.audit import services as audit

from .models import CustomerService, Service
from .permissions import require_access


def _save_catalog(service):
    service.full_clean()
    try:
        with transaction.atomic():
            service.save()
    except IntegrityError as error:
        if getattr(getattr(error.__cause__, "diag", None), "constraint_name", None) == "service_name_unique":
            raise ValidationError({"name": "A service with this name already exists, including archived services."}) from error
        raise
    return service


@transaction.atomic
def create_service(*, actor, name, description="", category=""):
    require_access(actor, "services.add_service", catalog=True)
    service = _save_catalog(Service(name=name, description=description, category=category))
    audit.record_change(actor=actor, instance=service)
    return service


@transaction.atomic
def update_service(*, actor, service_id, name, description="", category=""):
    require_access(actor, "services.change_service", catalog=True)
    service = Service.objects.select_for_update().get(pk=service_id)
    before = audit.snapshot(service)
    service.name, service.description, service.category = name, description, category
    _save_catalog(service)
    audit.record_change(actor=actor, instance=service, before=before)
    return service


@transaction.atomic
def set_service_active(*, actor, service_id, is_active):
    require_access(actor, "services.change_service", catalog=True)
    service = Service.objects.select_for_update().get(pk=service_id)
    if service.is_active != is_active:
        before = audit.snapshot(service)
        service.is_active = is_active
        service.full_clean()
        service.save(update_fields=["is_active", "updated_at"])
        audit.record_change(actor=actor, instance=service, before=before)
    return service


@transaction.atomic
def create_assignment(*, actor, customer_id, service_id, status=CustomerService.Status.ACTIVE,
                      start_date=None, end_date=None, notes=""):
    require_access(actor, "services.add_customerservice")
    # Serializes assignment creation with catalog archive; neither operation can
    # approve an assignment against a stale active flag.
    service = Service.objects.select_for_update().get(pk=service_id)
    if not service.is_active:
        raise ValidationError({"service": "This catalog service is archived. Choose an active service."})
    assignment = CustomerService(customer=Customer.objects.get(pk=customer_id), service=service,
                                 status=status, start_date=start_date, end_date=end_date, notes=notes)
    assignment.full_clean()
    assignment.save()
    audit.record_change(actor=actor, instance=assignment)
    return assignment


@transaction.atomic
def update_assignment(*, actor, customer_id, assignment_id, status, start_date=None, end_date=None, notes=""):
    require_access(actor, "services.change_customerservice")
    assignment = CustomerService.objects.select_for_update().get(pk=assignment_id, customer_id=customer_id)
    before = audit.snapshot(assignment)
    assignment.status, assignment.start_date, assignment.end_date, assignment.notes = status, start_date, end_date, notes
    assignment.full_clean()
    assignment.save()
    audit.record_change(actor=actor, instance=assignment, before=before)
    return assignment


@transaction.atomic
def terminate_assignment(*, actor, customer_id, assignment_id):
    require_access(actor, "services.change_customerservice")
    assignment = CustomerService.objects.select_for_update().get(pk=assignment_id, customer_id=customer_id)
    if assignment.status != CustomerService.Status.TERMINATED:
        before = audit.snapshot(assignment)
        assignment.status = CustomerService.Status.TERMINATED
        assignment.save(update_fields=["status", "updated_at"])
        audit.record_change(actor=actor, instance=assignment, before=before)
    return assignment
