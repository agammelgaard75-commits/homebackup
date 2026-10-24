from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from apps.contacts.models import Contact, ContactPoint
from apps.contacts.permissions import contact_access
from apps.services.permissions import READ_PERMISSIONS as SERVICE_READ
from apps.contacts.permissions import READ_PERMISSIONS as CONTACT_READ
from django.core.exceptions import PermissionDenied

from .service_forms import ServiceContactSearchForm
from .service_selectors import email_count, email_values, matching_assignments, result_rows


def _require_search_access(actor):
    if not actor.is_active or not actor.has_perms((*CONTACT_READ, *SERVICE_READ)):
        raise PermissionDenied


def _filters(request):
    data = request.GET.copy() if request.GET else None
    if data is not None:
        data.setdefault("mode", "any")
        data.setdefault("sort", "customer")
    form = ServiceContactSearchForm(data)
    return form, form.is_valid() if form.is_bound else False


@contact_access()
@require_safe
@never_cache
def service_contact_search(request):
    _require_search_access(request.user)
    form, valid = _filters(request)
    rows, count, filter_query = [], 0, ""
    if valid:
        filters = form.cleaned_data
        page = Paginator(result_rows(filters), 25).get_page(request.GET.get("page"))
        rows = list(page.object_list)
        customer_ids = {row["row_customer_id"] for row in rows}
        contact_ids = {row["row_contact_id"] for row in rows if row["row_contact_id"]}
        contacts_by_id = {contact.pk: contact for contact in Contact.objects.filter(pk__in=contact_ids)}
        services_by_customer = {customer_id: [] for customer_id in customer_ids}
        seen = {customer_id: set() for customer_id in customer_ids}
        for assignment in matching_assignments(filters, customer_ids):
            if assignment.service_id not in seen[assignment.customer_id]:
                seen[assignment.customer_id].add(assignment.service_id)
                services_by_customer[assignment.customer_id].append(assignment.service)
        points_by_contact = {contact_id: {"email": [], "phone": []} for contact_id in contact_ids}
        for point in ContactPoint.objects.filter(contact_id__in=contact_ids, is_active=True).order_by("kind", "id"):
            points_by_contact[point.contact_id][point.kind].append(point.value)
        general_by_customer = {customer_id: {"email": [], "phone": []} for customer_id in customer_ids}
        for point in ContactPoint.objects.filter(customer_id__in=customer_ids, contact__isnull=True,
                                                  is_active=True).order_by("kind", "id"):
            general_by_customer[point.customer_id][point.kind].append(point.value)
        for row in rows:
            contact = contacts_by_id.get(row["row_contact_id"])
            row["contact_type"] = contact.get_contact_type_display() if contact else ""
            row["job_title"] = contact.job_title if contact else ""
            row["contact_active"] = contact.is_active if contact else False
            row["matching_services"] = services_by_customer[row["row_customer_id"]]
            channels = points_by_contact.get(row["row_contact_id"]) if contact else general_by_customer[row["row_customer_id"]]
            row["emails"] = channels["email"]
            row["phones"] = channels["phone"]
        count = email_count(filters)
        params = request.GET.copy()
        params.pop("page", None)
        filter_query = params.urlencode()
    else:
        page = Paginator([], 25).get_page(1)
    return render(request, "search/service_contacts.html", {
        "filter_form": form, "page_obj": page, "rows": rows, "email_count": count,
        "filter_query": filter_query, "searched": form.is_bound,
    }, status=200 if not form.is_bound or valid else 400)


@contact_access()
@require_safe
@never_cache
def service_contact_emails(request):
    _require_search_access(request.user)
    form, valid = _filters(request)
    if not valid:
        return JsonResponse({"error": "Select valid service filters."}, status=400)
    addresses = email_values(form.cleaned_data)
    response = JsonResponse({"emails": "; ".join(addresses), "count": len(addresses)})
    response["X-Content-Type-Options"] = "nosniff"
    return response
