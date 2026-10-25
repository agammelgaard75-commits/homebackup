"""Issue revocable, expiring API credentials without storing their plaintext secrets."""
import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from .models import APICredential

SCOPES = frozenset({"read", "write", "import", "audit", "cleanup"})


def _digest(secret):
    return hmac.new(settings.SECRET_KEY.encode(), secret.encode(), hashlib.sha256).hexdigest()


def require_credential_admin(actor):
    if not actor.is_active or not actor.has_perms(("accounts.access_portal", "accounts.administer_portal")):
        raise PermissionDenied


def issue_credential(*, actor, user, name, scopes, expires_at):
    require_credential_admin(actor)
    if not user.is_active or not user.has_perm("accounts.access_portal"):
        raise ValidationError({"user": "Choose an active portal user."})
    if not isinstance(scopes, list) or not scopes or set(scopes) - SCOPES or len(scopes) != len(set(scopes)):
        raise ValidationError({"scopes": "Choose distinct supported scopes."})
    if not expires_at or timezone.is_naive(expires_at) or not timezone.now() < expires_at <= timezone.now() + timedelta(days=366):
        raise ValidationError({"expires_at": "Choose an expiry within the next 366 days."})
    secret = secrets.token_urlsafe(32)
    credential = APICredential(user=user, created_by=actor, name=name, scopes=scopes,
                               expires_at=expires_at, secret_hash=_digest(secret))
    credential.full_clean()
    credential.save()
    return credential, f"ccp_{credential.pk.hex}.{secret}"


def revoke_credential(*, actor, credential):
    require_credential_admin(actor)
    if credential.revoked_at is None:
        credential.revoked_at = timezone.now()
        credential.save(update_fields=["revoked_at"])
    return credential


def rotate_credential(*, actor, credential):
    require_credential_admin(actor)
    if credential.revoked_at or credential.expires_at <= timezone.now():
        raise ValidationError("Create a new credential for an expired or revoked credential.")
    secret = secrets.token_urlsafe(32)
    credential.secret_hash = _digest(secret)
    credential.rotated_at = timezone.now()
    credential.save(update_fields=["secret_hash", "rotated_at"])
    return f"ccp_{credential.pk.hex}.{secret}"


def valid_credential(credential, secret):
    return (credential.revoked_at is None and credential.expires_at > timezone.now()
            and credential.user.is_active and credential.user.has_perm("accounts.access_portal")
            and hmac.compare_digest(credential.secret_hash, _digest(secret)))
