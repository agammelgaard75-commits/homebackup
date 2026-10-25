"""Read-only queries used by customer overview and service pages."""
from django.db.models.functions import Lower

from .models import CustomerService, Service


def active_service_count(customer):
    # Counts active agreements, even when the catalog entry is archived. Dates
    # and catalog availability do not silently change assignment status.
    return CustomerService.objects.filter(customer=customer, status=CustomerService.Status.ACTIVE).count()


def customer_assignments(customer):
    return CustomerService.objects.filter(customer=customer).select_related("service", "customer")


def overview_services(customer, *, include_history=False):
    """Every assigned catalog service once, filtered to current ones by default."""
    if include_history:
        records = Service.objects.filter(assignments__customer=customer)
    else:
        records = Service.objects.filter(assignments__customer=customer,
                                         assignments__status=CustomerService.Status.ACTIVE, is_active=True)
    return records.distinct().order_by(Lower("name"), "id")
