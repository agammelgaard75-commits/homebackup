from django.core.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError

from apps.accounts.models import APICredential


def require_api(request, *permissions, scope="read"):
    actor = request.user
    if not actor.is_authenticated or not actor.is_active or not actor.has_perms(("accounts.access_portal", *permissions)):
        raise PermissionDenied
    if isinstance(request.auth, APICredential) and scope not in request.auth.scopes:
        raise PermissionDenied


def boolean_param(request, name, default=False):
    value = request.query_params.get(name)
    if value is None:
        return default
    if value in ("1", "true", "on"):
        return True
    if value in ("0", "false", "off"):
        return False
    raise ValidationError({name: ["Use true or false."]})


def choice_param(request, name, allowed, default):
    value = request.query_params.get(name, default)
    if value not in allowed:
        raise ValidationError({name: ["Unsupported choice."]})
    return value


def limited_query(request, name="q", limit=200):
    value = request.query_params.get(name, "").strip()
    if len(value) > limit:
        raise ValidationError({name: [f"Use at most {limit} characters."]})
    return value
