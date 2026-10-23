from django.urls import include, path

from apps.accounts.admin import portal_admin

urlpatterns = [
    path("admin/", portal_admin.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("customers/", include("apps.customers.urls")),
    path("", include("apps.core.urls")),
]
