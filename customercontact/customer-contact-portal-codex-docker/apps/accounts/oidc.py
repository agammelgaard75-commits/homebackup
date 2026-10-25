"""Keycloak integration around mozilla-django-oidc and PyJWT.

Only issuer/subject identifies a user. The portal's three client roles are the
sole source of OIDC authorization; realm and generic admin roles are ignored.
"""
import time
from functools import lru_cache
from urllib.parse import urlencode, urlparse

import jwt
import requests
from django.conf import settings
from django.contrib import auth
from django.contrib.auth import get_user_model
from django.core.exceptions import SuspiciousOperation
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse
from mozilla_django_oidc.auth import OIDCAuthenticationBackend
from mozilla_django_oidc.utils import absolutify, import_from_settings
from mozilla_django_oidc.views import OIDCAuthenticationCallbackView, OIDCAuthenticationRequestView

from .models import OIDCIdentity
from .services import role_from_oidc_claims, sync_oidc_user

SESSION_MAX_AGE = 300


class OIDCUnavailable(Exception):
    pass


@lru_cache(maxsize=1)
def provider_metadata():
    issuer = settings.OIDC_ISSUER_URL
    try:
        response = requests.get(f"{issuer}/.well-known/openid-configuration", timeout=5)
        response.raise_for_status()
        metadata = response.json()
        if metadata.get("issuer") != issuer:
            raise OIDCUnavailable("OIDC discovery issuer mismatch")
        origin = urlparse(issuer)
        for key in ("authorization_endpoint", "token_endpoint", "userinfo_endpoint", "jwks_uri", "end_session_endpoint"):
            endpoint = metadata.get(key)
            parsed = urlparse(endpoint or "")
            if parsed.scheme != "https" or parsed.netloc != origin.netloc or not endpoint:
                raise OIDCUnavailable("OIDC discovery endpoint mismatch")
        return metadata
    except (requests.RequestException, ValueError, TypeError) as error:
        raise OIDCUnavailable("OIDC provider unavailable") from error


DISCOVERED_SETTINGS = {
    "OIDC_OP_AUTHORIZATION_ENDPOINT": "authorization_endpoint",
    "OIDC_OP_TOKEN_ENDPOINT": "token_endpoint",
    "OIDC_OP_USER_ENDPOINT": "userinfo_endpoint",
    "OIDC_OP_JWKS_ENDPOINT": "jwks_uri",
}


def oidc_setting(name, *default):
    if name in DISCOVERED_SETTINGS:
        return provider_metadata()[DISCOVERED_SETTINGS[name]]
    return import_from_settings(name, *default)


role_from_claims = role_from_oidc_claims


def verify_access_token(token):
    """Use PyJWT for signature, claims and JWKS rotation; accept access tokens only."""
    try:
        if not token or len(token) > 16384:
            raise jwt.InvalidTokenError()
        jwks = jwks_client()
        key = jwks.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token, key.key, algorithms=["RS256"], issuer=settings.OIDC_ISSUER_URL,
            audience=settings.OIDC_API_AUDIENCE,
            options={"require": ["exp", "iat", "iss", "sub", "aud"]},
        )
        if claims.get("typ") != "Bearer" or not isinstance(claims.get("sub"), str) or not claims["sub"]:
            raise jwt.InvalidTokenError()
        return claims
    except (jwt.PyJWTError, OIDCUnavailable, requests.RequestException, ValueError) as error:
        raise SuspiciousOperation("Invalid OIDC access token") from error


@lru_cache(maxsize=1)
def jwks_client():
    return jwt.PyJWKClient(provider_metadata()["jwks_uri"], cache_jwk_set=True,
                           lifespan=300, timeout=5)


def user_for_claims(claims):
    return sync_oidc_user(claims)


