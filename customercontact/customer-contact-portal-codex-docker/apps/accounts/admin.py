"""Limited user administration; only superusers may change raw permissions."""
from django.contrib.admin import AdminSite
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group

from .forms import PortalAdminAuthenticationForm
from .models import User
from .services import ROLE_PERMISSIONS


class PortalAdminSite(AdminSite):
    login_form = PortalAdminAuthenticationForm
    site_header = "Customer Portal administration"
    site_title = "Customer Portal"
    site_url = "/"
    index_template = "admin/portal_index.html"

    def get_urls(self):
        from django.urls import path
        from apps.cleanup.views import cleanup_page

        return [path("data-cleanup/", self.admin_view(cleanup_page), name="data_cleanup"), *super().get_urls()]

    def has_permission(self, request):
        return request.user.is_active and request.user.has_perm("accounts.administer_portal")


class PortalUserAdmin(UserAdmin):
    def get_fieldsets(self, request, obj=None):
        if request.user.is_superuser:
            return super().get_fieldsets(request, obj)
        if obj is None:
            return ((None, {"fields": ("username", "password1", "password2", "groups")}),)
        return (
            (None, {"fields": ("username", "password")}),
            ("Personal information", {"fields": ("first_name", "last_name", "email")}),
            ("Access", {"fields": ("is_active", "groups")}),
        )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset if request.user.is_superuser else queryset.filter(is_superuser=False)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "groups" and not request.user.is_superuser:
            kwargs["queryset"] = Group.objects.filter(name__in=ROLE_PERMISSIONS)
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def has_change_permission(self, request, obj=None):
        if obj and obj.is_superuser and not request.user.is_superuser:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        # Deactivate accounts in the UI to preserve historical attribution.
        return False


class PortalGroupAdmin(GroupAdmin):
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    has_add_permission = has_view_permission
    has_change_permission = has_view_permission
    has_delete_permission = has_view_permission


portal_admin = PortalAdminSite(name="admin")
portal_admin.register(User, PortalUserAdmin)
portal_admin.register(Group, PortalGroupAdmin)
