"""Read-only inspection; use contacts services through the customer UI to write."""
from django.contrib import admin

from apps.accounts.admin import portal_admin

from .models import Contact, ContactPoint
from .permissions import READ_PERMISSIONS


class ReadOnlyContactAdmin(admin.ModelAdmin):
    actions = None

    def has_view_permission(self, request, obj=None):
        return request.user.has_perms(READ_PERMISSIONS)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]


@admin.register(Contact, site=portal_admin)
class ContactAdmin(ReadOnlyContactAdmin):
    list_display = ("full_name", "customer", "contact_type", "is_active")
    list_filter = ("is_active", "contact_type")
    search_fields = ("full_name",)
    list_select_related = ("customer",)


@admin.register(ContactPoint, site=portal_admin)
class ContactPointAdmin(ReadOnlyContactAdmin):
    list_display = ("id", "customer", "contact", "kind", "label", "is_primary", "is_active")
    list_filter = ("kind", "is_active")
    list_select_related = ("customer", "contact")
