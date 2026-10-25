from django.shortcuts import get_object_or_404
from django.db.models.functions import Lower
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.common import boolean_param, choice_param, limited_query, require_api
from apps.api.pagination import PortalPagination
from apps.api.schema import LIST_PARAMETERS, ContactAssociationRequest, ContactAssociationResponse
from apps.api.serializers import ContactPointSerializer, ContactSerializer, ContactWriteSerializer, MethodWriteSerializer, api_contacts
from apps.customers.models import Customer

from .models import Contact, ContactPoint
from .selectors import active_customer_ids, associated_contacts, global_contacts
from .services import (create_contact, save_contact_point, set_contact_active, set_contact_customers,
                       set_point_active, update_contact)

READ = ("customers.view_customer", "contacts.view_contact", "contacts.view_contactpoint")


def _owner(contact):
    ids = active_customer_ids(contact)
    if not ids:
        raise ValidationError({"customer_ids": ["This contact has no active customer association."]})
    return sorted(ids, key=str)[0]


def _serialized(contact):
    return ContactSerializer(api_contacts(Contact.objects.all()).get(pk=contact.pk)).data


class ContactListAPI(APIView):
    serializer_class = ContactSerializer

    @extend_schema(operation_id="contacts_list", responses=ContactSerializer(many=True),
        parameters=LIST_PARAMETERS + [OpenApiParameter("q", str, description="Name, email, phone, or customer substring."),
            OpenApiParameter("status", str, enum=["active", "archived", "all"]),
            OpenApiParameter("contact_type", str), OpenApiParameter("customer_id", str),
            OpenApiParameter("include_archived_customers", bool),
            OpenApiParameter("sort", str, enum=["name", "-name", "updated"])])
    def get(self, request):
        require_api(request, *READ)
        selected_status = choice_param(request, "status", ("active", "archived", "all"), "active")
        selected_type = choice_param(request, "contact_type", ("", *Contact.Type.values), "")
        selected_sort = choice_param(request, "sort", ("name", "-name", "updated"), "name")
        records = global_contacts(q=limited_query(request), status="" if selected_status == "all" else selected_status,
            contact_type=selected_type, include_archived_customers=boolean_param(request, "include_archived_customers"))
        if request.query_params.get("customer_id"):
            customer = get_object_or_404(Customer, pk=request.query_params["customer_id"])
            records = records.filter(pk__in=associated_contacts(customer).values("pk"))
        order = {"name": (Lower("full_name"), "id"), "-name": (Lower("full_name").desc(), "id"),
                 "updated": ("-updated_at", "id")}[selected_sort]
        paginator = PortalPagination()
        page = paginator.paginate_queryset(api_contacts(records.order_by(*order)), request)
        return paginator.get_paginated_response(ContactSerializer(page, many=True).data)

    @extend_schema(request=ContactWriteSerializer, responses={201: ContactSerializer})
    def post(self, request):
        require_api(request, *READ, "accounts.edit_portal", "contacts.add_contact", scope="write")
        serializer = ContactWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        customer_ids = values.pop("customer_ids", None)
        methods = values.pop("methods", None)
        if not customer_ids:
            raise ValidationError({"customer_ids": ["Select at least one customer."]})
        if not methods:
            raise ValidationError({"methods": ["At least one email address or phone number is required."]})
        contact = create_contact(actor=request.user, customer_id=customer_ids[0], customer_ids=customer_ids,
                                 methods=methods, **values)
        return Response(_serialized(contact), status=status.HTTP_201_CREATED)


class ContactDetailAPI(APIView):
    serializer_class = ContactSerializer

    def get(self, request, pk):
        require_api(request, *READ)
        return Response(_serialized(get_object_or_404(Contact, pk=pk)))

    @extend_schema(request=ContactWriteSerializer, responses=ContactSerializer)
    def put(self, request, pk):
        return self._update(request, pk, partial=False)

    @extend_schema(request=ContactWriteSerializer, responses=ContactSerializer)
    def patch(self, request, pk):
        return self._update(request, pk, partial=True)

    def _update(self, request, pk, *, partial):
        require_api(request, *READ, "accounts.edit_portal", "contacts.change_contact", scope="write")
        contact = get_object_or_404(Contact, pk=pk)
        serializer = ContactWriteSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        values = {field: data.get(field, getattr(contact, field)) for field in
                  ("full_name", "job_title", "department", "contact_type", "is_general", "notes")}
        if "customer_ids" in data:
            values["customer_ids"] = data["customer_ids"]
        if "methods" in data:
            values["methods"] = data["methods"]
        contact = update_contact(actor=request.user, customer_id=_owner(contact), contact_id=contact.pk, **values)
        return Response(_serialized(contact))


class ContactStatusAPI(APIView):
    serializer_class = ContactSerializer
    active = False

    @extend_schema(request=None, responses=ContactSerializer)
    def post(self, request, pk):
        require_api(request, *READ, "accounts.edit_portal", "contacts.change_contact", scope="write")
        contact = get_object_or_404(Contact, pk=pk)
        contact = set_contact_active(actor=request.user, customer_id=_owner(contact),
                                     contact_id=contact.pk, is_active=self.active)
        return Response(_serialized(contact))


