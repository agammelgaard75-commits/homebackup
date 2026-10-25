from django.contrib.auth import get_user_model
from django.conf import settings
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.credentials import issue_credential, revoke_credential, rotate_credential
from apps.accounts.models import APICredential
from apps.api.common import require_api
from apps.api.pagination import PortalPagination
from apps.api.serializers import CredentialCreateSerializer, CredentialSerializer
from apps.api.schema import CredentialIssueResponse, CurrentUserResponse, DashboardResponse
from apps.contacts.models import Contact
from apps.customers.models import Customer
from apps.services.models import CustomerService


class CurrentUserAPI(APIView):
    serializer_class = CurrentUserResponse

    def get(self, request):
        require_api(request)
        return Response({"id": request.user.pk, "username": request.user.get_username(),
                         "roles": list(request.user.groups.values_list("name", flat=True).order_by("name"))})


class DashboardSummaryAPI(APIView):
    serializer_class = DashboardResponse

    def get(self, request):
        require_api(request, "customers.view_customer", "contacts.view_contact", "services.view_customerservice")
        return Response({"active_customers": Customer.objects.filter(status=Customer.Status.ACTIVE).count(),
                         "active_contacts": Contact.objects.filter(is_active=True).count(),
                         "active_assignments": CustomerService.objects.filter(
                             status=CustomerService.Status.ACTIVE).count()})


class CredentialListAPI(APIView):
    serializer_class = CredentialSerializer

    def _check(self, request, scope):
        require_api(request, "accounts.administer_portal", scope=scope)
        if settings.AUTH_MODE == "oidc":
            raise PermissionDenied("Legacy API credentials are disabled in OIDC mode.")
        if isinstance(request.auth, APICredential):
            raise PermissionDenied("Manage credentials with an administrator browser session.")

    def get(self, request):
        self._check(request, "read")
        paginator = PortalPagination()
        page = paginator.paginate_queryset(APICredential.objects.select_related("user").all(), request)
        return paginator.get_paginated_response(CredentialSerializer(page, many=True).data)

    @extend_schema(request=CredentialCreateSerializer, responses={201: CredentialIssueResponse})
    def post(self, request):
        self._check(request, "write")
        serializer = CredentialCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        user = get_object_or_404(get_user_model(), pk=values["user_id"])
        credential, token = issue_credential(actor=request.user, user=user, name=values["name"],
            scopes=values["scopes"], expires_at=values["expires_at"])
        return Response({**CredentialSerializer(credential).data, "token": token}, status=status.HTTP_201_CREATED)


class CredentialActionAPI(APIView):
    serializer_class = CredentialSerializer
    action = None

    @extend_schema(request=None, responses=CredentialIssueResponse)
    def post(self, request, pk):
        require_api(request, "accounts.administer_portal", scope="write")
        if settings.AUTH_MODE == "oidc":
            raise PermissionDenied("Legacy API credentials are disabled in OIDC mode.")
        if isinstance(request.auth, APICredential):
            raise PermissionDenied("Manage credentials with an administrator browser session.")
        credential = get_object_or_404(APICredential, pk=pk)
        if self.action == "revoke":
            credential = revoke_credential(actor=request.user, credential=credential)
            return Response(CredentialSerializer(credential).data)
        token = rotate_credential(actor=request.user, credential=credential)
        return Response({**CredentialSerializer(credential).data, "token": token})