class PortalOIDCBackend(OIDCAuthenticationBackend):
    get_settings = staticmethod(oidc_setting)

    def __init__(self):
        # Django instantiates permission backends on every has_perm call. Keep
        # discovery out of those calls and only contact Keycloak during login.
        self.UserModel = get_user_model()
        self.OIDC_RP_CLIENT_ID = settings.OIDC_CLIENT_ID
        self.OIDC_RP_CLIENT_SECRET = settings.OIDC_CLIENT_SECRET
        self.OIDC_RP_SIGN_ALGO = "RS256"
        self.OIDC_RP_IDP_SIGN_KEY = None
        self.OIDC_OP_TOKEN_ENDPOINT = None
        self.OIDC_OP_USER_ENDPOINT = None
        self.OIDC_OP_JWKS_ENDPOINT = None

    def authenticate(self, request, **kwargs):
        metadata = provider_metadata()
        self.OIDC_OP_TOKEN_ENDPOINT = metadata["token_endpoint"]
        self.OIDC_OP_USER_ENDPOINT = metadata["userinfo_endpoint"]
        self.OIDC_OP_JWKS_ENDPOINT = metadata["jwks_uri"]
        return super().authenticate(request, **kwargs)

    def raise_token_response_error(self, response):
        # The upstream implementation includes response bodies in exceptions.
        # Provider error bodies can carry sensitive details, so keep ours terse.
        if response.status_code != 200:
            raise requests.HTTPError("OIDC token exchange failed.", response=response)

    def _verify_jws(self, payload, key):
        try:
            claims = jwt.decode(
                payload, key, algorithms=["RS256"], issuer=settings.OIDC_ISSUER_URL,
                audience=settings.OIDC_CLIENT_ID,
                options={"require": ["exp", "iat", "iss", "sub", "aud"]},
            )
            audience = claims["aud"]
            if claims.get("typ") == "Bearer" or (claims.get("azp") and claims["azp"] != settings.OIDC_CLIENT_ID):
                raise jwt.InvalidTokenError()
            if isinstance(audience, list) and len(audience) > 1 and claims.get("azp") != settings.OIDC_CLIENT_ID:
                raise jwt.InvalidTokenError()
            return claims
        except jwt.PyJWTError as error:
            raise SuspiciousOperation("Invalid OIDC ID token") from error

    def get_or_create_user(self, access_token, id_token, payload):
        access_claims = verify_access_token(access_token)
        if access_claims["sub"] != payload.get("sub") or access_claims["iss"] != payload.get("iss"):
            raise SuspiciousOperation("OIDC token subject mismatch")
        return user_for_claims(access_claims)

    def get_user(self, user_id):
        user = super().get_user(user_id)
        if not user or user.is_superuser or not OIDCIdentity.objects.filter(user=user, issuer=settings.OIDC_ISSUER_URL).exists():
            return None
        return user


class PortalOIDCRequestView(OIDCAuthenticationRequestView):
    get_settings = staticmethod(oidc_setting)

    def __init__(self, *args, **kwargs):
        # Discovery occurs on request, so an unavailable provider returns 503.
        from django.views.generic import View
        View.__init__(self, *args, **kwargs)

    def get(self, request):
        try:
            self.OIDC_OP_AUTH_ENDPOINT = oidc_setting("OIDC_OP_AUTHORIZATION_ENDPOINT")
            self.OIDC_RP_CLIENT_ID = settings.OIDC_CLIENT_ID
            configured = settings.OIDC_REDIRECT_URI
            actual = absolutify(request, reverse("oidc_authentication_callback"))
            if configured and configured != actual:
                return HttpResponse("OIDC callback URL does not match configuration.", status=503)
            return super().get(request)
        except OIDCUnavailable:
            return HttpResponse("Identity provider unavailable.", status=503)


class PortalOIDCCallbackView(OIDCAuthenticationCallbackView):
    def login_success(self):
        response = super().login_success()
        self.request.session["oidc_verified_at"] = time.time()
        return response

    def login_failure(self):
        if self.request.user.is_authenticated:
            auth.logout(self.request)
        return HttpResponseForbidden("Access denied. A portal role is required.")

    def get(self, request):
        try:
            return super().get(request)
        except (OIDCUnavailable, requests.RequestException):
            if request.user.is_authenticated:
                auth.logout(request)
            return HttpResponse("Identity provider unavailable.", status=503)


def oidc_login(request):
    if request.method != "GET":
        return HttpResponse(status=405)
    target = reverse("oidc_authentication_init")
    if request.GET.get("next"):
        target += "?" + urlencode({"next": request.GET["next"]})
    return HttpResponseRedirect(target)


def oidc_logged_out(request):
    return HttpResponse("Signed out of the portal. Close your browser or sign in again.")


def oidc_logout_url(request):
    try:
        endpoint = provider_metadata()["end_session_endpoint"]
    except OIDCUnavailable:
        return reverse("accounts:logged_out")
    return endpoint + "?" + urlencode({
        "client_id": settings.OIDC_CLIENT_ID,
        "post_logout_redirect_uri": request.build_absolute_uri(reverse("accounts:logged_out")),
    })


class OIDCSessionGateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.AUTH_MODE == "oidc" and not request.path.startswith("/oidc/") and request.user.is_authenticated:
            verified = request.session.get("oidc_verified_at", 0)
            if (not isinstance(verified, (int, float)) or time.time() - verified > SESSION_MAX_AGE
                    or not request.user.is_active):
                auth.logout(request)
        return self.get_response(request)
