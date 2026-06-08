from django.core.management.base import BaseCommand

from orders.expired_orders_cleanup_service import cleanup_expired_orders_and_email


class Command(BaseCommand):
    help = "Email expired orders grouped by location and delete them after successful email delivery."

    def handle(self, *args, **options):
        result = cleanup_expired_orders_and_email()
        self.stdout.write(
            self.style.SUCCESS(
                f"Cleanup complete. Deleted orders: {result['deleted_orders']}, attachments: {result['attachments_sent']}"
            )
        )
