from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.common import choice_param, limited_query, require_api
from apps.api.pagination import PortalPagination
from apps.api.schema import LIST_PARAMETERS, CleanupConfirmation, CleanupOperationResponse, CleanupPreviewResponse, CleanupSelection
from apps.api.serializers import ContactSerializer, CustomerSerializer, api_contacts
from apps.contacts.models import Contact
from apps.customers.models import Customer

from .models import CleanupOperation
from .services import StaleCleanupPreview, confirm_cleanup, preview_cleanup


class CleanupConflict(APIException):
    status_code = 409
    default_detail = "The cleanup preview is stale or blocked. Preview again."
    default_code = "cleanup_conflict"

PERMISSIONS = ("accounts.administer_portal", "customers.view_customer", "contacts.view_contact",
               "cleanup.view_cleanupoperation", "cleanup.execute_cleanup")


class ArchivedCustomersAPI(APIView):
    serializer_class = CustomerSerializer

    @extend_schema(responses=CustomerSerializer(many=True), parameters=LIST_PARAMETERS + [OpenApiParameter("q", str)])
    def get(self, request):
        require_api(request, *PERMISSIONS, scope="cleanup")
        records = Customer.objects.filter(status=Customer.Status.INACTIVE)
        query = limited_query(request)
        if query:
            records = records.filter(Q(name__icontains=query) | Q(reference_code__icontains=query))
        paginator = PortalPagination()
        page = paginator.paginate_queryset(records.order_by("name", "id"), request)
        return paginator.get_paginated_response(CustomerSerializer(page, many=True).data)


class ArchivedContactsAPI(APIView):
    serializer_class = ContactSerializer

    @extend_schema(responses=ContactSerializer(many=True), parameters=LIST_PARAMETERS + [
        OpenApiParameter("q", str), OpenApiParameter("contact_type", str)])
    def get(self, request):
        require_api(request, *PERMISSIONS, scope="cleanup")
        records = Contact.objects.filter(is_active=False)
        contact_type = choice_param(request, "contact_type", ("", *Contact.Type.values), "")
        if contact_type:
            records = records.filter(contact_type=contact_type)
        query = limited_query(request)
        if query:
            records = records.filter(Q(full_name__icontains=query) | Q(customer__name__icontains=query)
                                     | Q(customer_links__customer__name__icontains=query)).distinct()
        paginator = PortalPagination()
        page = paginator.paginate_queryset(api_contacts(records.order_by("full_name", "id")), request)
        return paginator.get_paginated_response(ContactSerializer(page, many=True).data)


class CleanupPreviewAPI(APIView):
    serializer_class = CleanupPreviewResponse

    @extend_schema(request=CleanupSelection, responses=CleanupPreviewResponse, examples=[OpenApiExample(
        "Preview archived records", value={"customer_ids": [], "contact_ids": [
            "00000000-0000-0000-0000-000000000001"]}, request_only=True)])
    def post(self, request):
        require_api(request, *PERMISSIONS, scope="cleanup")
        if not isinstance(request.data, dict):
            raise ValidationError({"selection": ["Use a JSON object."]})
        result = preview_cleanup(actor=request.user, customer_ids=request.data.get("customer_ids", []),
                                 contact_ids=request.data.get("contact_ids", []))
        return Response(result)


class CleanupConfirmAPI(APIView):
    serializer_class = CleanupOperationResponse

    @extend_schema(request=CleanupConfirmation, responses=CleanupOperationResponse)
    def post(self, request):
        require_api(request, *PERMISSIONS, scope="cleanup")
        if not isinstance(request.data, dict) or not isinstance(request.data.get("confirmation_token"), str):
            raise ValidationError({"confirmation_token": ["A validated preview token is required."]})
        try:
            operation = confirm_cleanup(actor=request.user, token=request.data["confirmation_token"],
                                        confirm=request.data.get("confirm"))
        except (StaleCleanupPreview, ProtectedError):
            raise CleanupConflict from None
        return Response({"id": str(operation.pk), "confirmation_ref": str(operation.confirmation_ref),
                         "result": operation.result, "counts": operation.counts})


class CleanupOperationAPI(APIView):
    serializer_class = CleanupOperationResponse

    def get(self, request, pk):
        require_api(request, *PERMISSIONS, scope="cleanup")
        operation = get_object_or_404(CleanupOperation, pk=pk)
        return Response({"id": str(operation.pk), "confirmation_ref": str(operation.confirmation_ref),
                         "actor_id": operation.actor_id, "created_at": operation.created_at.isoformat(),
                         "result": operation.result, "customer_ids": operation.customer_ids,
                         "contact_ids": operation.contact_ids, "counts": operation.counts,
                         "error_code": operation.error_code})
