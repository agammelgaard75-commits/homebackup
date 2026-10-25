import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models
from django.urls import reverse

from .validation import normalize_contact_value


class Contact(models.Model):
    class Type(models.TextChoices):
        TECHNICAL = "technical", "Technical"
        MANAGEMENT = "management", "Management"
        BILLING = "billing", "Billing"
        SUPPORT = "support", "Support"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="contacts")
    full_name = models.CharField("Name", max_length=200)
    job_title = models.CharField(max_length=200, blank=True)
    department = models.CharField(max_length=200, blank=True)
    contact_type = models.CharField(max_length=10, choices=Type.choices, default=Type.TECHNICAL)
    is_general = models.BooleanField(default=False, help_text="Use for a team or shared contact such as Support Desk or Reception.")
    notes = models.TextField(blank=True, max_length=10000, validators=[MaxLengthValidator(10000)])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name", "id"]
        indexes = [models.Index(fields=["customer", "full_name"], name="contact_customer_name_idx")]
        constraints = [
            models.CheckConstraint(condition=models.Q(full_name__regex=r"\S"), name="contact_name_not_blank"),
            models.CheckConstraint(condition=models.Q(contact_type__in=["technical", "management", "billing", "support", "other"]), name="contact_type_valid"),
            models.UniqueConstraint(fields=["id", "customer"], name="contact_id_customer_unique"),
        ]

    def clean_fields(self, exclude=None):
        if isinstance(self.full_name, str):
            self.full_name = self.full_name.strip()
        super().clean_fields(exclude=exclude)

    def clean(self):
        if not self.full_name or not self.full_name.strip():
            raise ValidationError({"full_name": "Enter a contact name."})
        if not self._state.adding and Contact.objects.filter(pk=self.pk).exclude(customer_id=self.customer_id).exists():
            raise ValidationError({"customer": "A contact cannot be moved to another customer."})

    def get_absolute_url(self):
        # The original customer remains a stable provenance/point owner. The
        # current URL follows an active association if that link is retired.
        if hasattr(self, "active_customer_links"):
            association = min(self.active_customer_links, key=lambda link: (link.created_at, link.customer_id), default=None)
        else:
            association = self.customer_links.filter(is_active=True).order_by("created_at", "customer_id").first()
        return reverse("contacts:detail", args=[association.customer_id if association else self.customer_id, self.pk])

    def __str__(self):
        # Avoid accidental contact name/email disclosure in generic object logs.
        return f"Contact {self.pk}"


class ContactCustomer(models.Model):
    """The authoritative current customer membership for a shared contact."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contact = models.ForeignKey(Contact, on_delete=models.PROTECT, related_name="customer_links")
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="contact_links")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["customer__name", "id"]
        constraints = [models.UniqueConstraint(fields=["contact", "customer"], name="contact_customer_pair_unique")]
        indexes = [models.Index(fields=["customer", "is_active"], name="contact_link_customer_active")]

    def clean(self):
        if not self._state.adding and type(self).objects.filter(pk=self.pk).exclude(contact_id=self.contact_id, customer_id=self.customer_id).exists():
            raise ValidationError("Contact and customer on an association cannot be changed.")

    def __str__(self):
        return f"Contact association {self.pk}"


class ContactPoint(models.Model):
    class Kind(models.TextChoices):
        EMAIL = "email", "Email"
        PHONE = "phone", "Phone"

    class Label(models.TextChoices):
        WORK = "work", "Work"
        MOBILE = "mobile", "Mobile"
        DIRECT = "direct", "Direct"
        SUPPORT = "support", "Support"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="contact_points")
    contact = models.ForeignKey(Contact, on_delete=models.PROTECT, related_name="points")
    kind = models.CharField(max_length=5, choices=Kind.choices)
    label = models.CharField(max_length=7, choices=Label.choices, default=Label.OTHER)
    value = models.CharField(max_length=254)
    normalized_value = models.CharField(max_length=254, editable=False, blank=True, db_index=True)
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kind", "-is_active", "-is_primary", "label", "id"]
        indexes = [models.Index(fields=["customer", "kind"], name="point_customer_kind_idx")]
        constraints = [
            models.CheckConstraint(condition=models.Q(kind__in=["email", "phone"]), name="point_kind_valid"),
            models.CheckConstraint(condition=models.Q(label__in=["work", "mobile", "direct", "support", "other"]), name="point_label_valid"),
            models.CheckConstraint(condition=models.Q(value__regex=r"\S"), name="point_value_not_blank"),
            models.CheckConstraint(condition=~models.Q(normalized_value=""), name="point_normalized_not_blank"),
            models.UniqueConstraint(fields=["contact", "kind"], condition=models.Q(contact__isnull=False, is_primary=True, is_active=True), name="person_primary_point_unique"),
        ]

    def clean_fields(self, exclude=None):
        self.value = (self.value or "").strip()
        super().clean_fields(exclude=exclude)

    def clean(self):
        errors = {}
        try:
            self.normalized_value = normalize_contact_value(self.kind, self.value)
        except ValidationError as error:
            errors["value"] = error.messages
        if self.contact_id and self.customer_id:
            if not Contact.objects.filter(pk=self.contact_id, customer_id=self.customer_id).exists():
                errors["contact"] = "The contact must belong to this customer."
        if not self._state.adding:
            if ContactPoint.objects.filter(pk=self.pk).exclude(customer_id=self.customer_id, contact_id=self.contact_id).exists():
                errors["contact"] = "Contact detail ownership cannot be changed."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Contact detail {self.pk}"
