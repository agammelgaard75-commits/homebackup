"""Dashboard reads respect the same permissions as their destination pages."""
from django.db.models import Prefetch

from apps.contacts.models import Contact, ContactCustomer
from apps.contacts.permissions import READ_PERMISSIONS as CONTACT_READ
from apps.customers.models import Customer
from apps.services.models import CustomerService
from apps.services.permissions import READ_PERMISSIONS as SERVICE_READ


def dashboard_data(actor):
    data = {}
    if not actor.is_active or not actor.has_perm("accounts.access_portal"):
        return data
    if actor.has_perm("customers.view_customer"):
        data["active_customers"] = Customer.objects.filter(status="active").count()
        data["recent_customers"] = Customer.objects.order_by("-updated_at", "-pk")[:5]
    if actor.has_perms(CONTACT_READ):
        data["active_contacts"] = Contact.objects.filter(is_active=True).count()
        data["recent_contacts"] = Contact.objects.select_related("customer").prefetch_related(
            Prefetch("customer_links", queryset=ContactCustomer.objects.filter(is_active=True).select_related("customer"),
                     to_attr="active_customer_links"),
        ).order_by("-created_at", "-pk")[:5]
        data["active_contact_preview"] = Contact.objects.filter(is_active=True).order_by("-updated_at", "-pk")[:5]
    if actor.has_perms(SERVICE_READ):
        data["active_assignments"] = CustomerService.objects.filter(status="active").count()
    return data
