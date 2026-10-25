from django.db.models import Q
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.common import boolean_param, choice_param, limited_query, require_api
from apps.api.pagination import PortalPagination
from apps.api.schema import LIST_PARAMETERS, ErrorResponse
from apps.api.serializers import AssignmentSerializer, ContactSerializer, CustomerSerializer, api_contacts
from apps.contacts.models import ContactCustomer, ContactPoint
from apps.contacts.selectors import associated_contacts
from apps.services.models import CustomerService

from .models import Customer
from .services import archive_customer, create_customer, update_customer


class CustomerListAPI(APIView):
    serializer_class = CustomerSerializer

    @extend_schema(operation_id="customers_list", responses=CustomerSerializer(many=True),
        parameters=LIST_PARAMETERS + [OpenApiParameter("q", str, description="Customer name or company ID substring."),
            OpenApiParameter("status", str, enum=["active", "inactive", "all"]),
            OpenApiParameter("sort", str, enum=["name", "-name", "updated"])])
    def get(self, request):
        require_api(request, "customers.view_customer")
        query = limited_query(request)
        selected_status = choice_param(request, "status", ("active", "inactive", "all"), "active")
        sort = choice_param(request, "sort", ("name", "-name", "updated"), "name")
        records = Customer.objects.all()
        if selected_status != "all":
            records = records.filter(status=selected_status)
        if query:
            records = records.filter(Q(name__icontains=query) | Q(reference_code__icontains=query))
        ordering = {"name": (Lower("name"), "id"), "-name": (Lower("name").desc(), "id"),
                    "updated": ("-updated_at", "id")}[sort]
        paginator = PortalPagination()
        page = paginator.paginate_queryset(records.order_by(*ordering), request)
        return paginator.get_paginated_response(CustomerSerializer(page, many=True).data)

    @extend_schema(request=CustomerSerializer, responses={201: CustomerSerializer, 400: ErrorResponse},
        examples=[OpenApiExample("Create customer", value={"name": "Example Company", "reference_code": "12345678"},
                                 request_only=True),
                  OpenApiExample("Field validation error", value={"error": {"code": "validation_error",
                      "fields": {"name": ["This field is required."]}}}, response_only=True, status_codes=["400"])])
    def post(self, request):
        require_api(request, "accounts.edit_portal", "customers.add_customer", scope="write")
        serializer = CustomerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = create_customer(actor=request.user, **serializer.validated_data)
        return Response(CustomerSerializer(customer).data, status=status.HTTP_201_CREATED)


class CustomerDetailAPI(APIView):
    serializer_class = CustomerSerializer

    def get(self, request, pk):
        require_api(request, "customers.view_customer")
        return Response(CustomerSerializer(get_object_or_404(Customer, pk=pk)).data)

    def put(self, request, pk):
        return self._update(request, pk, partial=False)

    def patch(self, request, pk):
        return self._update(request, pk, partial=True)

    def _update(self, request, pk, *, partial):
        require_api(request, "accounts.edit_portal", "customers.change_customer", scope="write")
        customer = get_object_or_404(Customer, pk=pk)
        serializer = CustomerSerializer(customer, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        values = {field: serializer.validated_data.get(field, getattr(customer, field)) for field in
                  ("name", "reference_code", "status", "address", "notes")}
        customer = update_customer(actor=request.user, customer_id=customer.pk, **values)
        return Response(CustomerSerializer(customer).data)


class CustomerStatusAPI(APIView):
    serializer_class = CustomerSerializer
    active = False

    @extend_schema(request=None, responses=CustomerSerializer)
    def post(self, request, pk):
        require_api(request, "accounts.edit_portal", "customers.change_customer", scope="write")
        customer = get_object_or_404(Customer, pk=pk)
        if self.active:
            customer = update_customer(actor=request.user, customer_id=customer.pk, name=customer.name,
                reference_code=customer.reference_code, status=Customer.Status.ACTIVE,
                address=customer.address, notes=customer.notes)
        else:
            customer = archive_customer(actor=request.user, customer_id=customer.pk)
        return Response(CustomerSerializer(customer).data)


class CustomerContactsAPI(APIView):
    serializer_class = ContactSerializer

    @extend_schema(responses=ContactSerializer(many=True), parameters=LIST_PARAMETERS + [
        OpenApiParameter("include_archived", bool)])
    def get(self, request, pk):
        require_api(request, "customers.view_customer", "contacts.view_contact", "contacts.view_contactpoint")
        customer = get_object_or_404(Customer, pk=pk)
        include_archived = boolean_param(request, "include_archived")
        records = associated_contacts(customer)
        if not include_archived:
            records = records.filter(is_active=True)
        records = api_contacts(records.order_by(Lower("full_name"), "id"))
        paginator = PortalPagination()
        page = paginator.paginate_queryset(records, request)
        return paginator.get_paginated_response(ContactSerializer(page, many=True).data)


class CustomerServicesAPI(APIView):
    serializer_class = AssignmentSerializer

    @extend_schema(responses=AssignmentSerializer(many=True), parameters=LIST_PARAMETERS + [
        OpenApiParameter("include_inactive", bool)])
    def get(self, request, pk):
        require_api(request, "customers.view_customer", "services.view_service", "services.view_customerservice")
        customer = get_object_or_404(Customer, pk=pk)
        include_inactive = boolean_param(request, "include_inactive")
        records = CustomerService.objects.filter(customer=customer).select_related("service")
        if not include_inactive:
            records = records.filter(status=CustomerService.Status.ACTIVE, service__is_active=True)
        paginator = PortalPagination()
        page = paginator.paginate_queryset(records.order_by("-created_at", "id"), request)
        return paginator.get_paginated_response(AssignmentSerializer(page, many=True).data)
