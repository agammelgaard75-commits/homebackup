from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import BasePermission
from apps.accounts.models import APICredential

from apps.audit.api import AuditHistoryAPI, CustomerActivityAPI
from apps.contacts.api import (ContactCustomerRemoveAPI, ContactCustomersAPI, ContactDetailAPI,
    ContactListAPI, ContactMethodDetailAPI, ContactMethodStatusAPI, ContactMethodsAPI, ContactStatusAPI)
from apps.core.api import DirectoryAPI, HealthAPI
from apps.customers.api import (CustomerContactsAPI, CustomerDetailAPI, CustomerListAPI,
    CustomerServicesAPI, CustomerStatusAPI)
from apps.search.api import GlobalSearchAPI, ServiceContactEmailsAPI, ServiceContactSearchAPI
from apps.services.api import (AssignmentDetailAPI, AssignmentListAPI, AssignmentTerminateAPI,
    ServiceCustomersAPI, ServiceDetailAPI, ServiceListAPI, ServiceStatusAPI)
from apps.cleanup.api import (ArchivedContactsAPI, ArchivedCustomersAPI, CleanupConfirmAPI,
    CleanupOperationAPI, CleanupPreviewAPI)

from .imports import ImportExecuteAPI, ImportPreviewAPI
from .views import CredentialActionAPI, CredentialListAPI, CurrentUserAPI, DashboardSummaryAPI


class DocumentationPermission(BasePermission):
    def has_permission(self, request, view):
        return (request.user.is_authenticated and request.user.is_active
                and request.user.has_perms(("accounts.access_portal", "accounts.administer_portal"))
                and (not isinstance(request.auth, APICredential) or "read" in request.auth.scopes))


class PortalSchemaView(SpectacularAPIView):
    permission_classes = [DocumentationPermission]


class PortalSwaggerView(SpectacularSwaggerView):
    permission_classes = [DocumentationPermission]


app_name = "api"
urlpatterns = [
    path("schema/", PortalSchemaView.as_view(), name="schema"),
    path("docs/", PortalSwaggerView.as_view(url_name="api:schema"), name="docs"),
    path("health/", HealthAPI.as_view(), name="health"),
    path("me/", CurrentUserAPI.as_view(), name="me"),
    path("dashboard/", DashboardSummaryAPI.as_view(), name="dashboard"),
    path("directory/", DirectoryAPI.as_view(), name="directory"),
    path("credentials/", CredentialListAPI.as_view(), name="credentials"),
    path("credentials/<uuid:pk>/revoke/", CredentialActionAPI.as_view(action="revoke"), name="credential_revoke"),
    path("credentials/<uuid:pk>/rotate/", CredentialActionAPI.as_view(action="rotate"), name="credential_rotate"),
    path("customers/", CustomerListAPI.as_view(), name="customers"),
    path("customers/<uuid:pk>/", CustomerDetailAPI.as_view(), name="customer_detail"),
    path("customers/<uuid:pk>/archive/", CustomerStatusAPI.as_view(active=False), name="customer_archive"),
    path("customers/<uuid:pk>/restore/", CustomerStatusAPI.as_view(active=True), name="customer_restore"),
    path("customers/<uuid:pk>/contacts/", CustomerContactsAPI.as_view(), name="customer_contacts"),
    path("customers/<uuid:pk>/services/", CustomerServicesAPI.as_view(), name="customer_services"),
    path("customers/<uuid:pk>/activity/", CustomerActivityAPI.as_view(), name="customer_activity"),
    path("contacts/", ContactListAPI.as_view(), name="contacts"),
    path("contacts/<uuid:pk>/", ContactDetailAPI.as_view(), name="contact_detail"),
    path("contacts/<uuid:pk>/archive/", ContactStatusAPI.as_view(active=False), name="contact_archive"),
    path("contacts/<uuid:pk>/restore/", ContactStatusAPI.as_view(active=True), name="contact_restore"),
    path("contacts/<uuid:pk>/methods/", ContactMethodsAPI.as_view(), name="contact_methods"),
    path("contacts/<uuid:pk>/methods/<uuid:point_pk>/", ContactMethodDetailAPI.as_view(), name="contact_method_detail"),
    path("contacts/<uuid:pk>/methods/<uuid:point_pk>/archive/", ContactMethodStatusAPI.as_view(active=False), name="contact_method_archive"),
    path("contacts/<uuid:pk>/methods/<uuid:point_pk>/restore/", ContactMethodStatusAPI.as_view(active=True), name="contact_method_restore"),
    path("contacts/<uuid:pk>/customers/", ContactCustomersAPI.as_view(), name="contact_customers"),
    path("contacts/<uuid:pk>/customers/<uuid:customer_pk>/remove/", ContactCustomerRemoveAPI.as_view(), name="contact_customer_remove"),
    path("services/", ServiceListAPI.as_view(), name="services"),
    path("services/<uuid:pk>/", ServiceDetailAPI.as_view(), name="service_detail"),
    path("services/<uuid:pk>/archive/", ServiceStatusAPI.as_view(active=False), name="service_archive"),
    path("services/<uuid:pk>/restore/", ServiceStatusAPI.as_view(active=True), name="service_restore"),
    path("services/<uuid:pk>/customers/", ServiceCustomersAPI.as_view(), name="service_customers"),
    path("assignments/", AssignmentListAPI.as_view(), name="assignments"),
    path("assignments/<uuid:pk>/", AssignmentDetailAPI.as_view(), name="assignment_detail"),
    path("assignments/<uuid:pk>/terminate/", AssignmentTerminateAPI.as_view(), name="assignment_terminate"),
    path("search/", GlobalSearchAPI.as_view(), name="search"),
    path("search/by-service/", ServiceContactSearchAPI.as_view(), name="service_search"),
    path("search/by-service/emails/", ServiceContactEmailsAPI.as_view(), name="service_emails"),
    path("imports/customers/preview/", ImportPreviewAPI.as_view(kind="customers"), name="customer_import_preview"),
    path("imports/customers/execute/", ImportExecuteAPI.as_view(kind="customers"), name="customer_import_execute"),
    path("imports/contacts/preview/", ImportPreviewAPI.as_view(kind="contacts"), name="contact_import_preview"),
    path("imports/contacts/execute/", ImportExecuteAPI.as_view(kind="contacts"), name="contact_import_execute"),
    path("audit/", AuditHistoryAPI.as_view(), name="audit"),
    path("cleanup/archived-customers/", ArchivedCustomersAPI.as_view(), name="cleanup_customers"),
    path("cleanup/archived-contacts/", ArchivedContactsAPI.as_view(), name="cleanup_contacts"),
    path("cleanup/preview/", CleanupPreviewAPI.as_view(), name="cleanup_preview"),
    path("cleanup/confirm/", CleanupConfirmAPI.as_view(), name="cleanup_confirm"),
    path("cleanup/operations/<uuid:pk>/", CleanupOperationAPI.as_view(), name="cleanup_operation"),
]
