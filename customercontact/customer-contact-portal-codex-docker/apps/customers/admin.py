"""Read-only admin inspection; mutations use the customer UI/service layer."""
from django.contrib import admin
from django.utils.html import format_html

from apps.accounts.admin import portal_admin

from .models import Customer


@admin.register(Customer, site=portal_admin)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "reference_code", "status", "updated_at", "open_customer")
    list_filter = ("status",)
    search_fields = ("name", "reference_code")
    readonly_fields = ("id", "name", "reference_code", "status", "address", "notes", "created_at", "updated_at", "open_customer")
    actions = None

    @admin.display(description="Customer page")
    def open_customer(self, obj):
        return format_html('<a href="{}">Open customer</a>', obj.get_absolute_url())

    def has_view_permission(self, request, obj=None):
        return request.user.has_perms(("accounts.access_portal", "customers.view_customer"))

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
