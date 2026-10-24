from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from apps.customers.models import Customer

from .forms import ContactFilterForm, ContactForm, ContactPointForm, GlobalContactFilterForm
from .models import Contact, ContactPoint
from .permissions import contact_access, require_access
from .selectors import associated_contacts, directory_results, is_associated, active_customer_ids, global_contacts
from .services import create_contact, update_contact, set_contact_active, save_contact_point, set_point_active


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
    filters = ContactFilterForm({"status": "active", **request.GET.dict()})
    people, filter_query = Contact.objects.none(), ""
    valid = filters.is_valid()
    if valid:
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
    linked_customers = Customer.objects.filter(pk__in=active_customer_ids(contact)).order_by("name", "pk")
    return render(request, "contacts/detail.html", {"customer": customer, "contact": contact, "points": contact.points.all(),
                  "linked_customers": linked_customers})


@contact_access()
@require_http_methods(["GET", "POST"])
@never_cache
def contact_form(request, customer_pk, pk=None):
    require_access(request.user, "contacts.change_contact" if pk else "contacts.add_contact")
    stale = _legacy_redirect(request, customer_pk, pk)
    if stale:
        return stale
    customer, contact = _owner(customer_pk, pk)
    form = ContactForm(request.POST if request.method == "POST" else None, instance=contact or Contact(customer=customer), customer=customer)
    if request.method == "POST" and form.is_valid():
        selected = form.cleaned_data.pop("customers")
        if request.POST.get("customers_present") == "1" and not selected:
            form.add_error("customers", "Select at least one customer.")
        else:
            customer_ids = [item.pk for item in selected] if selected else None
            try:
                if contact:
                    saved = update_contact(actor=request.user, customer_id=customer.pk, contact_id=contact.pk,
                                           customer_ids=customer_ids, **form.cleaned_data)
                else:
                    saved = create_contact(actor=request.user, customer_id=customer.pk, customer_ids=customer_ids, **form.cleaned_data)
            except ValidationError as error:
                _form_errors(form, error)
            else:
                messages.success(request, "Contact saved.")
                return redirect(saved)
    return render(request, "contacts/form.html", {
        "customer": customer, "form": form, "title": "Edit contact" if contact else "Add contact",
        "back_url": _back_url(customer, contact), "submit_label": "Save contact",
        "form_help": "Only a name is required. Add email addresses and phone numbers from the contact details page.",
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
        set_contact_active(actor=request.user, customer_id=customer.pk, contact_id=contact.pk, is_active=is_active)
        messages.success(request, "Contact restored." if is_active else "Contact archived. All details have been retained.")
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
        set_point_active(actor=request.user, customer_id=customer.pk, contact_id=contact.pk,
                         point_id=point.pk, is_active=is_active)
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
    filters = GlobalContactFilterForm({"status": "active", **request.GET.dict()})
    valid = filters.is_valid()
    people = global_contacts(**filters.cleaned_data) if valid else Contact.objects.none()
    return render(request, "contacts/global_list.html", {
        "filter_form": filters, "page_obj": Paginator(people, 25).get_page(request.GET.get("page")),
        "filter_query": urlencode(filters.cleaned_data) if valid else "",
    }, status=200 if valid else 400)


@contact_access("contacts.add_contact")
@require_http_methods(["GET", "POST"])
@never_cache
def global_contact_create(request):
    form = ContactForm(request.POST if request.method == "POST" else None, require_customers=True)
    if request.method == "POST" and form.is_valid():
        selected = form.cleaned_data.pop("customers")
        try:
            saved = create_contact(actor=request.user, customer_id=selected[0].pk,
                                   customer_ids=[customer.pk for customer in selected], **form.cleaned_data)
        except ValidationError as error:
            _form_errors(form, error)
        else:
            messages.success(request, "Contact saved.")
            return redirect(saved)
    return render(request, "contacts/form.html", {
        "form": form, "title": "Add contact", "back_url": reverse("global_contacts:list"),
        "submit_label": "Save contact", "form_help": "Choose at least one customer. Add email and phone details after saving.",
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
