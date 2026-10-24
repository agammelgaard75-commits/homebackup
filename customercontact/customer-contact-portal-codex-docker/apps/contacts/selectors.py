"""Read-only queries for scoped/global contact pages and customer overview."""
from django.db.models import Exists, OuterRef, Prefetch, Q
from django.db.models.functions import Lower

from .models import Contact, ContactCustomer, ContactPoint
from .validation import phone_search_value


def general_contact_points(customer):
    return ContactPoint.objects.filter(customer=customer, contact__isnull=True, is_active=True)


def associated_contacts(customer):
    """New membership rows are authoritative; legacy-only rows stay readable."""
    links = ContactCustomer.objects.filter(contact_id=OuterRef("pk"))
    active_for_customer = links.filter(customer=customer, is_active=True)
    return Contact.objects.annotate(_has_links=Exists(links), _linked_here=Exists(active_for_customer)).filter(
        Q(_linked_here=True) | Q(_has_links=False, customer=customer),
    )


def is_associated(contact, customer_id):
    links = ContactCustomer.objects.filter(contact_id=contact.pk)
    return links.filter(customer_id=customer_id, is_active=True).exists() if links.exists() else contact.customer_id == customer_id


def active_customer_ids(contact):
    links = list(ContactCustomer.objects.filter(contact_id=contact.pk, is_active=True).values_list("customer_id", flat=True))
    return links if ContactCustomer.objects.filter(contact_id=contact.pk).exists() else [contact.customer_id]


def directory_results(customer, query="", status="active"):
    people = associated_contacts(customer)
    general = ContactPoint.objects.filter(customer=customer, contact__isnull=True)
    if status:
        people = people.filter(is_active=status == "active")
        general = general.filter(is_active=status == "active")
    if query:
        matching = Q(value__icontains=query) | Q(normalized_value__icontains=query.lower())
        phone = phone_search_value(query)
        if phone:
            matching |= Q(kind="phone", normalized_value__contains=phone)
        point_matches = ContactPoint.objects.filter(is_active=True, contact__isnull=False).filter(matching)
        people = people.filter(Q(full_name__icontains=query) | Q(pk__in=point_matches.values("contact_id")))
        general = general.filter(matching)
    people = people.order_by(Lower("full_name"), "id").prefetch_related(
        Prefetch("points", queryset=ContactPoint.objects.filter(is_active=True), to_attr="active_points"),
        Prefetch("customer_links", queryset=ContactCustomer.objects.filter(is_active=True), to_attr="active_customer_links"),
    )
    return people, general


def global_contacts(q="", status="active", contact_type=""):
    people = Contact.objects.all()
    if status:
        people = people.filter(is_active=status == "active")
    if contact_type:
        people = people.filter(contact_type=contact_type)
    if q:
        matching = Q(value__icontains=q) | Q(normalized_value__icontains=q.lower())
        phone = phone_search_value(q)
        if phone:
            matching |= Q(kind="phone", normalized_value__contains=phone)
        points = ContactPoint.objects.filter(contact__isnull=False, is_active=True).filter(matching).values("contact_id")
        linked = ContactCustomer.objects.filter(is_active=True).filter(
            Q(customer__name__icontains=q) | Q(customer__reference_code__icontains=q),
        ).values("contact_id")
        people = people.filter(Q(full_name__icontains=q) | Q(job_title__icontains=q)
                               | Q(pk__in=points) | Q(pk__in=linked)
                               | Q(customer__name__icontains=q, customer_links__isnull=True)).distinct()
    return people.order_by(Lower("full_name"), "id").prefetch_related(
        Prefetch("points", queryset=ContactPoint.objects.filter(is_active=True), to_attr="active_points"),
        Prefetch("customer_links", queryset=ContactCustomer.objects.filter(is_active=True).select_related("customer"),
                 to_attr="active_customer_links"),
    )
