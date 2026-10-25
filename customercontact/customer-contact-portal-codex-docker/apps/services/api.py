from django.db.models import Q
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.common import choice_param, limited_query, require_api
from apps.api.pagination import PortalPagination
from apps.api.schema import LIST_PARAMETERS
from apps.api.serializers import AssignmentSerializer, ServiceSerializer
from apps.customers.models import Customer

from .models import CustomerService, Service
from .services import (create_assignment, create_service, set_service_active, terminate_assignment,
                       update_assignment, update_service)

CATALOG_READ = ("services.view_service",)
ASSIGNMENT_READ = ("services.view_service", "services.view_customerservice", "customers.view_customer")


class AssignmentWriteSerializer(serializers.Serializer):
    customer_id = serializers.UUIDField()
    service_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=CustomerService.Status.choices, default=CustomerService.Status.ACTIVE)
    start_date = serializers.DateField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=10000, required=False, allow_blank=True, default="")


class AssignmentUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=CustomerService.Status.choices, required=False)
    start_date = serializers.DateField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=10000, required=False, allow_blank=True)


class ServiceListAPI(APIView):
    serializer_class = ServiceSerializer

    @extend_schema(operation_id="services_list", responses=ServiceSerializer(many=True),
        parameters=LIST_PARAMETERS + [OpenApiParameter("q", str),
            OpenApiParameter("status", str, enum=["active", "archived", "all"]),
            OpenApiParameter("category", str), OpenApiParameter("sort", str, enum=["name", "-name", "updated"])])
    def get(self, request):
        require_api(request, *CATALOG_READ)
        selected_status = choice_param(request, "status", ("active", "archived", "all"), "active")
        selected_sort = choice_param(request, "sort", ("name", "-name", "updated"), "name")
        records = Service.objects.all()
        if selected_status != "all":
            records = records.filter(is_active=selected_status == "active")
        query = limited_query(request)
        if query:
            records = records.filter(Q(name__icontains=query) | Q(description__icontains=query) | Q(category__icontains=query))
        if request.query_params.get("category"):
            records = records.filter(category__iexact=limited_query(request, "category", 100))
        order = {"name": (Lower("name"), "id"), "-name": (Lower("name").desc(), "id"),
                 "updated": ("-updated_at", "id")}[selected_sort]
        paginator = PortalPagination()
        page = paginator.paginate_queryset(records.order_by(*order), request)
        return paginator.get_paginated_response(ServiceSerializer(page, many=True).data)

    def post(self, request):
        require_api(request, *CATALOG_READ, "accounts.edit_portal", "accounts.administer_portal", "services.add_service", scope="write")
        serializer = ServiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = create_service(actor=request.user, **serializer.validated_data)
        return Response(ServiceSerializer(service).data, status=status.HTTP_201_CREATED)


