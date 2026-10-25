from django import forms
from django.db.models.functions import Lower

from apps.services.models import Service


class ServiceContactSearchForm(forms.Form):
    services = forms.ModelMultipleChoiceField(
        label="Services", queryset=Service.objects.none(), required=False,
        widget=forms.SelectMultiple(attrs={"size": 8}),
        help_text="Choose one or more services. Use Ctrl or Command to select multiple.",
    )
    include_archived_services = forms.BooleanField(label="Include archived catalog services", required=False)
    mode = forms.ChoiceField(label="Match", choices=[("any", "ANY selected service"), ("all", "ALL selected services")], initial="any")
    include_inactive_assignments = forms.BooleanField(label="Include inactive assignments", required=False)
    include_archived_customers = forms.BooleanField(label="Include archived customers", required=False)
    include_archived_contacts = forms.BooleanField(label="Include archived contacts", required=False)
    sort = forms.ChoiceField(label="Sort", choices=[("customer", "Customer name"), ("contact", "Contact name"),
                                                   ("updated", "Recently updated customer")], initial="customer")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        include_archived = self.data.get("include_archived_services") in (True, "on", "true", "True", "1") if self.is_bound else False
        records = Service.objects.all() if include_archived else Service.objects.filter(is_active=True)
        self.fields["services"].queryset = records.order_by(Lower("name"), "id")

    def clean_services(self):
        services = self.cleaned_data["services"]
        if self.is_bound and not services:
            raise forms.ValidationError("Select at least one service.")
        return services
