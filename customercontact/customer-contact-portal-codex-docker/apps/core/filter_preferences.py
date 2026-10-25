"""Remember non-sensitive list choices in the existing server-side session.

The browser retains only Django's secure session cookie. Search text, contact
values and free-text notes are deliberately never stored as preferences.
"""


def chosen_filters(request, key, defaults, fields, *, multiple=()):
    if request.GET.get("reset") == "1":
        request.session.pop(key, None)
        saved = {}
    else:
        saved = request.session.get(key, {})
    data = {**defaults, **{field: value for field, value in saved.items() if field in fields}}
    submitted = request.GET.get("filters") == "1"
    for field in fields:
        if submitted or field in request.GET:
            data[field] = (request.GET.getlist(field) if field in multiple else request.GET.get(field, defaults[field]))
    return data


def remember_filters(request, key, form, fields, *, multiple=()):
    if request.GET.get("reset") == "1":
        return
    if request.GET.get("filters") != "1" and not any(field in request.GET for field in fields):
        return
    values = {}
    for field in fields:
        value = form.cleaned_data[field]
        if field in multiple:
            values[field] = [str(item.pk) for item in value]
        elif hasattr(value, "pk"):
            values[field] = str(value.pk)
        else:
            values[field] = value
    if request.session.get(key) != values:
        request.session[key] = values
