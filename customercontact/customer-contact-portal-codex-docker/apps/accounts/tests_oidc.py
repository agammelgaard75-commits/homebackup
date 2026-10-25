"""OIDC security and integration tests; no live Keycloak is required."""
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import include, path
from mozilla_django_oidc.views import OIDCLogoutView
from rest_framework.authentication import SessionAuthentication

from apps.accounts.admin import portal_admin
from apps.accounts.models import OIDCIdentity, User
from apps.accounts.oidc import (
    OIDCUnavailable, PortalOIDCBackend, PortalOIDCCallbackView, PortalOIDCRequestView,
    oidc_logged_out, oidc_login, provider_metadata, user_for_claims, verify_access_token,
)
from apps.api.authentication import KeycloakBearerAuthentication
from apps.api.views import CredentialListAPI, CurrentUserAPI
from apps.api.imports import ImportPreviewAPI
from apps.cleanup.api import ArchivedCustomersAPI
from apps.customers.api import CustomerListAPI
from apps.customers.models import Customer


ISSUER = "https://keycloak.test/realms/portal"
CLIENT = "customer-portal"
METADATA = {
    "issuer": ISSUER,
    "authorization_endpoint": ISSUER + "/protocol/openid-connect/auth",
    "token_endpoint": ISSUER + "/protocol/openid-connect/token",
    "userinfo_endpoint": ISSUER + "/protocol/openid-connect/userinfo",
    "jwks_uri": ISSUER + "/protocol/openid-connect/certs",
    "end_session_endpoint": ISSUER + "/protocol/openid-connect/logout",
}

