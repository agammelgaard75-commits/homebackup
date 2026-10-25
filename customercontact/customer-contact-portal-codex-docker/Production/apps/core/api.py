from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.api.common import require_api
from apps.api.schema import LIST_PARAMETERS, DirectoryResponse, HealthResponse
from apps.services.permissions import READ_PERMISSIONS as SERVICE_READ

from .directory import directory_rows
from .forms import CustomerDirectoryForm
from .health import database_is_healthy


class HealthAPI(APIView):
    serializer_class = HealthResponse

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        healthy = database_is_healthy()
        return Response({"status": "ok" if healthy else "unavailable"}, status=200 if healthy else 503)


class DirectoryAPI(APIView):
    serializer_class = DirectoryResponse

    @extend_schema(parameters=LIST_PARAMETERS + [OpenApiParameter("customer_q", str),
        OpenApiParameter("contact_q", str), OpenApiParameter("service_q", str),
        OpenApiParameter("services", str, many=True),
        OpenApiParameter("customer_status", str, enum=["active", "inactive", ""]),
        OpenApiParameter("include_inactive_services", bool), OpenApiParameter("include_archived_contacts", bool),
        OpenApiParameter("sort", str, enum=["name", "-name"])])
    def get(self, request):
        require_api(request, "customers.view_customer")
        choices = request.query_params.copy()
        choices.setdefault("customer_status", "active")
        choices.setdefault("sort", "name")
        form = CustomerDirectoryForm(choices, can_view_services=request.user.has_perms(SERVICE_READ))
        if not form.is_valid():
            raise ValidationError(form.errors)
        try:
            size = int(request.query_params.get("page_size", 25))
        except (TypeError, ValueError):
            raise ValidationError({"page_size": ["Use a whole number from 1 to 100."]}) from None
        if not 1 <= size <= 100:
            raise ValidationError({"page_size": ["Use a whole number from 1 to 100."]})
        page, rows, _, _ = directory_rows(request.user, form.cleaned_data, request.query_params.get("page"), size)

        def page_url(number):
            if number is None:
                return None
            query = request.query_params.copy()
            query["page"] = number
            return request.build_absolute_uri(f"{request.path}?{query.urlencode()}")

        return Response({"count": page.paginator.count,
            "next": page_url(page.next_page_number()) if page.has_next() else None,
            "previous": page_url(page.previous_page_number()) if page.has_previous() else None,
            "results": [{"customer": {"id": row["customer"].pk, "name": row["customer"].name},
                "contacts": [{"id": contact.pk, "name": contact.full_name} for contact in row["contacts"]],
                "services": [{"id": service.pk, "name": service.name} for service in row["services"]]}
                for row in rows]})
