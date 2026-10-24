"""Public accounts write operations. No role initialization in signals."""
from django.contrib.auth.models import Group, Permission
from django.db import transaction

ROLE_PERMISSIONS = {
    "Viewer": {
        "accounts.access_portal", "customers.view_customer", "contacts.view_contact", "contacts.view_contactpoint",
        "services.view_service", "services.view_customerservice",
    },
    "Editor": {
        "services.view_service", "services.view_customerservice", "services.add_customerservice", "services.change_customerservice",
        "accounts.access_portal", "accounts.edit_portal",
        "customers.view_customer", "customers.add_customer", "customers.change_customer",
        "contacts.view_contact", "contacts.add_contact", "contacts.change_contact",
        "contacts.view_contactpoint", "contacts.add_contactpoint", "contacts.change_contactpoint",
    },
    "Administrator": {
        "services.view_service", "services.add_service", "services.change_service",
        "services.view_customerservice", "services.add_customerservice", "services.change_customerservice",
        "accounts.access_portal", "accounts.edit_portal", "accounts.administer_portal",
        "accounts.add_user", "accounts.change_user", "accounts.view_user",
        "customers.view_customer", "customers.add_customer", "customers.change_customer",
        "contacts.view_contact", "contacts.add_contact", "contacts.change_contact",
        "contacts.view_contactpoint", "contacts.add_contactpoint", "contacts.change_contactpoint",
    },
}


@transaction.atomic
def setup_roles():
    """Reconcile managed groups after migrate; preserve users and memberships."""
    permissions = {
        f"{permission.content_type.app_label}.{permission.codename}": permission
        for permission in Permission.objects.filter(
            content_type__app_label__in=["accounts", "customers", "contacts", "services"],
        ).select_related("content_type")
    }
    for name, permission_names in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=name)
        group.permissions.set([permissions[permission_name] for permission_name in permission_names])
