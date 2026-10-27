import importlib
import os
from io import StringIO
from unittest.mock import patch
from uuid import UUID

from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.core.cache import cache


class ProductionConfigurationTests(SimpleTestCase):
    environment = {
        "PORTAL_ENV": "production", "AUTH_MODE": "oidc", "DJANGO_DEBUG": "0",
        "DJANGO_SECRET_KEY": "synthetic-test-key-" * 4, "POSTGRES_PASSWORD": "synthetic-db-password-" * 3,
        "PORTAL_DOMAIN": "portal.example.invalid", "DJANGO_ALLOWED_HOSTS": "portal.example.invalid,127.0.0.1",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "https://portal.example.invalid",
        "OIDC_ISSUER_URL": "https://sso.example.invalid/realms/portal", "OIDC_CLIENT_ID": "portal",
        "OIDC_CLIENT_SECRET": "synthetic-client-secret", "OIDC_REDIRECT_URI": "https://portal.example.invalid/oidc/callback/",
    }

    def tearDown(self):
        importlib.reload(importlib.import_module("config.settings"))

    def test_production_requires_oidc_https_and_strong_secrets(self):
        for change in ({"AUTH_MODE": "local"}, {"DJANGO_DEBUG": "1"}, {"DJANGO_SECRET_KEY": "short"},
                       {"POSTGRES_PASSWORD": "short"}, {"OIDC_REDIRECT_URI": "https://wrong.invalid/oidc/callback/"},
                       {"DJANGO_CSRF_TRUSTED_ORIGINS": "https://wrong.invalid"}):
            with self.subTest(change=tuple(change)), patch.dict(os.environ, self.environment | change):
                with self.assertRaises(ImproperlyConfigured):
                    importlib.reload(importlib.import_module("config.settings"))

    def test_production_has_secure_sessions_and_only_oidc_backend(self):
        with patch.dict(os.environ, self.environment):
            configured = importlib.reload(importlib.import_module("config.settings"))
            self.assertTrue(configured.SESSION_COOKIE_SECURE)
            self.assertTrue(configured.CSRF_COOKIE_SECURE)
            self.assertTrue(configured.SECURE_SSL_REDIRECT)
            self.assertEqual(configured.AUTHENTICATION_BACKENDS, ["apps.accounts.oidc.PortalOIDCBackend"])

    @override_settings(AUTH_MODE="oidc")
    def test_oidc_preflight_checks_keys_and_sanitizes_failures(self):
        command = "apps.accounts.management.commands.check_oidc"
        with patch(f"{command}.provider_metadata"), patch(f"{command}.jwks_client") as client:
            client.return_value.get_signing_keys.return_value = [object()]
            call_command("check_oidc", stdout=StringIO())
            client.return_value.get_signing_keys.assert_called_once()
            client.side_effect = ValueError("private-provider-response")
            with self.assertRaisesMessage(CommandError, "OIDC discovery/JWKS failed") as error:
                call_command("check_oidc")
            self.assertNotIn("private-provider-response", str(error.exception))

    @override_settings(AUTH_MODE="local")
    def test_oidc_preflight_rejects_local_mode(self):
        with self.assertRaises(CommandError):
            call_command("check_oidc")


class ProductionAPIRegressionTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_all_business_routes_require_authentication(self):
        from apps.api.urls import urlpatterns
        for pattern in urlpatterns:
            if pattern.name == "health":
                continue
            kwargs = {key: UUID(int=1) for key in pattern.pattern.converters}
            path = reverse(f"api:{pattern.name}", kwargs=kwargs)
            view = pattern.callback.view_class
            for method in ("get", "post", "put", "patch"):
                if not hasattr(view, method):
                    continue
                cache.clear()
                with self.subTest(path=path, method=method):
                    response = getattr(self.client, method)(path, secure=True)
                    self.assertEqual(response.status_code, 401, response.content)

    def test_unexpected_api_failure_is_generic_json(self):
        with patch("apps.core.api.database_is_healthy", side_effect=RuntimeError("sensitive-connection-string")):
            response = self.client.get("/api/v1/health/", secure=True)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["code"], "server_error")
        self.assertNotContains(response, "sensitive", status_code=500)

    def test_anonymous_throttle_returns_429(self):
        from rest_framework.throttling import AnonRateThrottle
        with patch.object(AnonRateThrottle, "rate", "1/min", create=True), patch.object(AnonRateThrottle, "get_rate", return_value="1/min"):
            self.assertEqual(self.client.get("/api/v1/health/", secure=True).status_code, 200)
            self.assertEqual(self.client.get("/api/v1/health/", secure=True).status_code, 429)
