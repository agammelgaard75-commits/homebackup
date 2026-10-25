from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from apps.customers.models import Customer
from apps.core.filter_preferences import chosen_filters, remember_filters
from apps.core.json_import import import_reference, import_workflow

from .forms import (ContactFilterForm, ContactForm, ContactPointFilterForm, ContactPointForm,
                    GlobalContactFilterForm, ContactMethodFormSet, initial_contact_methods)
from .models import Contact, ContactPoint
from .permissions import contact_access, require_access
from .selectors import associated_contacts, directory_results, is_associated, active_customer_ids, global_contacts
from .services import create_contact, update_contact, set_contact_active, save_contact_point, set_point_active
from .imports import confirm_contacts, manifest as contact_manifest, preview_contacts


def _owner(customer_pk, contact_pk=None):
    customer = get_object_or_404(Customer, pk=customer_pk)
    contact = get_object_or_404(associated_contacts(customer), pk=contact_pk) if contact_pk else None
    return customer, contact


def _legacy_redirect(request, customer_pk, contact_pk):
    """A removed origin link keeps its old GET URL pointing to the contact."""
    if request.method not in ("GET", "HEAD") or contact_pk is None:
        return None
    contact = Contact.objects.filter(pk=contact_pk, customer_id=customer_pk).first()
    if contact and not is_associated(contact, customer_pk):
        return redirect(contact.get_absolute_url())
    return None


def _back_url(customer, contact=None):
    if contact:
        return reverse("contacts:detail", args=[customer.pk, contact.pk]) if is_associated(contact, customer.pk) else contact.get_absolute_url()
    return reverse("contacts:list", args=[customer.pk])


def _form_errors(form, error):
    if hasattr(error, "message_dict"):
        for field, errors in error.message_dict.items():
            form.add_error(field if field in form.fields else None, errors)
    else:
        form.add_error(None, error)


@contact_access()
@require_safe
@never_cache
def contact_list(request, customer_pk):
    customer = get_object_or_404(Customer, pk=customer_pk)
    key = f"contacts.customer.{customer.pk}"
    choices = ("status",)
    selected = chosen_filters(request, key, {"status": "active"}, choices)
    filters = ContactFilterForm({**selected, "q": request.GET.get("q", "")})
    people, filter_query = Contact.objects.none(), ""
    valid = filters.is_valid()
    if valid:
        remember_filters(request, key, filters, choices)
        query, status = filters.cleaned_data["q"], filters.cleaned_data["status"]
        people = directory_results(customer, query, status)
        filter_query = urlencode({"q": query, "status": status})
    page = Paginator(people, 25).get_page(request.GET.get("page"))
    return render(request, "contacts/list.html", {
        "customer": customer, "filter_form": filters, "page_obj": page,
        "filter_query": filter_query,
    }, status=200 if valid else 400)


@contact_access()
@require_safe
@never_cache
def contact_detail(request, customer_pk, pk):
    stale = _legacy_redirect(request, customer_pk, pk)
    if stale:
        return stale
    customer, contact = _owner(customer_pk, pk)
    return _render_contact_detail(request, customer, contact)


def _render_contact_detail(request, customer, contact, *, edit_form=None, edit_methods=None, status=200):
    key = f"contacts.details.{contact.pk}"
    choices = ("status", "include_archived_customers")
    selected = chosen_filters(request, key, {"status": "active", "include_archived_customers": False}, choices)
    point_filters = ContactPointFilterForm(selected)
    valid = point_filters.is_valid()
    points = contact.points.all() if valid else contact.points.none()
    if valid:
        remember_filters(request, key, point_filters, choices)
        if point_filters.cleaned_data["status"]:
            points = points.filter(is_active=point_filters.cleaned_data["status"] == "active")
    linked_customers = Customer.objects.filter(pk__in=active_customer_ids(contact))
    if not point_filters.cleaned_data.get("include_archived_customers"):
        linked_customers = linked_customers.filter(status=Customer.Status.ACTIVE)
    linked_customers = linked_customers.order_by("name", "pk")
    can_edit = request.user.has_perms(("accounts.edit_portal", "contacts.change_contact"))
    if can_edit and edit_form is None:
        edit_form = ContactForm(instance=contact, customer=customer,
                                include_archived_customers=customer.status == Customer.Status.INACTIVE)
    if can_edit and edit_methods is None:
        edit_methods = ContactMethodFormSet(initial=initial_contact_methods(contact), prefix="methods")
    return render(request, "contacts/detail.html", {"customer": customer, "contact": contact, "points": points,
                  "point_filter_form": point_filters, "linked_customers": linked_customers,
                  "edit_form": edit_form, "edit_methods": edit_methods}, status=status if valid else 400)


