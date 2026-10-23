from django import forms

from .models import Customer


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ("name", "reference_code", "status", "address", "notes")
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 6}),
        }
        help_texts = {
            "status": "Archived customers remain available in the directory's Archived filter.",
            "notes": "Internal notes visible to portal staff. Maximum 10,000 characters.",
        }


class CustomerFilterForm(forms.Form):
    q = forms.CharField(label="Search customers", max_length=200, required=False,
                        widget=forms.TextInput(attrs={"placeholder": "Name or CVR / company ID", "type": "search"}))
    status = forms.ChoiceField(required=False, choices=[("", "All statuses"), *Customer.Status.choices])
    sort = forms.ChoiceField(required=False, choices=[("name", "Name"), ("updated", "Recently updated")])
