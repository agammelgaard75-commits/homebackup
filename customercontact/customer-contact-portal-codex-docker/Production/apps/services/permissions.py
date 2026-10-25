from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

CATALOG_READ_PERMISSIONS = ("accounts.access_portal", "services.view_service")
READ_PERMISSIONS = (*CATALOG_READ_PERMISSIONS, "customers.view_customer", "services.view_customerservice")


def require_access(actor, write_permission=None, *, catalog=False):
    permissions = CATALOG_READ_PERMISSIONS if catalog else READ_PERMISSIONS
    if write_permission:
        permissions += ("accounts.edit_portal", write_permission)
        if catalog:
            permissions += ("accounts.administer_portal",)
    if not actor.is_active or not actor.has_perms(permissions):
        raise PermissionDenied


def service_access(write_permission=None, *, catalog=False):
    def decorate(view):
        @login_required
        @wraps(view)
        def checked(request, *args, **kwargs):
            require_access(request.user, write_permission, catalog=catalog)
            return view(request, *args, **kwargs)
        return checked
    return decorate
