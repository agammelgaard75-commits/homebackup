from django.urls import include, path
from django.conf import settings

from apps.accounts.admin import portal_admin

urlpatterns = [
    path("api/v1/", include("apps.api.urls")),
    path("admin/", portal_admin.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("customers/", include("apps.customers.urls")),
    path("customers/<uuid:customer_pk>/contacts/", include("apps.contacts.urls")),
    path("contacts/", include("apps.contacts.global_urls")),
    path("customers/<uuid:customer_pk>/services/", include("apps.services.customer_urls")),
    path("services/", include("apps.services.urls")),
    path("search/", include("apps.search.urls")),
    path("audit/", include("apps.audit.urls")),
    path("customers/<uuid:customer_pk>/activity/", include("apps.audit.customer_urls")),
    path("", include("apps.core.urls")),
]
if settings.AUTH_MODE == "oidc":
    urlpatterns.insert(0, path("oidc/", include("mozilla_django_oidc.urls")))
