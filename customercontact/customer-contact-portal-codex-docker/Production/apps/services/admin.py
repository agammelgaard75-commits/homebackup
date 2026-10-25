"""Read-only inspection. All mutations use the owning app's validated UI/API."""
from django.contrib import admin
from django.utils.html import format_html

from apps.accounts.admin import portal_admin

from .models import CustomerService, Service
from .permissions import CATALOG_READ_PERMISSIONS, READ_PERMISSIONS


class ReadOnlyServiceAdmin(admin.ModelAdmin):
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Portal page")
    def open_record(self, obj):
        return format_html('<a href="{}">Open record</a>', obj.get_absolute_url())


@admin.register(Service, site=portal_admin)
class ServiceAdmin(ReadOnlyServiceAdmin):
    list_display = ("name", "category", "is_active", "open_record")
    list_filter = ("is_active",)
    search_fields = ("name", "category")
    readonly_fields = ("id", "name", "description", "category", "is_active", "created_at", "updated_at", "open_record")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perms(CATALOG_READ_PERMISSIONS)


@admin.register(CustomerService, site=portal_admin)
class CustomerServiceAdmin(ReadOnlyServiceAdmin):
    list_display = ("id", "customer", "service", "status", "open_record")
    list_select_related = ("customer", "service")
    list_filter = ("status",)
    readonly_fields = ("id", "customer", "service", "status", "start_date", "end_date", "notes", "created_at", "updated_at", "open_record")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perms(READ_PERMISSIONS)
