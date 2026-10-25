from django.core.paginator import Paginator
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.common import boolean_param, limited_query, require_api
from apps.api.pagination import PortalPagination
from apps.api.schema import LIST_PARAMETERS, EmailExportResponse, GlobalSearchResponse, ServiceSearchRow
from apps.contacts.permissions import READ_PERMISSIONS as CONTACT_READ
from apps.services.permissions import READ_PERMISSIONS as SERVICE_READ

from .selectors import result_url, search_groups
from .service_forms import ServiceContactSearchForm
from .service_selectors import email_values, enrich_rows, result_rows


class GlobalSearchAPI(APIView):
    serializer_class = GlobalSearchResponse

    @extend_schema(parameters=[OpenApiParameter("q", str), OpenApiParameter("include_archived", bool),
        OpenApiParameter("customers_page", int), OpenApiParameter("contacts_page", int),
        OpenApiParameter("services_page", int)])
    def get(self, request):
        require_api(request)
        query = limited_query(request)
        include_archived = boolean_param(request, "include_archived")
        groups = {}
        for label, _, records in search_groups(request.user, query, include_archived=include_archived):
            page = Paginator(records, 25).get_page(request.query_params.get(f"{label.lower()}_page", 1))
            groups[label.lower()] = {"count": page.paginator.count, "page": page.number,
                "pages": page.paginator.num_pages,
                "results": [{**row, "url": result_url(row)} for row in page.object_list]}
        return Response({"query": query, "groups": groups})


SERVICE_PARAMETERS = [OpenApiParameter("services", str, many=True, required=True,
    description="Repeat once per selected catalog service UUID."),
    OpenApiParameter("mode", str, enum=["any", "all"], description="Default: any."),
    OpenApiParameter("include_inactive_assignments", bool),
    OpenApiParameter("include_archived_services", bool),
    OpenApiParameter("include_archived_customers", bool),
    OpenApiParameter("include_archived_contacts", bool),
    OpenApiParameter("sort", str, enum=["customer", "contact", "updated"])]


def service_filters(request):
    data = request.query_params.copy()
    data.setdefault("mode", "any")
    data.setdefault("sort", "customer")
    form = ServiceContactSearchForm(data)
    if not form.is_valid():
        raise ValidationError(form.errors)
    return form.cleaned_data


class ServiceContactSearchAPI(APIView):
    serializer_class = ServiceSearchRow

    @extend_schema(parameters=LIST_PARAMETERS + SERVICE_PARAMETERS, responses=ServiceSearchRow(many=True))
    def get(self, request):
        require_api(request, *CONTACT_READ, *SERVICE_READ)
        filters = service_filters(request)
        paginator = PortalPagination()
        page = paginator.paginate_queryset(result_rows(filters), request)
        rows = enrich_rows(filters, list(page))
        for row in rows:
            row["matching_services"] = [{"id": str(service.pk), "name": service.name}
                                         for service in row["matching_services"]]
        return paginator.get_paginated_response(rows)


class ServiceContactEmailsAPI(APIView):
    serializer_class = EmailExportResponse

    @extend_schema(parameters=SERVICE_PARAMETERS, responses=EmailExportResponse)
    def get(self, request):
        require_api(request, *CONTACT_READ, *SERVICE_READ)
        addresses = email_values(service_filters(request))
        return Response({"count": len(addresses), "emails": addresses, "recipient_field": "; ".join(addresses)})
