from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    class Meta(AbstractUser.Meta):
        permissions = [
            ("access_portal", "Can access the portal"),
            ("edit_portal", "Can maintain portal business records"),
            ("administer_portal", "Can administer the portal"),
        ]
