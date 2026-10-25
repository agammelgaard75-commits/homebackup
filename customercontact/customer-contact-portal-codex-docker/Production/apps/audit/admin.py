from django.contrib import admin
from apps.accounts.admin import portal_admin
from .models import AuditEvent
from .selectors import visible_events


@admin.register(AuditEvent, site=portal_admin)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "object_type", "object_id")
    readonly_fields = ("id", "created_at", "actor", "action", "object_type", "object_id", "customer", "description", "changed_fields")
    actions = None

    def get_queryset(self, request):
        return visible_events(request.user)

    def has_view_permission(self, request, obj=None):
        return request.user.has_perms(("accounts.access_portal", "accounts.administer_portal", "audit.view_auditevent"))

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