class ServiceDetailAPI(APIView):
    serializer_class = ServiceSerializer

    def get(self, request, pk):
        require_api(request, *CATALOG_READ)
        return Response(ServiceSerializer(get_object_or_404(Service, pk=pk)).data)

    def put(self, request, pk):
        return self._update(request, pk, partial=False)

    def patch(self, request, pk):
        return self._update(request, pk, partial=True)

    def _update(self, request, pk, *, partial):
        require_api(request, *CATALOG_READ, "accounts.edit_portal", "accounts.administer_portal", "services.change_service", scope="write")
        service = get_object_or_404(Service, pk=pk)
        serializer = ServiceSerializer(service, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        values = {field: serializer.validated_data.get(field, getattr(service, field)) for field in
                  ("name", "description", "category")}
        service = update_service(actor=request.user, service_id=service.pk, **values)
        return Response(ServiceSerializer(service).data)


class ServiceStatusAPI(APIView):
    serializer_class = ServiceSerializer
    active = False

    @extend_schema(request=None, responses=ServiceSerializer)
    def post(self, request, pk):
        require_api(request, *CATALOG_READ, "accounts.edit_portal", "accounts.administer_portal", "services.change_service", scope="write")
        service = set_service_active(actor=request.user, service_id=get_object_or_404(Service, pk=pk).pk,
                                     is_active=self.active)
        return Response(ServiceSerializer(service).data)


class ServiceCustomersAPI(APIView):
    serializer_class = AssignmentSerializer

    @extend_schema(responses=AssignmentSerializer(many=True), parameters=LIST_PARAMETERS + [
        OpenApiParameter("status", str, enum=[*CustomerService.Status.values, "all"])])
    def get(self, request, pk):
        require_api(request, *ASSIGNMENT_READ)
        service = get_object_or_404(Service, pk=pk)
        selected_status = choice_param(request, "status", (*CustomerService.Status.values, "all"), "active")
        records = CustomerService.objects.filter(service=service).select_related("customer")
        if selected_status != "all":
            records = records.filter(status=selected_status, customer__status=Customer.Status.ACTIVE)
        paginator = PortalPagination()
        page = paginator.paginate_queryset(records.order_by("customer__name", "id"), request)
        return paginator.get_paginated_response(AssignmentSerializer(page, many=True).data)


class AssignmentListAPI(APIView):
    serializer_class = AssignmentSerializer

    @extend_schema(operation_id="assignments_list", responses=AssignmentSerializer(many=True),
        parameters=LIST_PARAMETERS + [OpenApiParameter("q", str), OpenApiParameter("customer_id", str),
            OpenApiParameter("service_id", str), OpenApiParameter("status", str,
                enum=[*CustomerService.Status.values, "all"])])
    def get(self, request):
        require_api(request, *ASSIGNMENT_READ)
        selected_status = choice_param(request, "status", (*CustomerService.Status.values, "all"), "active")
        records = CustomerService.objects.select_related("customer", "service")
        if selected_status != "all":
            records = records.filter(status=selected_status, customer__status=Customer.Status.ACTIVE,
                                     service__is_active=True)
        for parameter, field in (("customer_id", "customer_id"), ("service_id", "service_id")):
            if request.query_params.get(parameter):
                records = records.filter(**{field: request.query_params[parameter]})
        query = limited_query(request)
        if query:
            records = records.filter(Q(customer__name__icontains=query) | Q(service__name__icontains=query))
        paginator = PortalPagination()
        page = paginator.paginate_queryset(records.order_by("-created_at", "id"), request)
        return paginator.get_paginated_response(AssignmentSerializer(page, many=True).data)

    @extend_schema(request=AssignmentWriteSerializer, responses={201: AssignmentSerializer})
    def post(self, request):
        require_api(request, *ASSIGNMENT_READ, "accounts.edit_portal", "services.add_customerservice", scope="write")
        serializer = AssignmentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        get_object_or_404(Customer, pk=values["customer_id"])
        get_object_or_404(Service, pk=values["service_id"])
        assignment = create_assignment(actor=request.user, **values)
        return Response(AssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)


class AssignmentDetailAPI(APIView):
    serializer_class = AssignmentSerializer

    def get(self, request, pk):
        require_api(request, *ASSIGNMENT_READ)
        return Response(AssignmentSerializer(get_object_or_404(CustomerService, pk=pk)).data)

    @extend_schema(request=AssignmentUpdateSerializer, responses=AssignmentSerializer)
    def put(self, request, pk):
        return self._update(request, pk, partial=False)

    @extend_schema(request=AssignmentUpdateSerializer, responses=AssignmentSerializer)
    def patch(self, request, pk):
        return self._update(request, pk, partial=True)

    def _update(self, request, pk, *, partial):
        require_api(request, *ASSIGNMENT_READ, "accounts.edit_portal", "services.change_customerservice", scope="write")
        if set(request.data) & {"customer", "customer_id", "service", "service_id"}:
            raise ValidationError({"assignment": ["Customer and service are immutable; create a separate agreement."]})
        assignment = get_object_or_404(CustomerService, pk=pk)
        serializer = AssignmentUpdateSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        values = {field: serializer.validated_data.get(field, getattr(assignment, field)) for field in
                  ("status", "start_date", "end_date", "notes")}
        assignment = update_assignment(actor=request.user, customer_id=assignment.customer_id,
                                       assignment_id=assignment.pk, **values)
        return Response(AssignmentSerializer(assignment).data)


class AssignmentTerminateAPI(APIView):
    serializer_class = AssignmentSerializer

    @extend_schema(request=None, responses=AssignmentSerializer)
    def post(self, request, pk):
        require_api(request, *ASSIGNMENT_READ, "accounts.edit_portal", "services.change_customerservice", scope="write")
        assignment = get_object_or_404(CustomerService, pk=pk)
        assignment = terminate_assignment(actor=request.user, customer_id=assignment.customer_id,
                                          assignment_id=assignment.pk)
        return Response(AssignmentSerializer(assignment).data)
