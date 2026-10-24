from django import forms
from django.db.models.functions import Lower

from apps.services.models import Service


class ServiceContactSearchForm(forms.Form):
    services = forms.ModelMultipleChoiceField(
        label="Services", queryset=Service.objects.all().order_by(Lower("name"), "id"), required=False,
        widget=forms.SelectMultiple(attrs={"size": 8}),
        help_text="Choose one or more services. Use Ctrl or Command to select multiple.",
    )
    mode = forms.ChoiceField(label="Match", choices=[("any", "ANY selected service"), ("all", "ALL selected services")], initial="any")
    include_inactive_assignments = forms.BooleanField(label="Include inactive assignments", required=False)
    include_archived_customers = forms.BooleanField(label="Include archived customers", required=False)
    include_archived_contacts = forms.BooleanField(label="Include archived contacts", required=False)
    sort = forms.ChoiceField(label="Sort", choices=[("customer", "Customer name"), ("contact", "Contact name"),
                                                   ("updated", "Recently updated customer")], initial="customer")

    def clean_services(self):
        services = self.cleaned_data["services"]
        if self.is_bound and not services:
            raise forms.ValidationError("Select at least one service.")
        return services
