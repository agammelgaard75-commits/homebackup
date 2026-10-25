import uuid
from datetime import date

from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models
from django.db.models.functions import Lower, Trim
from django.urls import reverse


class Service(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, max_length=1000, validators=[MaxLengthValidator(1000)])
    category = models.CharField(max_length=100, blank=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(name__regex=r"\S"), name="service_name_not_blank"),
            models.UniqueConstraint(
                Lower(Trim("name")), name="service_name_unique",
                violation_error_message="A service with this name already exists, including archived services.",
            ),
        ]

    def clean_fields(self, exclude=None):
        self.name = self.name.strip() if isinstance(self.name, str) else self.name
        self.category = self.category.strip() if isinstance(self.category, str) else self.category
        super().clean_fields(exclude=exclude)

    def get_absolute_url(self):
        return reverse("services:detail", args=[self.pk])

    def __str__(self):
        return self.name


class CustomerService(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        EXPIRED = "expired", "Expired"
        TERMINATED = "terminated", "Terminated"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="service_assignments")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="assignments")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True, max_length=10000, validators=[MaxLengthValidator(10000)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "id"]
        indexes = [models.Index(fields=["customer", "status"], name="assignment_customer_status")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["active", "suspended", "expired", "terminated"]),
                name="assignment_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(start_date__isnull=True) | models.Q(end_date__isnull=True)
                | models.Q(end_date__gte=models.F("start_date")), name="assignment_dates_valid",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        # Field validation may already have rejected a malformed date.
        if isinstance(self.start_date, date) and isinstance(self.end_date, date) and self.end_date < self.start_date:
            errors["end_date"] = "End date cannot precede start date."
        if not self._state.adding:
            original = type(self).objects.filter(pk=self.pk).values("customer_id", "service_id").first()
            if original and (original["customer_id"] != self.customer_id or original["service_id"] != self.service_id):
                errors["__all__"] = "An assignment's customer and service cannot be changed. Create a separate assignment."
        if errors:
            raise ValidationError(errors)

    def get_absolute_url(self):
        return reverse("customer_services:detail", args=[self.customer_id, self.pk])

    def __str__(self):
        return f"Assignment {self.pk}"
