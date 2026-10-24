"""Read-only queries used by customer overview and service pages."""
from .models import CustomerService


def active_service_count(customer):
    # Counts active agreements, even when the catalog entry is archived. Dates
    # and catalog availability do not silently change assignment status.
    return CustomerService.objects.filter(customer=customer, status=CustomerService.Status.ACTIVE).count()


def customer_assignments(customer):
    return CustomerService.objects.filter(customer=customer).select_related("service", "customer")
