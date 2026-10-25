import importlib
import json
import logging
import os
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.db import OperationalError
from django.test import SimpleTestCase, TestCase

from .logging import SafeFormatter


class HealthTests(TestCase):
    def test_health_checks_database_without_authentication(self):
        response = self.client.get("/health/", HTTP_X_FORWARDED_PROTO="https")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertIn("no-store", response["Cache-Control"])

    def test_database_failure_is_non_sensitive(self):
        with patch("apps.core.views.connection.cursor", side_effect=OperationalError("sensitive connection details")):
            response = self.client.get("/health/", secure=True)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})
        self.assertNotContains(response, "sensitive", status_code=503)

    def test_health_rejects_mutations(self):
        self.assertEqual(self.client.post("/health/", secure=True).status_code, 405)


class SecurityTests(SimpleTestCase):
    def test_http_redirect_and_security_headers(self):
        response = self.client.get("/accounts/login/")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://testserver/accounts/login/")
        response = self.client.get("/accounts/login/", secure=True)
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("max-age=31536000", response["Strict-Transport-Security"])

    def test_unknown_host_is_rejected(self):
        self.assertEqual(self.client.get("/accounts/login/", secure=True, HTTP_HOST="evil.invalid").status_code, 400)

    def test_settings_fail_closed(self):
        for name in ("DJANGO_SECRET_KEY", "POSTGRES_PASSWORD", "DJANGO_ALLOWED_HOSTS"):
            for value in ("", "REPLACE_ON_INSTALL"):
                with self.subTest(name=name, value=value), patch.dict(os.environ, {name: value}):
                    with self.assertRaises(ImproperlyConfigured):
                        importlib.reload(importlib.import_module("config.settings"))
        importlib.reload(importlib.import_module("config.settings"))

    def test_logs_exclude_request_and_exception_values(self):
        record = logging.LogRecord("django.request", logging.ERROR, "", 1, "secret@example.invalid /?password=value", (), None)
        record.status_code = 500
        record.exc_info = (ValueError, ValueError("private note"), None)
        self.assertEqual(json.loads(SafeFormatter().format(record)), {
            "level": "ERROR", "logger": "django.request", "status": 500, "exception": "ValueError",
        })
