"""Read-only queries for the contacts UI and customer overview."""
from django.db.models import Prefetch, Q
from django.db.models.functions import Lower

from .models import Contact, ContactPoint
from .validation import phone_search_value


def general_contact_points(customer):
    return ContactPoint.objects.filter(customer=customer, contact__isnull=True, is_active=True)


def directory_results(customer, query="", status="active"):
    people = Contact.objects.filter(customer=customer)
    general = ContactPoint.objects.filter(customer=customer, contact__isnull=True)
    if status:
        people = people.filter(is_active=status == "active")
        general = general.filter(is_active=status == "active")
    if query:
        matching = Q(value__icontains=query) | Q(normalized_value__icontains=query.lower())
        phone = phone_search_value(query)
        if phone:
            matching |= Q(kind="phone", normalized_value__contains=phone)
        point_matches = ContactPoint.objects.filter(customer=customer, is_active=True).filter(matching)
        people = people.filter(Q(full_name__icontains=query) | Q(pk__in=point_matches.values("contact_id")))
        general = general.filter(matching)
    people = people.order_by(Lower("full_name"), "id").prefetch_related(
        Prefetch("points", queryset=ContactPoint.objects.filter(is_active=True), to_attr="active_points"),
    )
    return people, general
