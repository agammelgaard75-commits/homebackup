from django import forms
from django.db.models.functions import Lower

from apps.services.models import Service


class CustomerDirectoryForm(forms.Form):
    customer_q = forms.CharField(label="Customer name", required=False, max_length=200,
                                 widget=forms.TextInput(attrs={"type": "search"}))
    contact_q = forms.CharField(label="Contact name or email", required=False, max_length=200,
                                widget=forms.TextInput(attrs={"type": "search"}))
    service_q = forms.CharField(label="Service name", required=False, max_length=200,
                                widget=forms.TextInput(attrs={"type": "search"}))
    services = forms.ModelMultipleChoiceField(label="Filter by services", required=False,
        queryset=Service.objects.none(), widget=forms.SelectMultiple(attrs={"size": 5}))
    customer_status = forms.ChoiceField(label="Customers", required=False, choices=[("active", "Active"),
        ("inactive", "Archived"), ("", "All")])
    include_inactive_services = forms.BooleanField(label="Include inactive services and agreements", required=False)
    include_archived_contacts = forms.BooleanField(label="Include archived contacts", required=False)
    sort = forms.ChoiceField(label="Sort customers", choices=[("name", "Name A–Z"), ("-name", "Name Z–A")])

    def __init__(self, *args, can_view_services=True, **kwargs):
        super().__init__(*args, **kwargs)
        include_inactive = str(self.data.get("include_inactive_services", "")).lower() in ("true", "on", "1")
        services = (Service.objects.all() if include_inactive else Service.objects.filter(is_active=True)) if can_view_services else Service.objects.none()
        self.fields["services"].queryset = services.order_by(Lower("name"), "id")
