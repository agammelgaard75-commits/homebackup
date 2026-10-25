from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from apps.accounts.permissions import permission_required
from apps.core.filter_preferences import chosen_filters, remember_filters

from .forms import SearchForm
from .selectors import result_url, search_groups


@permission_required("accounts.access_portal")
@require_safe
@never_cache
def search(request):
    choices = ("include_archived",)
    selected = chosen_filters(request, "search.global", {"include_archived": False}, choices)
    form = SearchForm({**selected, "q": request.GET.get("q", "")})
    valid = form.is_valid()
    if valid:
        remember_filters(request, "search.global", form, choices)
    query = form.cleaned_data["q"] if valid else ""
    groups = []
    for label, page_key, rows in search_groups(request.user, query, include_archived=form.cleaned_data["include_archived"] if valid else False):
        page = Paginator(rows, 10).get_page(request.GET.get(page_key))
        results = list(page.object_list)
        for row in results:
            row["url"] = result_url(row)
        # Only propagate known, validated query/page parameters.
        params = {"q": query}
        if valid and form.cleaned_data["include_archived"]:
            params["include_archived"] = "on"
        for key in ("customers_page", "contacts_page", "services_page"):
            value = request.GET.get(key, "")
            if key != page_key and value.isdecimal() and len(value) < 8:
                params[key] = value
        groups.append({"label": label, "page_key": page_key, "page": page, "results": results, "filter_query": urlencode(params)})
    return render(request, "search/results.html", {"form": form, "query": query, "groups": groups,
                  "total": sum(group["page"].paginator.count for group in groups)}, status=200 if valid else 400)
