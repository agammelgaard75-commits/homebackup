from django import forms


class SearchForm(forms.Form):
    q = forms.CharField(label="Search the portal", max_length=200, required=False,
                        widget=forms.TextInput(attrs={"type": "search", "placeholder": "Customer, person, email, phone or service", "autofocus": True}))
