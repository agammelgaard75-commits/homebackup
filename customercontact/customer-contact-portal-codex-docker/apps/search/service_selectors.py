"""Service-based customer/contact search and permission-scoped email selection."""
from django.db.models import CharField, Count, Exists, F, OuterRef, Q, UUIDField, Value
from django.db.models.functions import Lower

from apps.contacts.models import ContactCustomer, ContactPoint
from apps.customers.models import Customer
from apps.services.models import CustomerService


def matched_customers(filters):
    """Use distinct service IDs, so separate agreements never multiply matches."""
    ids = [service.pk for service in filters["services"]]
    assignments = CustomerService.objects.filter(service_id__in=ids)
    if not filters["include_inactive_assignments"]:
        assignments = assignments.filter(status=CustomerService.Status.ACTIVE)
    if filters["mode"] == "all":
        matched_ids = assignments.values("customer_id").annotate(service_count=Count("service_id", distinct=True)).filter(
            service_count=len(ids)).values("customer_id")
    else:
        matched_ids = assignments.values("customer_id")
    customers = Customer.objects.filter(pk__in=matched_ids)
    if not filters["include_archived_customers"]:
        customers = customers.filter(status=Customer.Status.ACTIVE)
    return customers


def matching_assignments(filters, customer_ids):
    assignments = CustomerService.objects.filter(customer_id__in=customer_ids, service__in=filters["services"])
    if not filters["include_inactive_assignments"]:
        assignments = assignments.filter(status=CustomerService.Status.ACTIVE)
    return assignments.select_related("service").order_by(Lower("service__name"), "service_id", "id")


def result_rows(filters):
    customers = matched_customers(filters)
    active_links = ContactCustomer.objects.filter(customer_id=OuterRef("pk"), is_active=True)
    if not filters["include_archived_contacts"]:
        active_links = active_links.filter(contact__is_active=True)
    linked = ContactCustomer.objects.filter(customer_id__in=customers.values("pk"), is_active=True)
    if not filters["include_archived_contacts"]:
        linked = linked.filter(contact__is_active=True)
    contact_rows = linked.order_by().annotate(
        row_customer_id=F("customer_id"), row_contact_id=F("contact_id"),
        row_customer_name=F("customer__name"), row_contact_name=F("contact__full_name"),
        row_customer_status=F("customer__status"), row_customer_updated=F("customer__updated_at"),
    ).values("row_customer_id", "row_contact_id", "row_customer_name", "row_contact_name",
             "row_customer_status", "row_customer_updated")
    empty_rows = customers.annotate(_has_contacts=Exists(active_links)).filter(_has_contacts=False).order_by().annotate(
        row_customer_id=F("pk"), row_contact_id=Value(None, output_field=UUIDField()),
        row_customer_name=F("name"), row_contact_name=Value("", output_field=CharField()),
        row_customer_status=F("status"), row_customer_updated=F("updated_at"),
    ).values("row_customer_id", "row_contact_id", "row_customer_name", "row_contact_name",
             "row_customer_status", "row_customer_updated")
    rows = contact_rows.union(empty_rows, all=True)
    if filters["sort"] == "contact":
        return rows.order_by("row_contact_name", "row_customer_name", "row_customer_id", "row_contact_id")
    if filters["sort"] == "updated":
        return rows.order_by("-row_customer_updated", "row_customer_name", "row_contact_name", "row_customer_id", "row_contact_id")
    return rows.order_by("row_customer_name", "row_contact_name", "row_customer_id", "row_contact_id")


def _email_points(filters):
    """Whole-result export: active customers/contacts/details only, regardless of display toggles."""
    customer_ids = matched_customers(filters).filter(status=Customer.Status.ACTIVE).values("pk")
    contact_ids = ContactCustomer.objects.filter(customer_id__in=customer_ids, is_active=True,
                                                  contact__is_active=True).values("contact_id")
    return ContactPoint.objects.filter(kind=ContactPoint.Kind.EMAIL, is_active=True).filter(
        Q(contact__isnull=True, customer_id__in=customer_ids) | Q(contact_id__in=contact_ids),
    )


def email_count(filters):
    return _email_points(filters).values("normalized_value").distinct().count()


def email_values(filters):
    points = _email_points(filters).order_by(Lower("value"), "id")
    result, seen = [], set()
    for normalized, value in points.values_list("normalized_value", "value").iterator(chunk_size=500):
        value = value.strip()
        key = (normalized or value).strip().casefold()
        if value and key and key not in seen:
            seen.add(key)
            result.append(value)
    return result
