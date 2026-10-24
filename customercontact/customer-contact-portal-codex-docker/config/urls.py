from django.urls import include, path

from apps.accounts.admin import portal_admin

urlpatterns = [
    path("admin/", portal_admin.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("customers/", include("apps.customers.urls")),
    path("customers/<uuid:customer_pk>/contacts/", include("apps.contacts.urls")),
    path("customers/<uuid:customer_pk>/services/", include("apps.services.customer_urls")),
    path("services/", include("apps.services.urls")),
    path("search/", include("apps.search.urls")),
    path("audit/", include("apps.audit.urls")),
    path("customers/<uuid:customer_pk>/activity/", include("apps.audit.customer_urls")),
    path("", include("apps.core.urls")),
]
