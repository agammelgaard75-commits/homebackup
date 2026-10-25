from django.contrib.auth.views import LoginView, LogoutView
from django.conf import settings
from django.urls import path

app_name = "accounts"
urlpatterns = [
    path("login/", LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
]
if settings.AUTH_MODE == "oidc":
    from mozilla_django_oidc.views import OIDCLogoutView
    from .oidc import oidc_logged_out, oidc_login

    urlpatterns = [
        path("login/", oidc_login, name="login"),
        path("logout/", OIDCLogoutView.as_view(), name="logout"),
        path("logged-out/", oidc_logged_out, name="logged_out"),
    ]
