"""Public accounts write operations. No role initialization in signals."""
import hashlib

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction

from .models import OIDCIdentity, User

ROLE_PERMISSIONS = {
    "Viewer": {
        "audit.view_customer_activity",
        "accounts.access_portal", "customers.view_customer", "contacts.view_contact", "contacts.view_contactpoint",
        "services.view_service", "services.view_customerservice",
    },
    "Editor": {
        "audit.view_customer_activity",
        "services.view_service", "services.view_customerservice", "services.add_customerservice", "services.change_customerservice",
        "accounts.access_portal", "accounts.edit_portal",
        "customers.view_customer", "customers.add_customer", "customers.change_customer",
        "contacts.view_contact", "contacts.add_contact", "contacts.change_contact",
        "contacts.view_contactpoint", "contacts.add_contactpoint", "contacts.change_contactpoint",
    },
    "Administrator": {
        "cleanup.view_cleanupoperation", "cleanup.execute_cleanup",
        "audit.view_customer_activity", "audit.view_auditevent",
        "services.view_service", "services.add_service", "services.change_service",
        "services.view_customerservice", "services.add_customerservice", "services.change_customerservice",
        "accounts.access_portal", "accounts.edit_portal", "accounts.administer_portal",
        "accounts.add_user", "accounts.change_user", "accounts.view_user",
        "customers.view_customer", "customers.add_customer", "customers.change_customer",
        "contacts.view_contact", "contacts.add_contact", "contacts.change_contact",
        "contacts.view_contactpoint", "contacts.add_contactpoint", "contacts.change_contactpoint",
    },
}

OIDC_ROLE_MAP = {"portal-viewer": "Viewer", "portal-editor": "Editor", "portal-admin": "Administrator"}
OIDC_ROLE_ORDER = ("portal-admin", "portal-editor", "portal-viewer")


def role_from_oidc_claims(claims):
    resources = claims.get("resource_access")
    client = resources.get(settings.OIDC_CLIENT_ID) if isinstance(resources, dict) else None
    roles = client.get("roles", []) if isinstance(client, dict) else []
    if not isinstance(roles, list):
        return None
    return next((OIDC_ROLE_MAP[name] for name in OIDC_ROLE_ORDER if name in roles), None)


@transaction.atomic
def sync_oidc_user(claims):
    """Own the explicit issuer/subject link and verified portal role changes."""
    role = role_from_oidc_claims(claims)
    if not role or claims.get("iss") != settings.OIDC_ISSUER_URL:
        return None
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        return None
    identity = OIDCIdentity.objects.select_related("user").filter(issuer=settings.OIDC_ISSUER_URL, subject=subject).first()
    if identity:
        user = identity.user
        if not user.is_active or user.is_superuser:
            return None
    else:
        digest = hashlib.sha256(f"{settings.OIDC_ISSUER_URL}\x00{subject}".encode()).hexdigest()
        user = User.objects.create_user(username=f"oidc_{digest}")
        user.set_unusable_password()
        user.is_staff = False
        user.is_superuser = False
        user.save(update_fields=["password", "is_staff", "is_superuser"])
        OIDCIdentity.objects.create(user=user, issuer=settings.OIDC_ISSUER_URL, subject=subject)
    try:
        group = Group.objects.get(name=role)
    except Group.DoesNotExist as error:
        raise ImproperlyConfigured("Portal roles must be initialized before OIDC login.") from error
    user.groups.set([group])
    user.user_permissions.clear()
    if user.is_staff:
        user.is_staff = False
        user.save(update_fields=["is_staff"])
    return user


@transaction.atomic
def setup_roles():
    """Reconcile managed groups after migrate; preserve users and memberships."""
    permissions = {
        f"{permission.content_type.app_label}.{permission.codename}": permission
        for permission in Permission.objects.filter(
            content_type__app_label__in=["accounts", "customers", "contacts", "services", "audit", "cleanup"],
        ).select_related("content_type")
    }
    for name, permission_names in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=name)
        group.permissions.set([permissions[permission_name] for permission_name in permission_names])
