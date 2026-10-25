import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Meta(AbstractUser.Meta):
        permissions = [
            ("access_portal", "Can access the portal"),
            ("edit_portal", "Can maintain portal business records"),
            ("administer_portal", "Can administer the portal"),
        ]


class APICredential(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="api_credentials")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="issued_api_credentials")
    name = models.CharField(max_length=100)
    secret_hash = models.CharField(max_length=64)
    scopes = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    rotated_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"API credential {self.pk}"


class OIDCIdentity(models.Model):
    """Explicit issuer/subject link; never inferred from email or display name."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="oidc_identity")
    issuer = models.URLField(max_length=500)
    subject = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["issuer", "subject"], name="unique_oidc_issuer_subject")]
