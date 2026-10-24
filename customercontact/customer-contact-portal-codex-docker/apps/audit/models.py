import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class AuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Audit records are read-only.")

    def delete(self):
        raise ValidationError("Audit records are read-only.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("Audit records are read-only.")


class AuditEvent(models.Model):
    class Action(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        ARCHIVED = "archived", "Archived"
        RESTORED = "restored", "Restored"
        ASSIGNED = "assigned", "Assigned"
        ACTIVATED = "activated", "Activated"
        SUSPENDED = "suspended", "Suspended"
        EXPIRED = "expired", "Expired"
        TERMINATED = "terminated", "Terminated"

    class ObjectType(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        CONTACT = "contact", "Contact"
        CONTACT_POINT = "contact_point", "Contact detail"
        SERVICE = "service", "Catalog service"
        CUSTOMER_SERVICE = "customer_service", "Service assignment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="audit_events")
    action = models.CharField(max_length=12, choices=Action.choices, db_index=True)
    object_type = models.CharField(max_length=20, choices=ObjectType.choices)
    object_id = models.UUIDField()
    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.PROTECT, related_name="activity_events")
    description = models.CharField(max_length=100)
    changed_fields = models.JSONField(default=list)
    objects = AuditQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        default_permissions = ("view",)
        permissions = [("view_customer_activity", "Can view permitted customer activity")]
        indexes = [
            models.Index(fields=["-created_at", "-id"], name="audit_newest"),
            models.Index(fields=["customer", "-created_at", "-id"], name="audit_customer_newest"),
            models.Index(fields=["object_type", "object_id"], name="audit_object"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(action__in=["created", "updated", "archived", "restored", "assigned", "activated", "suspended", "expired", "terminated"]), name="audit_action_valid"),
            models.CheckConstraint(condition=models.Q(object_type__in=["customer", "contact", "contact_point", "service", "customer_service"]), name="audit_object_type_valid"),
            models.CheckConstraint(condition=(models.Q(object_type="service", customer__isnull=True) | (~models.Q(object_type="service") & models.Q(customer__isnull=False))), name="audit_customer_scope"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Audit records are read-only.")
        # Never let a new instance with an existing UUID fall back to UPDATE.
        kwargs["force_insert"] = True
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit records are read-only.")

    def __str__(self):
        return f"Audit event {self.pk}"
