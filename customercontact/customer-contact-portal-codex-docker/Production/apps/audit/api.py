from datetime import datetime, time, timezone

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.common import choice_param, require_api
from apps.api.pagination import PortalPagination
from apps.api.schema import LIST_PARAMETERS
from apps.api.serializers import AuditEventSerializer
from apps.customers.models import Customer

from .models import AuditEvent
from .selectors import visible_events


class AuditHistoryAPI(APIView):
    serializer_class = AuditEventSerializer

    @extend_schema(responses=AuditEventSerializer(many=True), parameters=LIST_PARAMETERS + [
        OpenApiParameter("actor_id", int), OpenApiParameter("action", str),
        OpenApiParameter("customer_id", str), OpenApiParameter("date_from", str),
        OpenApiParameter("date_to", str)])
    def get(self, request):
        require_api(request, "accounts.administer_portal", "audit.view_auditevent", scope="audit")
        return self.filtered_response(request, visible_events(request.user))

    @staticmethod
    def filtered_response(request, records):
        action = choice_param(request, "action", ("", *AuditEvent.Action.values), "")
        if action:
            records = records.filter(action=action)
        if request.query_params.get("actor_id"):
            records = records.filter(actor_id=request.query_params["actor_id"])
        if request.query_params.get("customer_id"):
            records = records.filter(related_customer_id=request.query_params["customer_id"])
        for parameter, lookup, boundary in (("date_from", "created_at__gte", time.min),
                                            ("date_to", "created_at__lte", time.max)):
            value = request.query_params.get(parameter)
            if value:
                try:
                    instant = datetime.combine(datetime.strptime(value, "%Y-%m-%d").date(), boundary, timezone.utc)
                except ValueError:
                    raise ValidationError({parameter: ["Use YYYY-MM-DD."]}) from None
                records = records.filter(**{lookup: instant})
        paginator = PortalPagination()
        page = paginator.paginate_queryset(records, request)
        return paginator.get_paginated_response(AuditEventSerializer(page, many=True).data)


class CustomerActivityAPI(APIView):
    serializer_class = AuditEventSerializer

    @extend_schema(responses=AuditEventSerializer(many=True), parameters=LIST_PARAMETERS + [
        OpenApiParameter("actor_id", int), OpenApiParameter("action", str),
        OpenApiParameter("date_from", str), OpenApiParameter("date_to", str)])
    def get(self, request, pk):
        require_api(request, "customers.view_customer", "audit.view_customer_activity")
        customer = get_object_or_404(Customer, pk=pk)
        return AuditHistoryAPI.filtered_response(request, visible_events(request.user).filter(customer=customer))