class ContactMethodsAPI(APIView):
    serializer_class = ContactPointSerializer

    @extend_schema(operation_id="contact_methods_list", responses=ContactPointSerializer(many=True),
                   parameters=LIST_PARAMETERS + [OpenApiParameter("include_archived", bool)])
    def get(self, request, pk):
        require_api(request, *READ)
        contact = get_object_or_404(Contact, pk=pk)
        records = contact.points.all() if boolean_param(request, "include_archived") else contact.points.filter(is_active=True)
        paginator = PortalPagination()
        page = paginator.paginate_queryset(records.order_by("kind", "-is_primary", "id"), request)
        return paginator.get_paginated_response(ContactPointSerializer(page, many=True).data)

    @extend_schema(request=MethodWriteSerializer, responses={201: ContactPointSerializer})
    def post(self, request, pk):
        require_api(request, *READ, "accounts.edit_portal", "contacts.add_contactpoint", scope="write")
        contact = get_object_or_404(Contact, pk=pk)
        serializer = MethodWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data.get("remove") or data.get("point_id"):
            raise ValidationError({"method": ["Use this endpoint to create a new method."]})
        point = save_contact_point(actor=request.user, customer_id=_owner(contact), contact_id=contact.pk,
                                   kind=data["kind"], value=data["value"], label=data["label"],
                                   is_primary=data["is_primary"])
        return Response(ContactPointSerializer(point).data, status=status.HTTP_201_CREATED)


class ContactMethodDetailAPI(APIView):
    serializer_class = ContactPointSerializer

    def get(self, request, pk, point_pk):
        require_api(request, *READ)
        return Response(ContactPointSerializer(get_object_or_404(ContactPoint, pk=point_pk, contact_id=pk)).data)

    def put(self, request, pk, point_pk):
        return self._update(request, pk, point_pk, partial=False)

    def patch(self, request, pk, point_pk):
        return self._update(request, pk, point_pk, partial=True)

    def _update(self, request, pk, point_pk, *, partial):
        require_api(request, *READ, "accounts.edit_portal", "contacts.change_contactpoint", scope="write")
        contact = get_object_or_404(Contact, pk=pk)
        point = get_object_or_404(ContactPoint, pk=point_pk, contact=contact)
        if not point.is_active:
            raise ValidationError({"method": ["Restore this method before editing it."]})
        serializer = ContactPointSerializer(point, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        data = {field: serializer.validated_data.get(field, getattr(point, field)) for field in
                ("kind", "value", "label", "is_primary")}
        point = save_contact_point(actor=request.user, customer_id=_owner(contact), contact_id=contact.pk,
                                   point_id=point.pk, **data)
        return Response(ContactPointSerializer(point).data)


class ContactMethodStatusAPI(APIView):
    serializer_class = ContactPointSerializer
    active = False

    @extend_schema(request=None, responses=ContactPointSerializer)
    def post(self, request, pk, point_pk):
        require_api(request, *READ, "accounts.edit_portal", "contacts.change_contactpoint", scope="write")
        contact = get_object_or_404(Contact, pk=pk)
        get_object_or_404(ContactPoint, pk=point_pk, contact=contact)
        point = set_point_active(actor=request.user, customer_id=_owner(contact), contact_id=contact.pk,
                                 point_id=point_pk, is_active=self.active)
        return Response(ContactPointSerializer(point).data)


class ContactCustomersAPI(APIView):
    serializer_class = ContactSerializer

    @extend_schema(responses=ContactAssociationResponse(many=True),
                   parameters=[OpenApiParameter("include_archived", bool)])
    def get(self, request, pk):
        require_api(request, *READ)
        contact = get_object_or_404(Contact, pk=pk)
        records = contact.customer_links.all() if boolean_param(request, "include_archived") else contact.customer_links.filter(is_active=True)
        return Response([{"customer_id": str(link.customer_id), "is_active": link.is_active,
                          "created_at": link.created_at.isoformat(), "updated_at": link.updated_at.isoformat()}
                         for link in records.order_by("customer_id")])

    @extend_schema(request=ContactAssociationRequest, responses=ContactSerializer)
    def post(self, request, pk):
        require_api(request, *READ, "accounts.edit_portal", "contacts.change_contact", scope="write")
        contact = get_object_or_404(Contact, pk=pk)
        customer_id = request.data.get("customer_id")
        if not customer_id:
            raise ValidationError({"customer_id": ["Required."]})
        customer = get_object_or_404(Customer, pk=customer_id)
        owner = _owner(contact)
        selected = set(active_customer_ids(contact)) | {customer.pk}
        set_contact_customers(actor=request.user, customer_id=owner, contact_id=contact.pk, customer_ids=selected)
        return Response(_serialized(contact))


class ContactCustomerRemoveAPI(APIView):
    serializer_class = ContactSerializer

    @extend_schema(request=None, responses=ContactSerializer)
    def post(self, request, pk, customer_pk):
        require_api(request, *READ, "accounts.edit_portal", "contacts.change_contact", scope="write")
        contact = get_object_or_404(Contact, pk=pk)
        selected = set(active_customer_ids(contact))
        if customer_pk not in selected:
            raise ValidationError({"customer_id": ["This customer is not currently associated."]})
        remaining = selected - {customer_pk}
        if not remaining:
            raise ValidationError({"customer_id": ["A contact must retain at least one customer."]})
        set_contact_customers(actor=request.user, customer_id=_owner(contact), contact_id=contact.pk,
                              customer_ids=remaining)
        return Response(_serialized(contact))
