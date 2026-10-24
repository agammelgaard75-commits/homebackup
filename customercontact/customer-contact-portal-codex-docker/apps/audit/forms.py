from django import forms
from django.contrib.auth import get_user_model

from .models import AuditEvent


class AuditFilterForm(forms.Form):
    date_from = forms.DateField(label="From date (UTC)", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(label="To date (UTC)", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    actor = forms.ModelChoiceField(label="User", queryset=get_user_model().objects.none(), required=False, empty_label="All users")
    action = forms.ChoiceField(required=False, choices=[("", "All actions"), *AuditEvent.Action.choices])

    def __init__(self, *args, events, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["actor"].queryset = get_user_model().objects.filter(pk__in=events.order_by().values("actor_id")).order_by("username", "pk")

    def clean(self):
        data = super().clean()
        start, end = data.get("date_from"), data.get("date_to")
        if start and end and end < start:
            self.add_error("date_to", "To date cannot precede from date.")
        return data
