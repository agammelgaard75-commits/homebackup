from datetime import datetime, time, timezone
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from apps.accounts.permissions import permission_required
from apps.customers.models import Customer

from .forms import AuditFilterForm
from .selectors import visible_events


def _history(request, customer=None):
    records = visible_events(request.user)
    if customer is not None:
        records = records.filter(customer=customer)
    filters = AuditFilterForm(request.GET, events=records)
    valid = filters.is_valid()
    query = {}
    if valid:
        data = filters.cleaned_data
        if data["date_from"]:
            records = records.filter(created_at__gte=datetime.combine(data["date_from"], time.min, timezone.utc))
        if data["date_to"]:
            # Inclusive UTC day without depending on the display timezone.
            records = records.filter(created_at__lte=datetime.combine(data["date_to"], time.max, timezone.utc))
        if data["actor"]:
            records = records.filter(actor=data["actor"])
        if data["action"]:
            records = records.filter(action=data["action"])
        query = {key: value.pk if key == "actor" and value else value or "" for key, value in data.items()}
    else:
        records = records.none()
    return render(request, "audit/history.html", {
        "customer": customer, "filter_form": filters, "page_obj": Paginator(records, 25).get_page(request.GET.get("page")),
        "filter_query": urlencode(query),
    }, status=200 if valid else 400)


@permission_required("accounts.access_portal")
@permission_required("accounts.administer_portal")
@permission_required("audit.view_auditevent")
@require_safe
@never_cache
def history(request):
    return _history(request)


@permission_required("accounts.access_portal")
@permission_required("customers.view_customer")
@permission_required("audit.view_customer_activity")
@require_safe
@never_cache
def customer_activity(request, customer_pk):
    return _history(request, get_object_or_404(Customer, pk=customer_pk))
