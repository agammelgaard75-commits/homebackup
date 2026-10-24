"""Read-only PostgreSQL substring search; permissions precede every query.

Project different entities into a common shape so PostgreSQL can UNION and
paginate each group without loading the full result set into Python.
"""
from django.db.models import Case, CharField, F, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Cast, Coalesce
from django.urls import reverse

from apps.contacts.models import Contact, ContactCustomer, ContactPoint
from apps.contacts.permissions import READ_PERMISSIONS as CONTACT_READ
from apps.contacts.validation import phone_search_value
from apps.customers.models import Customer
from apps.services.models import CustomerService, Service
from apps.services.permissions import READ_PERMISSIONS as SERVICE_READ


def _active(field="is_active"):
    return Case(When(**{field: True}, then=Value("Active")), default=Value("Archived"), output_field=CharField())


def _rows(queryset, kind, title, subtitle, *, customer_id=None, customer_name=None, status=None, customer_status=None):
    return queryset.order_by().annotate(
        result_id=Cast("pk", CharField()), result_kind=Value(kind), result_title=title, result_subtitle=subtitle,
        result_customer_id=Cast(customer_id, CharField()) if customer_id is not None else Value(""),
        result_customer_name=customer_name if customer_name is not None else Value(""),
        result_status=status if status is not None else _active(),
        result_customer_status=customer_status if customer_status is not None else Value(""),
    ).values("result_id", "result_kind", "result_title", "result_subtitle", "result_customer_id",
             "result_customer_name", "result_status", "result_customer_status")


def search_groups(actor, query):
    if not actor.is_active or not actor.has_perm("accounts.access_portal") or not query:
        return []
    groups = []
    if actor.has_perm("customers.view_customer"):
        records = Customer.objects.filter(Q(name__icontains=query) | Q(reference_code__icontains=query))
        groups.append(("Customers", "customers_page", _rows(records, "customer", F("name"), F("reference_code"),
                      status=Case(When(status="active", then=Value("Active")), default=Value("Archived")))))
    if actor.has_perms(CONTACT_READ):
        points = ContactPoint.objects.filter(Q(value__icontains=query) | Q(normalized_value__icontains=query))
        phone = phone_search_value(query)
        if phone:
            points = ContactPoint.objects.filter(Q(pk__in=points.values("pk")) | Q(kind="phone", normalized_value__contains=phone))
        people = Contact.objects.filter(Q(full_name__icontains=query) | Q(job_title__icontains=query) | Q(pk__in=points.values("contact_id")))
        current_link = ContactCustomer.objects.filter(contact_id=OuterRef("pk"), is_active=True).order_by("created_at", "customer_id")
        people_rows = _rows(people, "contact", F("full_name"), F("job_title"),
                            customer_id=Coalesce(Subquery(current_link.values("customer_id")[:1]), F("customer_id")),
                            customer_name=Coalesce(Subquery(current_link.values("customer__name")[:1]), F("customer__name")),
                            customer_status=Coalesce(Subquery(current_link.values("customer__status")[:1]), F("customer__status")))
        groups.append(("Contacts", "contacts_page", people_rows))
    if actor.has_perm("services.view_service"):
        catalog = Service.objects.filter(Q(name__icontains=query) | Q(description__icontains=query))
        rows = _rows(catalog, "service", F("name"), F("description"))
        if actor.has_perms(SERVICE_READ):
            assignments = CustomerService.objects.filter(Q(service_id__in=catalog.values("pk")) | Q(customer__name__icontains=query) | Q(customer__reference_code__icontains=query))
            rows = rows.union(_rows(assignments, "assignment", F("service__name"),
                                    Case(When(service__is_active=False, then=Value("Archived catalog service")), default=Value("Customer agreement")),
                                    customer_id=F("customer_id"), customer_name=F("customer__name"),
                                    status=F("status"), customer_status=F("customer__status")))
        groups.append(("Services", "services_page", rows))
    return [(label, page_key, rows.order_by("result_title", "result_kind", "result_id")) for label, page_key, rows in groups]


def result_url(row):
    kind, pk, customer_pk = row["result_kind"], row["result_id"], row["result_customer_id"]
    if kind == "customer":
        return reverse("customers:detail", args=[pk])
    if kind == "contact":
        return reverse("contacts:detail", args=[customer_pk, pk])
    if kind == "service":
        return reverse("services:detail", args=[pk])
    return reverse("customer_services:detail", args=[customer_pk, pk])
