from django import forms
from django.core.exceptions import ValidationError
from apps.customers.models import Customer

from .models import Contact, ContactPoint


class ContactForm(forms.ModelForm):
    contact_type = forms.ChoiceField(choices=Contact.Type.choices, required=False)
    is_general = forms.BooleanField(
        label="General contact (team or shared address)", required=False,
        help_text="Select for Support Desk, Reception, Billing or another contact that is not a named person.",
    )
    customers = forms.ModelMultipleChoiceField(
        label="Associated customers", queryset=Customer.objects.all(), required=False,
        widget=forms.SelectMultiple(attrs={"size": 7}),
        help_text="Choose one or more customers. Use Ctrl or Command to select multiple. Removing a selection archives that association.",
    )

    class Meta:
        model = Contact
        fields = ("full_name", "is_general", "job_title", "department", "contact_type", "notes")
        widgets = {"notes": forms.Textarea(attrs={"rows": 5})}

    def clean_contact_type(self):
        return self.cleaned_data["contact_type"] or Contact.Type.OTHER

    def __init__(self, *args, customer=None, require_customers=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.require_customers = require_customers
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


class ContactFilterForm(forms.Form):
    q = forms.CharField(label="Search contacts", required=False, max_length=200,
                        widget=forms.TextInput(attrs={"type": "search", "placeholder": "Name, email or phone"}))
    status = forms.ChoiceField(required=False, choices=[("active", "Active"), ("archived", "Archived"), ("", "All statuses")])


class GlobalContactFilterForm(forms.Form):
    q = forms.CharField(label="Search contacts", max_length=200, required=False,
                        widget=forms.TextInput(attrs={"type": "search", "placeholder": "Name, email, phone or customer"}))
    status = forms.ChoiceField(required=False, choices=[("active", "Active"), ("archived", "Archived"), ("", "All statuses")])
    contact_type = forms.ChoiceField(label="Contact type", required=False, choices=[("", "All types"), *Contact.Type.choices])
