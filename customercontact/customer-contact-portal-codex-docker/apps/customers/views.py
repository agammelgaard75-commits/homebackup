from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from apps.accounts.permissions import permission_required
from apps.contacts.permissions import READ_PERMISSIONS
from apps.contacts.selectors import general_contact_points

from .forms import CustomerFilterForm, CustomerForm
from .models import Customer
from .services import archive_customer, create_customer, update_customer


@permission_required("accounts.access_portal")
@permission_required("customers.view_customer")
@require_safe
@never_cache
def customer_list(request):
    filters = CustomerFilterForm({"status": "active", "sort": "name", **request.GET.dict()})
    customers = Customer.objects.none()
    filter_query = ""
    valid = filters.is_valid()
    if valid:
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
    customer = get_object_or_404(Customer, pk=pk)
    contacts_enabled = request.user.has_perms(READ_PERMISSIONS)
    return render(request, "customers/detail.html", {
        "customer": customer, "contacts_enabled": contacts_enabled,
        "general_points": general_contact_points(customer) if contacts_enabled else [],
    })


def _customer_form(request, customer=None):
    form = CustomerForm(request.POST if request.method == "POST" else None, instance=customer)
    if request.method == "POST" and form.is_valid():
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
