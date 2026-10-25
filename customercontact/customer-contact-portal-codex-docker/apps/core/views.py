from django.http import JsonResponse
from django.db import connection
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from urllib.parse import urlencode

from apps.accounts.permissions import permission_required
from apps.services.permissions import READ_PERMISSIONS as SERVICE_READ
from .directory import directory_rows
from .filter_preferences import chosen_filters, remember_filters
from .forms import CustomerDirectoryForm
from .health import database_is_healthy


@permission_required("accounts.access_portal")
@require_safe
@never_cache
def home(request):
    if not request.user.has_perm("customers.view_customer"):
        return render(request, "core/home.html", {"can_view_customers": False})
    choices = ("customer_status", "include_inactive_services", "include_archived_contacts", "sort", "services")
    defaults = {"customer_status": "active", "include_inactive_services": False,
                "include_archived_contacts": False, "sort": "name", "services": []}
    selected = chosen_filters(request, "core.directory", defaults, choices, multiple=("services",))
    if request.GET.get("filters") == "1":
        for checkbox in ("include_inactive_services", "include_archived_contacts"):
            if checkbox not in request.GET:
                selected[checkbox] = False
    data = {**selected, **{key: request.GET.get(key, "") for key in ("customer_q", "contact_q", "service_q")}}
    form = CustomerDirectoryForm(data, can_view_services=request.user.has_perms(SERVICE_READ))
    valid = form.is_valid()
    context = {"can_view_customers": True, "filter_form": form}
    if valid:
        remember_filters(request, "core.directory", form, choices, multiple=("services",))
        page, rows, can_contacts, can_services = directory_rows(request.user, form.cleaned_data, request.GET.get("page"))
        context.update(page_obj=page, rows=rows, can_contacts=can_contacts, can_services=can_services,
                       filter_query=urlencode([(key, str(value).lower() if isinstance(value, bool) else value)
                                               for key, value in form.cleaned_data.items() if key != "services"] +
                                              [("services", str(service.pk)) for service in form.cleaned_data["services"]]))
    return render(request, "core/home.html", context, status=200 if valid else 400)


@require_safe
@never_cache
def health(request):
    healthy = database_is_healthy(connection)
    return JsonResponse({"status": "ok" if healthy else "unavailable"}, status=200 if healthy else 503)