@contact_access()
@require_http_methods(["GET", "POST"])
@never_cache
def contact_form(request, customer_pk, pk=None):
    require_access(request.user, "contacts.change_contact" if pk else "contacts.add_contact")
    stale = _legacy_redirect(request, customer_pk, pk)
    if stale:
        return stale
    customer, contact = _owner(customer_pk, pk)
    include_archived = (request.POST.get("include_archived_customers") == "on" or customer.status == Customer.Status.INACTIVE if request.method == "POST"
                        else request.GET.get("include_archived_customers") == "1" or customer.status == Customer.Status.INACTIVE)
    form = ContactForm(request.POST if request.method == "POST" else None, instance=contact or Contact(customer=customer),
                       customer=customer, include_archived_customers=include_archived)
    if request.method == "GET":
        form.initial["include_archived_customers"] = include_archived
    method_formset = (ContactMethodFormSet(request.POST if request.method == "POST" else None,
                                          initial=initial_contact_methods(contact), prefix="methods")
                      if request.method != "POST" or not contact or "methods-TOTAL_FORMS" in request.POST else None)
    if request.method == "POST":
        form_valid = form.is_valid()
        primary_email = form.cleaned_data.get("primary_email", "") if form_valid else ""
        if method_formset:
            method_formset.has_primary_email = bool(primary_email)
        methods_valid = method_formset.is_valid() if method_formset else True
    if request.method == "POST" and form_valid and methods_valid:
        selected = form.cleaned_data.pop("customers")
        form.cleaned_data.pop("include_archived_customers", None)
        primary_email = form.cleaned_data.pop("primary_email", "")
        customer_ids = {item.pk for item in selected}
        if contact and not include_archived:
            customer_ids.update(Customer.objects.filter(pk__in=active_customer_ids(contact),
                                                        status=Customer.Status.INACTIVE).values_list("pk", flat=True))
        if request.POST.get("customers_present") == "1" and not customer_ids:
            form.add_error("customers", "Select at least one customer.")
        else:
            methods = list(method_formset.cleaned_data) if method_formset else None
            if primary_email:
                methods.append({"kind": "email", "value": primary_email, "label": "work", "is_primary": True})
            try:
                if contact:
                    saved = update_contact(actor=request.user, customer_id=customer.pk, contact_id=contact.pk,
                                           customer_ids=list(customer_ids) if customer_ids else None,
                                           methods=methods, **form.cleaned_data)
                else:
                    saved = create_contact(actor=request.user, customer_id=customer.pk,
                                           customer_ids=list(customer_ids) if customer_ids else None,
                                           methods=methods, **form.cleaned_data)
            except ValidationError as error:
                _form_errors(form, error)
            else:
                messages.success(request, "Contact saved.")
                if request.POST.get("return_to") == "customer":
                    return redirect(customer)
                return redirect(saved)
    if contact is not None and request.method == "POST" and request.POST.get("inline_edit") == "1":
        if request.POST.get("return_to") == "customer":
            from apps.customers.views import _render_customer_detail
            return _render_customer_detail(request, customer, selected_contact=contact,
                                           contact_edit_form=form, contact_edit_methods=method_formset, status=400)
        return _render_contact_detail(request, customer, contact, edit_form=form,
                                      edit_methods=method_formset, status=400)
    if contact is None and request.method == "POST" and request.POST.get("return_to") == "customer":
        from apps.customers.views import _render_customer_detail
        return _render_customer_detail(request, customer, new_contact_form=form, new_methods=method_formset, status=400)
    return render(request, "contacts/form.html", {
        "customer": customer, "form": form, "method_formset": method_formset, "new_contact": contact is None,
        "title": "Edit contact" if contact else "Add contact",
        "back_url": _back_url(customer, contact), "submit_label": "Save contact",
        "form_help": "Enter a name and at least one email address or phone number.",
    })