account_urls = ([
    path("login/", oidc_login, name="login"),
    path("logout/", OIDCLogoutView.as_view(), name="logout"),
    path("logged-out/", oidc_logged_out, name="logged_out"),
], "accounts")
urlpatterns = [
    path("accounts/", include(account_urls)),
    path("oidc/authenticate/", PortalOIDCRequestView.as_view(), name="oidc_authentication_init"),
    path("oidc/callback/", PortalOIDCCallbackView.as_view(), name="oidc_authentication_callback"),
    path("api/v1/me/", CurrentUserAPI.as_view(authentication_classes=[KeycloakBearerAuthentication])),
    path("api/v1/customers/", CustomerListAPI.as_view(authentication_classes=[KeycloakBearerAuthentication, SessionAuthentication])),
    path("api/v1/cleanup/archived-customers/", ArchivedCustomersAPI.as_view(authentication_classes=[KeycloakBearerAuthentication])),
    path("api/v1/credentials/", CredentialListAPI.as_view(authentication_classes=[KeycloakBearerAuthentication])),
    path("api/v1/imports/customers/preview/", ImportPreviewAPI.as_view(
        kind="customers", authentication_classes=[KeycloakBearerAuthentication])),
    path("admin/", portal_admin.urls),
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


@override_settings(
    ROOT_URLCONF="apps.accounts.tests_oidc", AUTH_MODE="oidc",
    AUTHENTICATION_BACKENDS=["apps.accounts.oidc.PortalOIDCBackend"],
    OIDC_ISSUER_URL=ISSUER, OIDC_CLIENT_ID=CLIENT, OIDC_CLIENT_SECRET="test-only-secret",
    OIDC_API_AUDIENCE=CLIENT, OIDC_REDIRECT_URI="", OIDC_RP_CLIENT_ID=CLIENT,
    OIDC_RP_CLIENT_SECRET="test-only-secret", OIDC_RP_SIGN_ALGO="RS256",
    OIDC_RP_SCOPES="openid", OIDC_USE_PKCE=True, OIDC_USE_NONCE=True,
    OIDC_VERIFY_SSL=True, OIDC_TIMEOUT=5, OIDC_STORE_ACCESS_TOKEN=False,
    OIDC_STORE_ID_TOKEN=False,
    OIDC_OP_LOGOUT_URL_METHOD="apps.accounts.oidc.oidc_logout_url",
    STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
              "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
)
class OIDCTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public_key = cls.private_key.public_key()

    def claims(self, role="portal-viewer", subject="person-1", **overrides):
        now = int(time.time())
        claims = {
            "iss": ISSUER, "sub": subject, "aud": CLIENT, "iat": now,
            "exp": now + 240, "typ": "Bearer",
            "resource_access": {CLIENT: {"roles": [role] if role else []}},
        }
        claims.update(overrides)
        return claims

    def token(self, claims, key=None):
        return jwt.encode(claims, key or self.private_key, algorithm="RS256", headers={"kid": "test-key"})

    def key_patch(self):
        client = Mock()
        client.get_signing_key_from_jwt.return_value = SimpleNamespace(key=self.public_key)
        return patch("apps.accounts.oidc.jwks_client", return_value=client)

    def test_discovery_requires_exact_issuer_and_https_same_host(self):
        response = Mock()
        response.json.return_value = METADATA
        with patch("apps.accounts.oidc.requests.get", return_value=response) as get:
            provider_metadata.cache_clear()
            self.assertEqual(provider_metadata()["issuer"], ISSUER)
            self.assertEqual(get.call_args.kwargs["timeout"], 5)
            for changed in ({"issuer": "https://wrong.test/realms/portal"},
                            {"jwks_uri": "http://keycloak.test/certs"},
                            {"token_endpoint": "https://other.test/token"}):
                provider_metadata.cache_clear()
                response.json.return_value = {**METADATA, **changed}
                with self.assertRaises(OIDCUnavailable):
                    provider_metadata()
        provider_metadata.cache_clear()

    def test_access_token_signature_issuer_audience_expiry_and_type(self):
        with self.key_patch():
            self.assertEqual(verify_access_token(self.token(self.claims()))["sub"], "person-1")
            for claims in (
                self.claims(iss="https://wrong.test/realms/portal"),
                self.claims(aud="wrong-audience"),
                self.claims(exp=int(time.time()) - 5),
                self.claims(iat=int(time.time()) - 301, exp=int(time.time()) + 60),
                self.claims(typ="ID"),
            ):
                with self.subTest(claims=claims):
                    with self.assertRaisesMessage(Exception, "Invalid OIDC access token"):
                        verify_access_token(self.token(claims))
            with self.assertRaisesMessage(Exception, "Invalid OIDC access token"):
                verify_access_token("malformed")
            wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            with self.assertRaisesMessage(Exception, "Invalid OIDC access token"):
                verify_access_token(self.token(self.claims(), wrong_key))
        backend = PortalOIDCBackend()
        now = int(time.time())
        id_claims = {"iss": ISSUER, "sub": "person-1", "aud": "wrong-audience",
                     "iat": now, "exp": now + 240}
        with self.assertRaisesMessage(Exception, "Invalid OIDC ID token"):
            backend._verify_jws(self.token(id_claims), self.public_key)

    def test_browser_login_role_mapping_and_no_email_auto_link(self):
        local = User.objects.create_user(username="existing", email="same@example.test", password="local-only-test")
        with patch("apps.accounts.oidc.provider_metadata", return_value=METADATA), self.key_patch(), \
             patch.object(PortalOIDCBackend, "retrieve_matching_jwk", return_value=self.public_key), \
             patch.object(PortalOIDCBackend, "get_token") as token_exchange:
            response = self.client.get("/", secure=True)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/accounts/login/", response["Location"])
            response = self.client.get("/accounts/login/?next=/", secure=True)
            self.assertEqual(response.status_code, 302)
            response = self.client.get(response["Location"], secure=True)
            self.assertIn(METADATA["authorization_endpoint"], response["Location"])
            state, values = next(iter(self.client.session["oidc_states"].items()))
            now = int(time.time())
            id_claims = {"iss": ISSUER, "sub": "person-1", "aud": CLIENT, "iat": now,
                         "exp": now + 240, "nonce": values["nonce"], "email": "same@example.test"}
            token_exchange.return_value = {"id_token": self.token(id_claims),
                                           "access_token": self.token(self.claims())}
            response = self.client.get(f"/oidc/callback/?state={state}&code=test-code", secure=True)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response["Location"], "/")
            linked = OIDCIdentity.objects.get(issuer=ISSUER, subject="person-1")
            self.assertNotEqual(linked.user_id, local.pk)
            self.assertFalse(linked.user.has_usable_password())
            self.assertFalse(linked.user.is_staff)
            self.assertFalse(linked.user.is_superuser)
            self.assertEqual(list(linked.user.groups.values_list("name", flat=True)), ["Viewer"])
            self.assertEqual(self.client.get("/", secure=True).status_code, 200)
            self.assertNotIn("oidc_access_token", self.client.session)
            self.assertNotIn("oidc_id_token", self.client.session)
            session = self.client.session
            session["oidc_verified_at"] = time.time() - 301
            session.save()
            self.assertEqual(self.client.get("/", secure=True).status_code, 302)

    def test_browser_rejects_user_without_portal_role(self):
        with patch("apps.accounts.oidc.provider_metadata", return_value=METADATA), self.key_patch(), \
             patch.object(PortalOIDCBackend, "retrieve_matching_jwk", return_value=self.public_key), \
             patch.object(PortalOIDCBackend, "get_token") as token_exchange:
            self.client.get("/oidc/authenticate/", secure=True)
            state, values = next(iter(self.client.session["oidc_states"].items()))
            now = int(time.time())
            id_claims = {"iss": ISSUER, "sub": "no-portal-role", "aud": CLIENT, "iat": now,
                         "exp": now + 240, "nonce": values["nonce"]}
            token_exchange.return_value = {"id_token": self.token(id_claims),
                                           "access_token": self.token(self.claims(role=None, subject="no-portal-role"))}
            response = self.client.get(f"/oidc/callback/?state={state}&code=test-code", secure=True)
            self.assertEqual(response.status_code, 403)
            self.assertFalse(OIDCIdentity.objects.filter(subject="no-portal-role").exists())
            self.assertNotIn("_auth_user_id", self.client.session)

    def test_editor_admin_and_removed_role(self):
        for role, group in (("portal-viewer", "Viewer"), ("portal-editor", "Editor"),
                            ("portal-admin", "Administrator")):
            with self.subTest(role=role):
                user = user_for_claims(self.claims(role=role, subject=role))
                self.assertEqual(list(user.groups.values_list("name", flat=True)), [group])
                self.assertEqual(user.has_perm("accounts.administer_portal"), role == "portal-admin")
                self.assertEqual(user.has_perm("accounts.edit_portal"), role != "portal-viewer")
        self.assertIsNone(user_for_claims(self.claims(role=None, subject="no-role")))
        self.assertFalse(OIDCIdentity.objects.filter(subject="no-role").exists())

    def test_api_authentication_permissions_and_service_account(self):
        Customer.objects.create(name="Visible company")
        with self.key_patch():
            self.assertEqual(self.client.get("/api/v1/me/", secure=True).status_code, 401)
            self.assertEqual(self.client.get("/api/v1/me/", HTTP_AUTHORIZATION="Bearer bad", secure=True).status_code, 401)
            viewer = self.token(self.claims(subject="service-account-automation"))
            response = self.client.get("/api/v1/customers/", HTTP_AUTHORIZATION=f"Bearer {viewer}", secure=True)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["count"], 1)
            response = self.client.post("/api/v1/customers/", {"name": "Blocked"},
                                        content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {viewer}", secure=True)
            self.assertEqual(response.status_code, 403)
            self.assertEqual(self.client.get("/api/v1/cleanup/archived-customers/",
                HTTP_AUTHORIZATION=f"Bearer {viewer}", secure=True).status_code, 403)
            self.assertEqual(self.client.post("/api/v1/imports/customers/preview/", {},
                content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {viewer}", secure=True).status_code, 403)
            no_role = self.token(self.claims(role=None, subject="service-account-no-role"))
            self.assertEqual(self.client.get("/api/v1/me/", HTTP_AUTHORIZATION=f"Bearer {no_role}", secure=True).status_code, 403)
            editor = self.token(self.claims(role="portal-editor", subject="editor"))
            response = self.client.post("/api/v1/customers/", {"name": "Editor company"},
                                        content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {editor}", secure=True)
            self.assertEqual(response.status_code, 201)
            admin = self.token(self.claims(role="portal-admin", subject="admin"))
            self.assertEqual(self.client.get("/api/v1/cleanup/archived-customers/",
                HTTP_AUTHORIZATION=f"Bearer {admin}", secure=True).status_code, 200)
            self.assertEqual(self.client.post("/api/v1/imports/customers/preview/", {},
                content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {admin}", secure=True).status_code, 400)
            self.assertEqual(self.client.get("/api/v1/credentials/",
                HTTP_AUTHORIZATION=f"Bearer {admin}", secure=True).status_code, 403)
            self.assertEqual(self.client.get("/api/v1/me/", HTTP_AUTHORIZATION="Bearer ccp_fake.fake",
                secure=True).status_code, 401)

    def test_removed_role_and_session_csrf(self):
        user = user_for_claims(self.claims(role="portal-editor", subject="role-changed"))
        with self.key_patch():
            removed = self.token(self.claims(role=None, subject="role-changed"))
            self.assertEqual(self.client.get("/api/v1/me/", HTTP_AUTHORIZATION=f"Bearer {removed}",
                                             secure=True).status_code, 403)
        client = Client(enforce_csrf_checks=True)
        client.force_login(user, backend="apps.accounts.oidc.PortalOIDCBackend")
        session = client.session
        session["oidc_verified_at"] = time.time()
        session.save()
        client.get("/", secure=True)
        self.assertEqual(client.post("/api/v1/customers/", {"name": "CSRF blocked"},
                                     content_type="application/json", secure=True).status_code, 403)
        csrf = client.cookies["csrftoken"].value
        response = client.post("/api/v1/customers/", {"name": "CSRF allowed"},
                               content_type="application/json", secure=True, HTTP_X_CSRFTOKEN=csrf,
                               HTTP_REFERER="https://testserver/")
        self.assertEqual(response.status_code, 201, response.content)
        session = client.session
        session["oidc_verified_at"] = time.time() - 301
        session.save()
        self.assertEqual(client.get("/", secure=True).status_code, 302)

    def test_unavailable_provider_admin_login_and_logout(self):
        with patch("apps.accounts.oidc.provider_metadata", side_effect=OIDCUnavailable()):
            self.assertEqual(self.client.get("/oidc/authenticate/", secure=True).status_code, 503)
        self.assertEqual(self.client.post("/accounts/login/", {"username": "x", "password": "y"}, secure=True).status_code, 405)
        self.assertEqual(self.client.get("/admin/login/", secure=True).status_code, 302)
        self.assertEqual(self.client.get("/accounts/logout/", secure=True).status_code, 405)
        user = user_for_claims(self.claims(role="portal-admin", subject="logout-user"))
        self.client.force_login(user, backend="apps.accounts.oidc.PortalOIDCBackend")
        session = self.client.session
        session["oidc_verified_at"] = time.time()
        session.save()
        with patch("apps.accounts.oidc.provider_metadata", return_value=METADATA):
            response = self.client.post("/accounts/logout/", secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertIn(METADATA["end_session_endpoint"], response["Location"])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_explicit_link_and_inactive_account(self):
        user = User.objects.create_user(username="prior", password="local-test")
        call_command("link_oidc_user", "prior", ISSUER, "linked-sub", verbosity=0)
        self.assertFalse(OIDCIdentity.objects.filter(user=user).exists())
        call_command("link_oidc_user", "prior", ISSUER, "linked-sub", "--apply", verbosity=0)
        self.assertEqual(user_for_claims(self.claims(subject="linked-sub")).pk, user.pk)
        user.is_active = False
        user.save(update_fields=["is_active"])
        self.assertIsNone(user_for_claims(self.claims(subject="linked-sub")))

    def test_oidc_managed_groups_are_not_editable_in_administration(self):
        admin = user_for_claims(self.claims(role="portal-admin", subject="portal-admin"))
        target = user_for_claims(self.claims(subject="portal-viewer"))
        self.client.force_login(admin, backend="apps.accounts.oidc.PortalOIDCBackend")
        session = self.client.session
        session["oidc_verified_at"] = time.time()
        session.save()
        response = self.client.get(f"/admin/accounts/user/{target.pk}/change/", secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="groups"')
        self.assertEqual(self.client.get("/admin/accounts/user/add/", secure=True).status_code, 403)
