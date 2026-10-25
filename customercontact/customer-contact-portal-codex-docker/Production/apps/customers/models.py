import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, RegexValidator
from django.db import models
from django.db.models.functions import Lower, Trim
from django.urls import reverse


class Customer(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    import_id = models.CharField(max_length=128, null=True, blank=True, unique=True,
        validators=[RegexValidator(r"\A[A-Za-z0-9][A-Za-z0-9._:-]*\Z", "Use a stable key starting with a letter or number.")])
    name = models.CharField(max_length=200, db_index=True)
    reference_code = models.CharField(
        "CVR / company ID", max_length=64, blank=True, default="",
        validators=[RegexValidator(
            r"\A[A-Za-z0-9][A-Za-z0-9./_-]*\Z",
            "Use letters, numbers, dots, slashes, hyphens or underscores; start with a letter or number.",
        )],
        help_text="Optional. Must be unique. Leading zeros are retained; letters are stored in uppercase.",
    )
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    address = models.TextField(blank=True, max_length=2000, validators=[MaxLengthValidator(2000)])
    notes = models.TextField(blank=True, max_length=10000, validators=[MaxLengthValidator(10000)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(name__regex=r"\S"), name="customer_name_not_blank"),
            models.CheckConstraint(
                condition=models.Q(status__in=["active", "inactive"]), name="customer_status_valid",
            ),
            models.UniqueConstraint(
                Lower(Trim("reference_code")), condition=~models.Q(reference_code=""),
                name="customer_reference_unique",
                violation_error_message="A customer with this CVR / company ID already exists.",
            ),
        ]

    def clean_fields(self, exclude=None):
        # Normalize before field validators for both forms and service callers.
        if isinstance(self.name, str):
            self.name = self.name.strip()
        self.reference_code = (self.reference_code or "").strip().upper()
        if isinstance(self.import_id, str):
            self.import_id = self.import_id.strip() or None
        super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        if not self.name or not self.name.strip():
            raise ValidationError({"name": "Enter a customer name."})

    def get_absolute_url(self):
        return reverse("customers:detail", args=[self.pk])

    def __str__(self):
        return self.name
