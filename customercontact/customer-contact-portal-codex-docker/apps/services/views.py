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

from .forms import AssignmentFilterForm, AssignmentForm, CatalogFilterForm, ServiceForm
from .models import CustomerService, Service
from .permissions import READ_PERMISSIONS, service_access
from .selectors import customer_assignments
from .services import create_assignment, create_service, set_service_active, terminate_assignment, update_assignment, update_service


def _page(request, records):
    return Paginator(records, 25).get_page(request.GET.get("page"))


def _assignment(customer_pk, pk):
    return get_object_or_404(CustomerService.objects.select_related("customer", "service"), pk=pk, customer_id=customer_pk)


@service_access(catalog=True)
@require_safe
@never_cache
def catalog_list(request):
    filters = CatalogFilterForm(request.GET)
    records = Service.objects.none()
    valid = filters.is_valid()
    if valid:
        data = filters.cleaned_data
        records = Service.objects.all()
        if data["q"]:
            records = records.filter(Q(name__icontains=data["q"]) | Q(description__icontains=data["q"]) | Q(category__icontains=data["q"]))
        if data["status"]:
            records = records.filter(is_active=data["status"] == "active")
        if data["category"]:
            records = records.filter(category__iexact=data["category"])
        records = records.order_by(Lower("name"), "id")
    return render(request, "services/catalog_list.html", {
        "filter_form": filters, "page_obj": _page(request, records),
        "filter_query": urlencode(filters.cleaned_data) if valid else "",
    }, status=200 if valid else 400)


@service_access(catalog=True)
@require_safe
@never_cache
def catalog_detail(request, pk):
    service = get_object_or_404(Service, pk=pk)
    can_view_assignments = request.user.has_perms(READ_PERMISSIONS)
    records = service.assignments.select_related("customer", "service") if can_view_assignments else CustomerService.objects.none()
    return render(request, "services/catalog_detail.html", {
        "service": service, "can_view_assignments": can_view_assignments, "page_obj": _page(request, records),
    })


def _catalog_form(request, service=None):
    form = ServiceForm(request.POST if request.method == "POST" else None, instance=service)
    if request.method == "POST" and form.is_valid():
        try:
            if service is None:
                saved = create_service(actor=request.user, **form.cleaned_data)
            else:
                saved = update_service(actor=request.user, service_id=service.pk, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Catalog service saved.")
            return redirect(saved)
    return render(request, "services/form.html", {
        "form": form, "title": "Edit service" if service else "Create service",
        "back_url": service.get_absolute_url() if service else reverse("services:list"),
    })


@service_access("services.add_service", catalog=True)
@require_http_methods(["GET", "POST"])
@never_cache
def catalog_create(request):
    return _catalog_form(request)


@service_access("services.change_service", catalog=True)
@require_http_methods(["GET", "POST"])
@never_cache
def catalog_edit(request, pk):
    return _catalog_form(request, get_object_or_404(Service, pk=pk))


@service_access("services.change_service", catalog=True)
@require_http_methods(["GET", "POST"])
@never_cache
def catalog_status(request, pk, active):
    service = get_object_or_404(Service, pk=pk)
    if request.method == "POST":
        set_service_active(actor=request.user, service_id=pk, is_active=active)
        messages.success(request, "Catalog service restored." if active else "Catalog service archived. Existing assignments are retained.")
        return redirect(service)
    return render(request, "services/confirm.html", {
        "title": "Restore service" if active else "Archive service", "subject": service.name,
        "explanation": "Existing assignments and their statuses remain unchanged. Only active catalog services can be newly assigned.",
        "back_url": service.get_absolute_url(),
    })


@service_access()
@require_safe
@never_cache
def assignment_list(request, customer_pk):
    customer = get_object_or_404(Customer, pk=customer_pk)
    filters = AssignmentFilterForm(request.GET)
    valid = filters.is_valid()
    records = customer_assignments(customer) if valid else CustomerService.objects.none()
    if valid and filters.cleaned_data["status"]:
        records = records.filter(status=filters.cleaned_data["status"])
    return render(request, "services/assignment_list.html", {
        "customer": customer, "filter_form": filters, "page_obj": _page(request, records),
        "filter_query": urlencode(filters.cleaned_data) if valid else "",
    }, status=200 if valid else 400)


@service_access()
@require_safe
@never_cache
def assignment_detail(request, customer_pk, pk):
    assignment = _assignment(customer_pk, pk)
    return render(request, "services/assignment_detail.html", {"assignment": assignment, "customer": assignment.customer})


def _assignment_form(request, customer, assignment=None):
    form = AssignmentForm(request.POST if request.method == "POST" else None,
                          instance=assignment or CustomerService(customer=customer))
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data.copy()
        service = data.pop("service")
        try:
            if assignment is None:
                saved = create_assignment(actor=request.user, customer_id=customer.pk, service_id=service.pk, **data)
            else:
                saved = update_assignment(actor=request.user, customer_id=customer.pk, assignment_id=assignment.pk, **data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Service assignment saved.")
            return redirect(saved)
    return render(request, "services/form.html", {
        "form": form, "customer": customer, "title": "Edit assignment" if assignment else "Assign service",
        "back_url": assignment.get_absolute_url() if assignment else reverse("customer_services:list", args=[customer.pk]),
    })


@service_access("services.add_customerservice")
@require_http_methods(["GET", "POST"])
@never_cache
def assignment_create(request, customer_pk):
    return _assignment_form(request, get_object_or_404(Customer, pk=customer_pk))


@service_access("services.change_customerservice")
@require_http_methods(["GET", "POST"])
@never_cache
def assignment_edit(request, customer_pk, pk):
    assignment = _assignment(customer_pk, pk)
    return _assignment_form(request, assignment.customer, assignment)


@service_access("services.change_customerservice")
@require_http_methods(["GET", "POST"])
@never_cache
def assignment_terminate(request, customer_pk, pk):
    assignment = _assignment(customer_pk, pk)
    if request.method == "POST":
        terminate_assignment(actor=request.user, customer_id=customer_pk, assignment_id=pk)
        messages.success(request, "Assignment terminated. Its details and history are retained.")
        return redirect(assignment)
    return render(request, "services/confirm.html", {
        "title": "Terminate assignment", "subject": assignment.service.name, "customer": assignment.customer,
        "explanation": "The assignment will be marked Terminated. Dates, notes and relationships will be retained. You can edit its status later.",
        "back_url": assignment.get_absolute_url(),
    })
