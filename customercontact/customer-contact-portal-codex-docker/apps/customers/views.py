from urllib.parse import urlencode
from uuid import UUID

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.db.models import Q
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from apps.accounts.permissions import permission_required
from apps.contacts.permissions import READ_PERMISSIONS
from apps.contacts.selectors import associated_contacts, customer_overview_contacts
from apps.contacts.forms import ContactForm, ContactMethodFormSet, initial_contact_methods
from apps.contacts.models import Contact
from apps.core.filter_preferences import chosen_filters, remember_filters
from apps.core.json_import import import_reference, import_workflow
from apps.services.permissions import READ_PERMISSIONS as SERVICE_READ_PERMISSIONS
from apps.services.selectors import active_service_count, overview_services
from apps.services.forms import AssignmentForm
from apps.services.models import CustomerService

from .forms import CustomerFilterForm, CustomerForm, CustomerOverviewFilterForm
from .models import Customer
from .services import archive_customer, create_customer, update_customer
from .imports import confirm_customers, manifest as customer_manifest, preview_customers


@permission_required("accounts.access_portal")
@permission_required("customers.view_customer")
@require_safe
@never_cache
def customer_list(request):
    choices = ("status", "sort")
    selected = chosen_filters(request, "customers.directory", {"status": "active", "sort": "name"}, choices)
    filters = CustomerFilterForm({**selected, "q": request.GET.get("q", "")})
    customers = Customer.objects.none()
    filter_query = ""
    valid = filters.is_valid()
    if valid:
        remember_filters(request, "customers.directory", filters, choices)
        query = filters.cleaned_data["q"]
        status = filters.cleaned_data["status"]
        sort = filters.cleaned_data["sort"] or "name"
        customers = Customer.objects.all()
        if query:
            customers = customers.filter(Q(name__icontains=query) | Q(reference_code__icontains=query))
        if status:
            customers = customers.filter(status=status)
        ordering = ["-updated_at", "id"] if sort == "updated" else [Lower("name"), "id"]
        customers = customers.order_by(*ordering)
        filter_query = urlencode({"q": query, "status": status, "sort": sort})
    page = Paginator(customers, 25).get_page(request.GET.get("page"))
    return render(request, "customers/list.html", {
        "filter_form": filters, "page_obj": page, "filter_query": filter_query,
    }, status=200 if valid else 400)


@permission_required("accounts.access_portal")
@permission_required("customers.view_customer")
@require_safe
@never_cache
def customer_detail(request, pk):
    return _render_customer_detail(request, get_object_or_404(Customer, pk=pk))


def _render_customer_detail(request, customer, *, edit_form=None, new_contact_form=None,
                            new_methods=None, selected_contact=None, contact_edit_form=None, contact_edit_methods=None,
                            new_assignment_form=None, assignment_edit_override=None,
                            status=200):
    contacts_enabled = request.user.has_perms(READ_PERMISSIONS)
    services_enabled = request.user.has_perms(SERVICE_READ_PERMISSIONS)
    key = f"customers.overview.{customer.pk}"
    choices = ("services", "contacts")
    selected = chosen_filters(request, key, {"services": "current", "contacts": "current"}, choices)
    overview_filters = CustomerOverviewFilterForm(selected)
    valid = overview_filters.is_valid()
    if valid:
        remember_filters(request, key, overview_filters, choices)
    can_edit_customer = request.user.has_perms(("accounts.edit_portal", "customers.change_customer"))
    can_add_contact = contacts_enabled and request.user.has_perms(("accounts.edit_portal", "contacts.add_contact"))
    can_manage_contacts = contacts_enabled and request.user.has_perms(("accounts.edit_portal", "contacts.change_contact"))
    if can_manage_contacts and selected_contact is None and request.GET.get("edit_contact"):
        try:
            contact_id = UUID(request.GET["edit_contact"])
        except ValueError as error:
            raise Http404 from error
        selected_contact = get_object_or_404(associated_contacts(customer), pk=contact_id)
    if selected_contact is not None and can_manage_contacts:
        contact_edit_form = contact_edit_form or ContactForm(
            instance=selected_contact, customer=customer,
            include_archived_customers=customer.status == Customer.Status.INACTIVE)
        contact_edit_methods = contact_edit_methods or ContactMethodFormSet(
            initial=initial_contact_methods(selected_contact), prefix="methods")
    can_add_assignment = services_enabled and request.user.has_perms(("accounts.edit_portal", "services.add_customerservice"))
    can_edit_assignment = services_enabled and request.user.has_perms(("accounts.edit_portal", "services.change_customerservice"))
    assignments = CustomerService.objects.filter(customer=customer).select_related("service") if can_edit_assignment else []
    if can_edit_assignment and valid and overview_filters.cleaned_data["services"] != "all":
        assignments = assignments.filter(status=CustomerService.Status.ACTIVE, service__is_active=True)
    return render(request, "customers/detail.html", {
        "customer": customer, "contacts_enabled": contacts_enabled,
        "overview_contacts": customer_overview_contacts(customer, include_archived=overview_filters.cleaned_data["contacts"] == "all")
                             if contacts_enabled and valid else [],
        "services_enabled": services_enabled,
        "active_service_count": active_service_count(customer) if services_enabled else None,
        "overview_services": overview_services(customer, include_history=overview_filters.cleaned_data["services"] == "all")
                             if services_enabled and valid else [],
        "overview_filter_form": overview_filters,
        "customer_form": (edit_form or CustomerForm(instance=customer)) if can_edit_customer else None,
        "contact_create_form": (new_contact_form or ContactForm(instance=Contact(customer=customer), customer=customer,
                                            include_archived_customers=customer.status == Customer.Status.INACTIVE)) if can_add_contact else None,
        "contact_create_methods": (new_methods or ContactMethodFormSet(prefix="methods")) if can_add_contact else None,
        "can_manage_contacts": can_manage_contacts,
        "selected_contact": selected_contact if can_manage_contacts else None,
        "contact_edit_form": contact_edit_form if can_manage_contacts else None,
        "contact_edit_methods": contact_edit_methods if can_manage_contacts else None,
        "assignment_create_form": (new_assignment_form or AssignmentForm(instance=CustomerService(customer=customer))) if can_add_assignment else None,
        "assignment_edit_rows": [(assignment, assignment_edit_override[1] if assignment_edit_override and assignment.pk == assignment_edit_override[0]
                                  else AssignmentForm(instance=assignment)) for assignment in assignments],
    }, status=status if valid else 400)


