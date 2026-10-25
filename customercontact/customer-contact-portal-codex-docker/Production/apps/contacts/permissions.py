from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

READ_PERMISSIONS = ("accounts.access_portal", "customers.view_customer", "contacts.view_contact", "contacts.view_contactpoint")


def require_access(actor, write_permission=None):
    permissions = READ_PERMISSIONS
    if write_permission:
        permissions += ("accounts.edit_portal", write_permission)
    if not actor.is_active or not actor.has_perms(permissions):
        raise PermissionDenied


def contact_access(write_permission=None):
    def decorate(view):
        @login_required
        @wraps(view)
        def checked(request, *args, **kwargs):
            require_access(request.user, write_permission)
            return view(request, *args, **kwargs)
        return checked
    return decorate
