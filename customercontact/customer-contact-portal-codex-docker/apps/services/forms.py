from django import forms
from django.db.models.functions import Lower

from .models import CustomerService, Service


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ("name", "description", "category")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}
        help_texts = {"name": "Unique across active and archived services; case and surrounding spaces are ignored."}


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = CustomerService
        fields = ("service", "status", "start_date", "end_date", "notes")
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }
        help_texts = {
            "service": "Choose an active catalog service. Separate agreements may use the same service.",
            "status": "Status is maintained manually; dates do not automatically change it.",
            "notes": "Internal notes visible to portal staff. Maximum 10,000 characters.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["service"]
        if not self.instance._state.adding:
            field.queryset = Service.objects.filter(pk=self.instance.service_id)
            field.disabled = True
            field.help_text = "The service is retained for history. Create a separate assignment to use another service."
        else:
            field.queryset = Service.objects.filter(is_active=True).order_by(Lower("name"), "id")


class CatalogFilterForm(forms.Form):
    q = forms.CharField(label="Search services", max_length=200, required=False,
                        widget=forms.TextInput(attrs={"type": "search", "placeholder": "Name, description or category"}))
    status = forms.ChoiceField(required=False, choices=[("active", "Active"), ("archived", "Archived"), ("", "All statuses")])
    category = forms.CharField(max_length=100, required=False)


class AssignmentFilterForm(forms.Form):
    status = forms.ChoiceField(required=False, choices=[*CustomerService.Status.choices, ("", "All statuses")])


class CatalogUsageFilterForm(forms.Form):
    status = forms.ChoiceField(label="Agreement status", required=False,
                               choices=[*CustomerService.Status.choices, ("", "All statuses")])
    include_archived_customers = forms.BooleanField(label="Include archived customers", required=False)
