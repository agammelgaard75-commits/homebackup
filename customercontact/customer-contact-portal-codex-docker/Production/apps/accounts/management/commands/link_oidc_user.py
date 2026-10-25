"""Explicitly link a reviewed local account to an issuer and Keycloak subject."""
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import OIDCIdentity


class Command(BaseCommand):
    help = "Preview or explicitly link a local user to a Keycloak issuer and subject."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("issuer")
        parser.add_argument("subject")
        parser.add_argument("--apply", action="store_true", help="Persist the reviewed link")

    @transaction.atomic
    def handle(self, username, issuer, subject, apply, **options):
        issuer = issuer.rstrip("/")
        parsed = urlparse(issuer)
        if parsed.scheme != "https" or not parsed.netloc or not subject or len(subject) > 255:
            raise CommandError("Issuer must be HTTPS and subject must be 1–255 characters.")
        try:
            user = get_user_model().objects.select_for_update().get(username=username)
        except get_user_model().DoesNotExist as error:
            raise CommandError("Local user not found.") from error
        if user.is_superuser or not user.is_active:
            raise CommandError("Cannot link a superuser or inactive user.")
        if OIDCIdentity.objects.filter(user=user).exists() or OIDCIdentity.objects.filter(issuer=issuer, subject=subject).exists():
            raise CommandError("User or issuer/subject is already linked.")
        if apply:
            OIDCIdentity.objects.create(user=user, issuer=issuer, subject=subject)
            self.stdout.write("Identity link created. Portal groups will follow the next verified OIDC token.")
        else:
            self.stdout.write("Dry run: eligible for explicit issuer/subject link; use --apply after review.")
