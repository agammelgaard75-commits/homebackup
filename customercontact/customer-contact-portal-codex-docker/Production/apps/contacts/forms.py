from django import forms
from django.forms import BaseFormSet, formset_factory
from django.core.exceptions import ValidationError
from apps.customers.models import Customer

from .models import Contact, ContactPoint
from .validation import CONTACT_METHOD_REQUIRED, normalize_contact_value


class ContactForm(forms.ModelForm):
    primary_email = forms.EmailField(label="Email address", required=False,
                                     help_text="Enter an email address here, or add a phone number below.")
    contact_type = forms.ChoiceField(choices=Contact.Type.choices, required=False, initial=Contact.Type.TECHNICAL)
    is_general = forms.BooleanField(
        label="General contact (team or shared address)", required=False,
        help_text="Select for Support Desk, Reception, Billing or another contact that is not a named person.",
    )
    customers = forms.ModelMultipleChoiceField(
        label="Associated customers", queryset=Customer.objects.all(), required=False,
        widget=forms.SelectMultiple(attrs={"size": 7}),
        help_text="Choose one or more customers. Use Ctrl or Command to select multiple. Removing a selection archives that association.",
    )
    include_archived_customers = forms.BooleanField(label="Include archived customers in the selection", required=False)

    class Meta:
        model = Contact
        fields = ("full_name", "primary_email", "is_general", "job_title", "department", "contact_type", "notes")
        widgets = {"notes": forms.Textarea(attrs={"rows": 5})}

    def clean_contact_type(self):
        return self.cleaned_data["contact_type"] or (
            self.instance.contact_type if not self.instance._state.adding else Contact.Type.TECHNICAL
        )

    def __init__(self, *args, customer=None, require_customers=False, include_archived_customers=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.require_customers = require_customers
        self.fields["customers"].queryset = (Customer.objects.all() if include_archived_customers
                                              else Customer.objects.filter(status=Customer.Status.ACTIVE))
        if not self.instance._state.adding:
            self.fields.pop("primary_email")
        if customer and self.instance._state.adding:
            self.initial.setdefault("customers", [customer.pk])
        elif not self.instance._state.adding:
            from .selectors import active_customer_ids
            self.initial.setdefault("customers", active_customer_ids(self.instance))
        self.fields["customers"].required = require_customers

    def clean_customers(self):
        selected = self.cleaned_data["customers"]
        if self.require_customers and not selected:
            raise ValidationError("Select at least one customer.")
        return selected


class ContactPointForm(forms.Form):
    kind = forms.ChoiceField(choices=ContactPoint.Kind.choices)
    label = forms.ChoiceField(choices=ContactPoint.Label.choices, required=False)
    value = forms.CharField(max_length=254, help_text="Email, or a phone with 7–15 digits. Phone formatting is retained; extensions are not supported.")
    is_primary = forms.BooleanField(required=False, help_text="Replaces the current primary of this kind for this owner. Archived details must be restored first.")

    def __init__(self, *args, customer, contact=None, **kwargs):
        self.customer = customer
        self.contact = contact
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        cleaned["label"] = cleaned.get("label") or ContactPoint.Label.OTHER
        if not self.errors:
            candidate = ContactPoint(customer=self.customer, contact=self.contact, **cleaned)
            try:
                candidate.full_clean(validate_constraints=False)
            except ValidationError as error:
                for field, errors in error.message_dict.items():
                    self.add_error(field if field in self.fields else None, errors)
        return cleaned


class ContactMethodForm(forms.Form):
    point_id = forms.UUIDField(required=False, widget=forms.HiddenInput)
    kind = forms.ChoiceField(label="Type", choices=[("", "Choose email or phone"), *ContactPoint.Kind.choices], required=False)
    value = forms.CharField(label="Email address or phone number", required=False, max_length=254)
    label = forms.ChoiceField(choices=[("", "Other"), *ContactPoint.Label.choices], required=False)
    is_primary = forms.BooleanField(label="Primary", required=False)
    remove = forms.BooleanField(label="Archive this detail", required=False)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("remove"):
            return cleaned
        kind, value = cleaned.get("kind"), (cleaned.get("value") or "").strip()
        if not kind and not value and not cleaned.get("point_id"):
            cleaned["empty"] = True
            return cleaned
        if not kind:
            self.add_error("kind", "Select email or phone.")
        if not value:
            self.add_error("value", "Enter an email address or phone number.")
        if kind and value:
            try:
                normalize_contact_value(kind, value)
            except ValidationError as error:
                self.add_error("value", error)
        cleaned["value"] = value
        cleaned["label"] = cleaned.get("label") or ContactPoint.Label.OTHER
        return cleaned


class BaseContactMethodFormSet(BaseFormSet):
    has_primary_email = False

    def clean(self):
        if not self.has_primary_email and not any(not form.errors and form.cleaned_data and not form.cleaned_data.get("empty")
                   and not form.cleaned_data.get("remove") and form.cleaned_data.get("kind")
                   and form.cleaned_data.get("value") for form in self.forms):
            raise ValidationError(CONTACT_METHOD_REQUIRED)


ContactMethodFormSet = formset_factory(ContactMethodForm, formset=BaseContactMethodFormSet, extra=4)


def initial_contact_methods(contact):
    if contact is None:
        return []
    return [{"point_id": point.pk, "kind": point.kind, "value": point.value, "label": point.label,
             "is_primary": point.is_primary}
            for point in contact.points.filter(is_active=True).order_by("kind", "-is_primary", "id")]


class ContactFilterForm(forms.Form):
    q = forms.CharField(label="Search contacts", required=False, max_length=200,
                        widget=forms.TextInput(attrs={"type": "search", "placeholder": "Name, email or phone"}))
    status = forms.ChoiceField(required=False, choices=[("active", "Active"), ("archived", "Archived"), ("", "All statuses")])


class GlobalContactFilterForm(forms.Form):
    q = forms.CharField(label="Search contacts", max_length=200, required=False,
                        widget=forms.TextInput(attrs={"type": "search", "placeholder": "Name, email, phone or customer"}))
    status = forms.ChoiceField(required=False, choices=[("active", "Active"), ("archived", "Archived"), ("", "All statuses")])
    contact_type = forms.ChoiceField(label="Contact type", required=False, choices=[("", "All types"), *Contact.Type.choices])
    include_archived_customers = forms.BooleanField(label="Include contacts under archived customers", required=False)


class ContactPointFilterForm(forms.Form):
    status = forms.ChoiceField(label="Details", choices=[("active", "Active"), ("archived", "Archived"), ("", "All statuses")])
    include_archived_customers = forms.BooleanField(label="Show archived customer associations", required=False)