def _customer_form(request, customer=None):
    was_active = customer is not None and customer.status == Customer.Status.ACTIVE
    form = CustomerForm(request.POST if request.method == "POST" else None, instance=customer)
    if request.method == "POST" and form.is_valid():
        if was_active and form.cleaned_data["status"] == Customer.Status.INACTIVE and request.POST.get("confirm_archive") != "yes":
            if request.POST.get("inline_edit") == "1":
                form.add_error("status", "Confirm archive before saving this status change.")
                return _render_customer_detail(request, customer, edit_form=form, status=400)
            return render(request, "customers/confirm_edit_archive.html", {"customer": customer, "form": form})
        try:
            if customer is None:
                saved = create_customer(actor=request.user, **form.cleaned_data)
            else:
                saved = update_customer(actor=request.user, customer_id=customer.pk, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Customer created." if customer is None else "Customer updated.")
            return redirect(saved)
    if customer is not None and request.method == "POST" and request.POST.get("inline_edit") == "1":
        return _render_customer_detail(request, customer, edit_form=form, status=400)
    return render(request, "customers/form.html", {"form": form, "customer": customer})


@permission_required("accounts.access_portal")
@permission_required("accounts.edit_portal")
@permission_required("customers.view_customer")
@permission_required("customers.add_customer")
@require_http_methods(["GET", "POST"])
@never_cache
def customer_create(request):
    return _customer_form(request)


@permission_required("accounts.access_portal")
@permission_required("accounts.edit_portal")
@permission_required("customers.view_customer")
@permission_required("customers.change_customer")
@require_http_methods(["GET", "POST"])
@never_cache
def customer_edit(request, pk):
    return _customer_form(request, get_object_or_404(Customer, pk=pk))


@permission_required("accounts.access_portal")
@permission_required("accounts.edit_portal")
@permission_required("customers.view_customer")
@permission_required("customers.change_customer")
@require_http_methods(["GET", "POST"])
@never_cache
def customer_archive(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == "POST":
        archive_customer(actor=request.user, customer_id=customer.pk)
        messages.success(request, "Customer archived. The record has been retained.")
        return redirect(customer)
    return render(request, "customers/archive.html", {"customer": customer})


@permission_required("accounts.access_portal")
@permission_required("accounts.edit_portal")
@permission_required("accounts.administer_portal")
@permission_required("customers.view_customer")
@permission_required("customers.add_customer")
@permission_required("customers.change_customer")
@require_http_methods(["GET", "POST"])
@never_cache
def customer_import(request):
    context, status, counts = import_workflow(request, kind="customers", preview=preview_customers,
                                              manifest=customer_manifest, confirm=confirm_customers)
    if counts is not None:
        messages.success(request, f"Customer import complete: {counts['create']} created, {counts['update']} updated, {counts['unchanged']} unchanged.")
        return redirect("customers:list")
    context.update(import_kind="customers", title="Import customers from JSON", back_url=reverse("customers:list"),
                   example_url="customers:import_example", schema_url="customers:import_schema",
                   guide_url="customers:import_guide")
    return render(request, "customers/import.html", context, status=status)


@permission_required("accounts.access_portal")
@permission_required("accounts.edit_portal")
@permission_required("accounts.administer_portal")
@permission_required("customers.view_customer")
@permission_required("customers.add_customer")
@permission_required("customers.change_customer")
@require_safe
@never_cache
def customer_import_reference(request, asset):
    return import_reference("customers", asset)
