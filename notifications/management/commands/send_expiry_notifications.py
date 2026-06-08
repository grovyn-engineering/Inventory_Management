from django.core.management.base import BaseCommand

from notifications.service import run_expiry_notifications


class Command(BaseCommand):
    help = "Dispatch expiry notifications for stocks approaching expiry."

    def handle(self, *args, **options):
        run_expiry_notifications()
        self.stdout.write(self.style.SUCCESS("Expiry notifications dispatched."))
