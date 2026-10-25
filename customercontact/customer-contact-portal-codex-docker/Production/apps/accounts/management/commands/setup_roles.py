from django.core.management.base import BaseCommand

from apps.accounts.services import setup_roles


class Command(BaseCommand):
    help = "Initialize/reconcile Viewer, Editor and Administrator groups after migrate."

    def handle(self, *args, **options):
        setup_roles()
        self.stdout.write(self.style.SUCCESS("Portal roles initialized."))
