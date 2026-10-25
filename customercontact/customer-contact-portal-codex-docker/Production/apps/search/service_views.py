from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from apps.contacts.permissions import contact_access
from apps.core.filter_preferences import chosen_filters, remember_filters
from apps.services.permissions import READ_PERMISSIONS as SERVICE_READ
from apps.contacts.permissions import READ_PERMISSIONS as CONTACT_READ
from django.core.exceptions import PermissionDenied

from .service_forms import ServiceContactSearchForm
from .service_selectors import email_count, email_values, enrich_rows, result_rows


def _require_search_access(actor):
    if not actor.is_active or not actor.has_perms((*CONTACT_READ, *SERVICE_READ)):
        raise PermissionDenied


def _filters(request):
    fields = ("services", "include_archived_services", "mode", "include_inactive_assignments",
              "include_archived_customers", "include_archived_contacts", "sort")
    defaults = {"services": [], "include_archived_services": False, "mode": "any",
                "include_inactive_assignments": False, "include_archived_customers": False,
                "include_archived_contacts": False, "sort": "customer"}
    data = chosen_filters(request, "search.by_service", defaults, fields, multiple=("services",))
    if request.GET.get("reset") == "1" or (not request.GET and not data["services"]):
        data = None
    form = ServiceContactSearchForm(data)
    valid = form.is_valid() if form.is_bound else False
    if valid:
        remember_filters(request, "search.by_service", form, fields, multiple=("services",))
    return form, valid


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
        rows = enrich_rows(filters, list(page.object_list))
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
    # The export must be bound to the explicit filters sent with the button,
    # never an older session preference from a previous page visit.
    data = request.GET.copy() if request.GET else None
    if data is not None:
        data.setdefault("mode", "any")
        data.setdefault("sort", "customer")
    form = ServiceContactSearchForm(data)
    valid = form.is_valid() if form.is_bound else False
    if not valid:
        return JsonResponse({"error": "Select valid service filters."}, status=400)
    addresses = email_values(form.cleaned_data)
    response = JsonResponse({"emails": "; ".join(addresses), "count": len(addresses)})
    response["X-Content-Type-Options"] = "nosniff"
    return response
