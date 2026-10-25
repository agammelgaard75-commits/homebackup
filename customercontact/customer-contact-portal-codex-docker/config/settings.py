"""Environment-driven settings shared by Docker development and production."""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"


def required(name):
    value = os.environ.get(name, "").strip()
    if not value or value == "REPLACE_ON_INSTALL":
        raise ImproperlyConfigured(f"Set {name} to a non-placeholder value.")
    return value


def csv_setting(name):
    return [value.strip() for value in required(name).split(",") if value.strip()]


SECRET_KEY = required("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = csv_setting("DJANGO_ALLOWED_HOSTS")
if "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must contain explicit hosts.")
CSRF_TRUSTED_ORIGINS = [
    value.strip() for value in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if value.strip()
]
if not DEBUG and any(not origin.startswith("https://") for origin in CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured("Trusted origins must use HTTPS when DEBUG=0.")
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework", "drf_spectacular", "drf_spectacular_sidecar", "mozilla_django_oidc",
    "apps.core", "apps.accounts", "apps.customers", "apps.contacts",
    "apps.services", "apps.search", "apps.audit", "apps.cleanup", "apps.api",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.oidc.OIDCSessionGateMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "apps/core/templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.environ.get("POSTGRES_DB", "customer_portal"),
    "USER": os.environ.get("POSTGRES_USER", "customer_portal"),
    "PASSWORD": required("POSTGRES_PASSWORD"),
    "HOST": os.environ.get("DATABASE_HOST", "db"),
    "PORT": os.environ.get("DATABASE_PORT", "5432"),
    "CONN_MAX_AGE": 60,
    "CONN_HEALTH_CHECKS": True,
    "OPTIONS": {"connect_timeout": 3},
}}
AUTH_USER_MODEL = "accounts.User"
AUTH_MODE = os.environ.get("AUTH_MODE", "local").strip().lower()
if AUTH_MODE not in {"local", "oidc"}:
    raise ImproperlyConfigured("AUTH_MODE must be local or oidc.")
if AUTH_MODE == "oidc":
    OIDC_ISSUER_URL = required("OIDC_ISSUER_URL").rstrip("/")
    if not OIDC_ISSUER_URL.startswith("https://"):
        raise ImproperlyConfigured("OIDC_ISSUER_URL must use HTTPS.")
    OIDC_CLIENT_ID = required("OIDC_CLIENT_ID")
    OIDC_CLIENT_SECRET = required("OIDC_CLIENT_SECRET")
    OIDC_API_AUDIENCE = os.environ.get("OIDC_API_AUDIENCE", OIDC_CLIENT_ID).strip()
    OIDC_REDIRECT_URI = os.environ.get("OIDC_REDIRECT_URI", "").strip()
    OIDC_RP_CLIENT_ID = OIDC_CLIENT_ID
    OIDC_RP_CLIENT_SECRET = OIDC_CLIENT_SECRET
    OIDC_RP_SIGN_ALGO = "RS256"
    OIDC_RP_SCOPES = "openid"
    OIDC_USE_PKCE = True
    OIDC_USE_NONCE = True
    OIDC_VERIFY_SSL = True
    OIDC_TIMEOUT = 5
    OIDC_STORE_ACCESS_TOKEN = False
    OIDC_STORE_ID_TOKEN = False
    OIDC_AUTHENTICATE_CLASS = "apps.accounts.oidc.PortalOIDCRequestView"
    OIDC_CALLBACK_CLASS = "apps.accounts.oidc.PortalOIDCCallbackView"
    OIDC_OP_LOGOUT_URL_METHOD = "apps.accounts.oidc.oidc_logout_url"
    AUTHENTICATION_BACKENDS = ["apps.accounts.oidc.PortalOIDCBackend"]
else:
    AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "accounts:login"
LANGUAGE_CODE = "en"
TIME_ZONE = os.environ.get("TZ", "Europe/Copenhagen")
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
# Do not impose HSTS on other internal applications or request public preloading.
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
LOGGING = {
    "version": 1, "disable_existing_loggers": False,
    "formatters": {"safe": {"()": "apps.core.logging.SafeFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "safe"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django": {"handlers": ["console"], "level": "INFO", "propagate": False}},
}
# This internal hostname has no managed child sites and cannot use public preload.
# Keep HSTS on this hostname without asserting HTTPS for unrelated descendants.
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]


def bounded_import_setting(name, default, upper):
    try:
        value = int(os.environ.get(name, default))
    except ValueError as error:
        raise ImproperlyConfigured(f"{name} must be an integer.") from error
    if not 1 <= value <= upper:
        raise ImproperlyConfigured(f"{name} must be between 1 and {upper}.")
    return value


JSON_IMPORT_MAX_BYTES = bounded_import_setting("JSON_IMPORT_MAX_BYTES", 1048576, 5242880)
JSON_IMPORT_MAX_RECORDS = bounded_import_setting("JSON_IMPORT_MAX_RECORDS", 500, 1000)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        ("apps.api.authentication.KeycloakBearerAuthentication" if AUTH_MODE == "oidc"
         else "apps.api.authentication.BearerCredentialAuthentication"),
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": "apps.api.pagination.PortalPagination",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "60/min", "user": "240/min"},
    "EXCEPTION_HANDLER": "apps.api.exceptions.portal_exception_handler",
    "PAGE_SIZE": 25,
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Customer Contact Portal API",
    "DESCRIPTION": "Versioned internal API. Session writes require CSRF; bearer credentials require a matching scope and user permission.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "ENUM_NAME_OVERRIDES": {
        "CustomerStatusEnum": [("active", "Active"), ("inactive", "Archived")],
        "AssignmentStatusEnum": [("active", "Active"), ("suspended", "Suspended"),
                                 ("expired", "Expired"), ("terminated", "Terminated")],
    },
}
if AUTH_MODE == "oidc":
    SPECTACULAR_SETTINGS["DESCRIPTION"] = (
        "Versioned internal API. Session writes require CSRF; Keycloak Bearer access tokens "
        "require the portal audience and client roles."
    )
DATA_UPLOAD_MAX_MEMORY_SIZE = max(JSON_IMPORT_MAX_BYTES + 65536, 2621440)
