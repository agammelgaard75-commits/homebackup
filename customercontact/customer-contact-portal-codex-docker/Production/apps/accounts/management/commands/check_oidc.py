"""Verify provider discovery and JWKS connectivity without logging credentials."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.oidc import jwks_client, provider_metadata


class Command(BaseCommand):
    help = "Check OIDC discovery/JWKS over verified TLS; does not prove user/client login."

    def handle(self, *args, **options):
        if settings.AUTH_MODE != "oidc":
            raise CommandError("OIDC mode is required for this check.")
        try:
            provider_metadata()
            keys = jwks_client().get_signing_keys()
            if not keys:
                raise ValueError("No signing keys")
        except Exception as error:
            # Never echo HTTP bodies, URLs with credentials or library exceptions.
            raise CommandError("OIDC discovery/JWKS failed. Check DNS, trusted CA, issuer and routing.") from None
        self.stdout.write("OIDC discovery and signing keys verified over TLS. Browser login, roles and API tokens still require a staging test.")