@contact_access("contacts.change_contact")
@require_http_methods(["GET", "POST"])
@never_cache
def contact_status(request, customer_pk, pk, is_active):
    stale = _legacy_redirect(request, customer_pk, pk)
    if stale:
        return stale
    customer, contact = _owner(customer_pk, pk)
    if request.method == "POST":
        try:
            set_contact_active(actor=request.user, customer_id=customer.pk, contact_id=contact.pk, is_active=is_active)
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        else:
            messages.success(request, "Contact restored." if is_active else "Contact archived. All details have been retained.")
        if request.POST.get("return_to") == "customer":
            return redirect(customer)
        return redirect(contact)
    return render(request, "contacts/confirm.html", {
        "customer": customer, "title": "Restore contact" if is_active else "Archive contact",
        "subject": contact.full_name, "back_url": contact.get_absolute_url(),
        "explanation": "All email addresses and phone numbers are retained. This changes only the person's active status.",
    })


@contact_access()
@require_http_methods(["GET", "POST"])
@never_cache
def point_form(request, customer_pk, contact_pk, point_pk=None):
    require_access(request.user, "contacts.change_contactpoint" if point_pk else "contacts.add_contactpoint")
    stale = _legacy_redirect(request, customer_pk, contact_pk)
    if stale:
        return stale
    customer, contact = _owner(customer_pk, contact_pk)
    owner = contact.customer
    point = get_object_or_404(ContactPoint, pk=point_pk, customer=owner, contact=contact) if point_pk else None
    initial = {field: getattr(point, field) for field in ("kind", "label", "value", "is_primary")} if point else {"kind": "email", "label": "other"}
    form = ContactPointForm(request.POST if request.method == "POST" else None, customer=owner, contact=contact, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            save_contact_point(actor=request.user, customer_id=customer.pk, contact_id=contact.pk,
                               point_id=point.pk if point else None, **form.cleaned_data)
        except ValidationError as error:
            _form_errors(form, error)
        else:
            messages.success(request, "Contact detail saved.")
            return redirect(_back_url(customer, contact))
    return render(request, "contacts/form.html", {
        "customer": customer, "form": form, "title": "Edit contact detail" if point else "Add contact detail",
        "back_url": _back_url(customer, contact), "submit_label": "Save detail",
        "form_help": f"For {contact.full_name}.",
    })


@contact_access("contacts.change_contactpoint")
@require_http_methods(["GET", "POST"])
@never_cache
def point_status(request, customer_pk, point_pk, is_active, contact_pk):
    stale = _legacy_redirect(request, customer_pk, contact_pk)
    if stale:
        return stale
    customer, contact = _owner(customer_pk, contact_pk)
    point = get_object_or_404(ContactPoint, pk=point_pk, customer=contact.customer, contact=contact)
    if request.method == "POST":
        try:
            set_point_active(actor=request.user, customer_id=customer.pk, contact_id=contact.pk,
                             point_id=point.pk, is_active=is_active)
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        else:
            messages.success(request, "Contact detail restored." if is_active else "Contact detail archived.")
        return redirect(_back_url(customer, contact))
    return render(request, "contacts/confirm.html", {
        "customer": customer, "title": "Restore contact detail" if is_active else "Archive contact detail",
        "subject": point.value, "back_url": _back_url(customer, contact),
        "explanation": "The value is retained. Its primary designation is cleared when archived; you can choose a primary again after restoring.",
    })


@contact_access("contacts.add_contact")
@require_safe
@never_cache
def legacy_general_create(request, customer_pk):
    get_object_or_404(Customer, pk=customer_pk)
    return redirect("contacts:create", customer_pk=customer_pk)


@contact_access("contacts.change_contactpoint")
@require_safe
@never_cache
def legacy_general_action(request, customer_pk, point_pk, action):
    point = get_object_or_404(ContactPoint, pk=point_pk, customer_id=customer_pk)
    return redirect(reverse(f"contacts:point_{action}", args=[customer_pk, point.contact_id, point.pk]))

@contact_access()
@require_safe
@never_cache
def global_contact_list(request):
    choices = ("status", "contact_type", "include_archived_customers")
    selected = chosen_filters(request, "contacts.global", {"status": "active", "contact_type": "",
                                                         "include_archived_customers": False}, choices)
    filters = GlobalContactFilterForm({**selected, "q": request.GET.get("q", "")})
    valid = filters.is_valid()
    if valid:
        remember_filters(request, "contacts.global", filters, choices)
    people = global_contacts(**filters.cleaned_data) if valid else Contact.objects.none()
    return render(request, "contacts/global_list.html", {
        "filter_form": filters, "page_obj": Paginator(people, 25).get_page(request.GET.get("page")),
        "filter_query": urlencode(filters.cleaned_data) if valid else "",
    }, status=200 if valid else 400)


@contact_access("contacts.add_contact")
@require_http_methods(["GET", "POST"])
@never_cache
def global_contact_create(request):
    include_archived = (request.POST.get("include_archived_customers") == "on" if request.method == "POST"
                        else request.GET.get("include_archived_customers") == "1")
    form = ContactForm(request.POST if request.method == "POST" else None, require_customers=True,
                       include_archived_customers=include_archived)
    if request.method == "GET":
        form.initial["include_archived_customers"] = include_archived
    method_formset = ContactMethodFormSet(request.POST if request.method == "POST" else None, prefix="methods")
    if request.method == "POST":
        form_valid = form.is_valid()
        method_formset.has_primary_email = bool(form.cleaned_data.get("primary_email")) if form_valid else False
        methods_valid = method_formset.is_valid()
    if request.method == "POST" and form_valid and methods_valid:
        selected = form.cleaned_data.pop("customers")
        form.cleaned_data.pop("include_archived_customers", None)
        primary_email = form.cleaned_data.pop("primary_email", "")
        methods = list(method_formset.cleaned_data)
        if primary_email:
            methods.append({"kind": "email", "value": primary_email, "label": "work", "is_primary": True})
        try:
            saved = create_contact(actor=request.user, customer_id=selected[0].pk,
                                   customer_ids=[customer.pk for customer in selected], methods=methods,
                                   **form.cleaned_data)
        except ValidationError as error:
            _form_errors(form, error)
        else:
            messages.success(request, "Contact saved.")
            return redirect(saved)
    return render(request, "contacts/form.html", {
        "form": form, "method_formset": method_formset, "new_contact": True,
        "title": "Add contact", "back_url": reverse("global_contacts:list"),
        "submit_label": "Save contact", "form_help": "Choose at least one customer and enter an email address or phone number.",
    })


@contact_access()
@require_safe
@never_cache
def global_contact_detail(request, pk):
    return redirect(get_object_or_404(Contact, pk=pk).get_absolute_url())


def _global_contact_action(request, pk, action):
    contact = get_object_or_404(Contact, pk=pk)
    customer_id = active_customer_ids(contact)[0]
    return redirect(reverse(f"contacts:{action}", args=[customer_id, pk]))


@contact_access("contacts.change_contact")
@require_safe
@never_cache
def global_contact_edit(request, pk):
    return _global_contact_action(request, pk, "edit")


@contact_access("contacts.change_contact")
@require_safe
@never_cache
def global_contact_archive(request, pk):
    return _global_contact_action(request, pk, "archive")


@contact_access("contacts.change_contact")
@require_safe
@never_cache
def global_contact_restore(request, pk):
    return _global_contact_action(request, pk, "restore")


def _require_contact_import(actor):
    required = ("accounts.edit_portal", "accounts.administer_portal", "contacts.add_contact", "contacts.change_contact",
                "contacts.add_contactpoint", "contacts.change_contactpoint")
    if not actor.has_perms(required):
        raise PermissionDenied


@contact_access()
@require_http_methods(["GET", "POST"])
@never_cache
def global_contact_import(request):
    _require_contact_import(request.user)
    context, status, counts = import_workflow(request, kind="contacts", preview=preview_contacts,
                                              manifest=contact_manifest, confirm=confirm_contacts)
    if counts is not None:
        messages.success(request, f"Contact import complete: {counts['create']} created, {counts['update']} updated, {counts['unchanged']} unchanged.")
        return redirect("global_contacts:list")
    context.update(import_kind="contacts", title="Import contacts from JSON", back_url=reverse("global_contacts:list"),
                   example_url="global_contacts:import_example", schema_url="global_contacts:import_schema",
                   guide_url="global_contacts:import_guide")
    return render(request, "contacts/import.html", context, status=status)


@contact_access()
@require_safe
@never_cache
def global_contact_import_reference(request, asset):
    _require_contact_import(request.user)
    return import_reference("contacts", asset)
