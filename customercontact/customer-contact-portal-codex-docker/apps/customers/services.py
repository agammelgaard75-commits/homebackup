"""Public customer write API; all application mutations use these functions.

Each function requires an active actor with portal access, edit access and the
specific customer model permission. They normalize and fully validate input,
use transactions, and never log submitted values. Archiving preserves the row.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from .models import Customer


def require_customer_write(actor, permission):
    if not actor.is_active or not actor.has_perms((
        "accounts.access_portal", "accounts.edit_portal", "customers.view_customer", permission,
    )):
        raise PermissionDenied


def _save_validated(customer):
    customer.full_clean()
    try:
        # A savepoint lets callers safely handle a concurrent uniqueness failure.
        with transaction.atomic():
            customer.save()
    except IntegrityError as error:
        if getattr(getattr(error.__cause__, "diag", None), "constraint_name", None) == "customer_reference_unique":
            raise ValidationError({"reference_code": "A customer with this CVR / company ID already exists."}) from error
        raise
    return customer


@transaction.atomic
def create_customer(*, actor, name, reference_code="", status=Customer.Status.ACTIVE, address="", notes=""):
    require_customer_write(actor, "customers.add_customer")
    return _save_validated(Customer(
        name=name, reference_code=reference_code, status=status, address=address, notes=notes,
    ))


@transaction.atomic
def update_customer(*, actor, customer_id, name, reference_code, status, address, notes):
    require_customer_write(actor, "customers.change_customer")
    customer = Customer.objects.select_for_update().get(pk=customer_id)
    customer.name = name
    customer.reference_code = reference_code
    customer.status = status
    customer.address = address
    customer.notes = notes
    return _save_validated(customer)


@transaction.atomic
def archive_customer(*, actor, customer_id):
    require_customer_write(actor, "customers.change_customer")
    customer = Customer.objects.select_for_update().get(pk=customer_id)
    if customer.status != Customer.Status.INACTIVE:
        customer.status = Customer.Status.INACTIVE
        customer.save(update_fields=["status", "updated_at"])
    return customer
