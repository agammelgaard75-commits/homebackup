"""Permission gates for views and future owning-app service functions.

Future mutations must check edit_portal AND the owning model's permission.
Role permissions are reconciled explicitly by setup_roles after migrations.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def permission_required(permission):
    def decorate(view):
        @login_required
        @wraps(view)
        def checked(request, *args, **kwargs):
            if not request.user.is_active or not request.user.has_perm(permission):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return checked
    return decorate
