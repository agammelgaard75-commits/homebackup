from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from apps.accounts.permissions import permission_required
from apps.contacts.models import Contact
from apps.customers.models import Customer

from .services import confirm_cleanup, preview_cleanup


@permission_required("accounts.access_portal")
@permission_required("accounts.administer_portal")
@permission_required("cleanup.view_cleanupoperation")
@permission_required("cleanup.execute_cleanup")
@require_http_methods(["GET", "POST"])
@never_cache
def cleanup_page(request):
    query = request.GET.get("q", "").strip()[:200]
    contact_type = request.GET.get("contact_type", "")
    if contact_type not in ("", *Contact.Type.values):
        contact_type = ""
    customers = Customer.objects.filter(status=Customer.Status.INACTIVE)
    contacts = Contact.objects.filter(is_active=False)
    if contact_type:
        contacts = contacts.filter(contact_type=contact_type)
    if query:
        customers = customers.filter(Q(name__icontains=query) | Q(reference_code__icontains=query))
        contacts = contacts.filter(Q(full_name__icontains=query) | Q(customer__name__icontains=query)
                                   | Q(customer_links__customer__name__icontains=query)).distinct()
    context = {"q": query, "contact_type": contact_type, "contact_types": Contact.Type.choices,
               "customer_page": Paginator(customers.order_by("name", "id"), 25).get_page(request.GET.get("customer_page")),
               "contact_page": Paginator(contacts.order_by("full_name", "id"), 25).get_page(request.GET.get("contact_page"))}
    if request.method == "POST":
        try:
            if request.POST.get("action") == "preview":
                context["preview"] = preview_cleanup(actor=request.user,
                    customer_ids=request.POST.getlist("customer_ids"), contact_ids=request.POST.getlist("contact_ids"))
            elif request.POST.get("action") == "confirm":
                operation = confirm_cleanup(actor=request.user,
                    token=request.POST.get("confirmation_token", ""), confirm=request.POST.get("confirm") == "on")
                messages.success(request, f"Cleanup completed. Operation ID: {operation.pk}")
                return redirect("admin:data_cleanup")
            else:
                raise ValidationError("Choose records to preview first.")
        except (ValidationError, ProtectedError) as error:
            context["error"] = "; ".join(error.messages) if isinstance(error, ValidationError) else "A protected dependency blocked deletion. Preview again."
            return render(request, "cleanup/page.html", context, status=409 if isinstance(error, ProtectedError) else 400)
    return render(request, "cleanup/page.html", context)
