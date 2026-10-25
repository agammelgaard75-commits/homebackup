import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class CleanupQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Cleanup history is read-only.")

    def delete(self):
        raise ValidationError("Cleanup history is read-only.")


class CleanupOperation(models.Model):
    class Result(models.TextChoices):
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    confirmation_ref = models.UUIDField(db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    result = models.CharField(max_length=10, choices=Result.choices)
    customer_ids = models.JSONField(default=list)
    contact_ids = models.JSONField(default=list)
    counts = models.JSONField(default=dict)
    error_code = models.CharField(max_length=40, blank=True)
    objects = CleanupQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        default_permissions = ("view",)
        permissions = [("execute_cleanup", "Can permanently remove archived records")]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Cleanup history is read-only.")
        kwargs["force_insert"] = True
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Cleanup history is read-only.")
