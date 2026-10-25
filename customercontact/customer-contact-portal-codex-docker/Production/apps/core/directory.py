"""Permission-scoped reads for the home customer directory."""
from collections import defaultdict

from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models.functions import Lower

from apps.contacts.models import Contact, ContactCustomer, ContactPoint
from apps.contacts.permissions import READ_PERMISSIONS as CONTACT_READ
from apps.customers.models import Customer
from apps.services.models import CustomerService
from apps.services.permissions import READ_PERMISSIONS as SERVICE_READ


def directory_rows(actor, filters, page_number, page_size=25):
    can_contacts = actor.has_perms(CONTACT_READ)
    can_services = actor.has_perms(SERVICE_READ)
    customers = Customer.objects.all()
    status = filters["customer_status"]
    if status:
        customers = customers.filter(status=status)
    if filters["customer_q"]:
        customers = customers.filter(name__icontains=filters["customer_q"])

    if filters["contact_q"] and can_contacts:
        query = filters["contact_q"]
        point_ids = ContactPoint.objects.filter(is_active=True, kind="email", value__icontains=query).values("contact_id")
        matching = Contact.objects.filter(Q(full_name__icontains=query) | Q(pk__in=point_ids))
        if not filters["include_archived_contacts"]:
            matching = matching.filter(is_active=True)
        linked_ids = ContactCustomer.objects.filter(is_active=True, contact__in=matching).values("customer_id")
        legacy_ids = matching.filter(customer_links__isnull=True).values("customer_id")
        customers = customers.filter(Q(pk__in=linked_ids) | Q(pk__in=legacy_ids))

    assignments = CustomerService.objects.all()
    if not filters["include_inactive_services"]:
        assignments = assignments.filter(status=CustomerService.Status.ACTIVE, service__is_active=True)
    if filters["service_q"] and can_services:
        customers = customers.filter(pk__in=assignments.filter(service__name__icontains=filters["service_q"]).values("customer_id"))
    if filters["services"] and can_services:
        customers = customers.filter(pk__in=assignments.filter(service__in=filters["services"]).values("customer_id"))

    ordering = [Lower("name").desc(), "id"] if filters["sort"] == "-name" else [Lower("name"), "id"]
    page = Paginator(customers.order_by(*ordering), page_size).get_page(page_number)
    visible = list(page.object_list)
    ids = [customer.pk for customer in visible]
    contacts_by_customer = defaultdict(dict)
    services_by_customer = defaultdict(dict)
    if ids and can_contacts:
        links = ContactCustomer.objects.filter(is_active=True, customer_id__in=ids).select_related("contact")
        if not filters["include_archived_contacts"]:
            links = links.filter(contact__is_active=True)
        for link in links:
            contacts_by_customer[link.customer_id][link.contact_id] = link.contact
        legacy = Contact.objects.filter(customer_id__in=ids, customer_links__isnull=True)
        if not filters["include_archived_contacts"]:
            legacy = legacy.filter(is_active=True)
        for contact in legacy:
            contacts_by_customer[contact.customer_id][contact.pk] = contact
    if ids and can_services:
        for assignment in assignments.filter(customer_id__in=ids).select_related("service"):
            services_by_customer[assignment.customer_id][assignment.service_id] = assignment.service
    rows = [{"customer": customer,
             "contacts": sorted(contacts_by_customer[customer.pk].values(), key=lambda item: item.full_name.casefold()),
             "services": sorted(services_by_customer[customer.pk].values(), key=lambda item: item.name.casefold())}
            for customer in visible]
    return page, rows, can_contacts, can_services
