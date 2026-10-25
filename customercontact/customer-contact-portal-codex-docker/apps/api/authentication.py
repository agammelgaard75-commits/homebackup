from uuid import UUID

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.accounts.credentials import valid_credential
from apps.accounts.models import APICredential


class BearerCredentialAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if not header:
            return None
        if not header.startswith("Bearer "):
            raise AuthenticationFailed("Use a Bearer credential.")
        token = header[7:]
        if len(token) > 160 or not token.startswith("ccp_") or "." not in token:
            raise AuthenticationFailed("Invalid API credential.")
        identity, secret = token[4:].split(".", 1)
        try:
            identifier = UUID(hex=identity)
            credential = APICredential.objects.select_related("user").get(pk=identifier)
        except (ValueError, APICredential.DoesNotExist):
            raise AuthenticationFailed("Invalid API credential.") from None
        if not secret or not valid_credential(credential, secret):
            raise AuthenticationFailed("Invalid or expired API credential.")
        return credential.user, credential

    def authenticate_header(self, request):
        return 'Bearer realm="Customer Portal API"'


class BearerCredentialScheme(OpenApiAuthenticationExtension):
    target_class = "apps.api.authentication.BearerCredentialAuthentication"
    name = "BearerCredential"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "ccp_<uuid>.<secret>",
                "description": "Administrator-issued hashed credential. Scopes and the owner's portal permissions both apply."}
