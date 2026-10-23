from django.contrib.auth.forms import AuthenticationForm


class PortalAdminAuthenticationForm(AuthenticationForm):
    """Use the portal's administrator permission instead of Django's staff flag."""

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.has_perm("accounts.administer_portal"):
            raise self.get_invalid_login_error()
