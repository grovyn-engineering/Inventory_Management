from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from inventory.models import Location, Product, ProductVariant, Stock
from notifications.models import Alert
from users.models import User


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    LOW_STOCK_THRESHOLD=5,
    EXPIRY_ALERT_DAYS=2,
    WHATSAPP_API_URL="https://example.com/wa",
)
class StockNotificationTests(TestCase):
    def setUp(self):
        self.location_a = Location.objects.create(name="Hyderabad")
        self.location_b = Location.objects.create(name="Bengaluru")

        self.admin = User.objects.create_user(
            username="admin",
            password="pass1234",
            role="admin",
            email="admin@example.com",
            phone_number="9111111111",
        )
        self.manager_a = User.objects.create_user(
            username="manager-a",
            password="pass1234",
            role="manager",
            location=self.location_a,
            email="manager.a@example.com",
            phone_number="9222222222",
        )
        self.manager_b = User.objects.create_user(
            username="manager-b",
            password="pass1234",
            role="manager",
            location=self.location_b,
            email="manager.b@example.com",
            phone_number="9333333333",
        )

        self.product = Product.objects.create(
            name="Milk",
            price=20,
            location=self.location_a,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            location=self.location_a,
            name="1L",
            sku="MILK-1L",
            price=20,
            attributes={},
        )

    @patch("notifications.service._send_whatsapp_request", return_value=True)
    def test_low_stock_stock_update_and_role_scope(self, _wa_mock):
        Stock.objects.create(
            product=self.product,
            variant=self.variant,
            location=self.location_a,
            quantity=3,
            expiry_date=timezone.localdate() + timedelta(days=10),
        )

        manager_types = set(
            Alert.objects.filter(user=self.manager_a).values_list("alert_type", flat=True)
        )
        admin_types = set(
            Alert.objects.filter(user=self.admin).values_list("alert_type", flat=True)
        )

        self.assertIn("stock_update", manager_types)
        self.assertIn("low_stock", manager_types)
        self.assertIn("stock_update", admin_types)
        self.assertIn("low_stock", admin_types)
        self.assertFalse(Alert.objects.filter(user=self.manager_b).exists())

    @patch("notifications.service._send_whatsapp_request", return_value=True)
    def test_zero_stock_alert_on_quantity_drop_to_zero(self, _wa_mock):
        stock = Stock.objects.create(
            product=self.product,
            variant=self.variant,
            location=self.location_a,
            quantity=8,
            expiry_date=timezone.localdate() + timedelta(days=10),
        )
        Alert.objects.all().delete()

        stock.quantity = 0
        stock.save(update_fields=["quantity"])

        types = set(Alert.objects.filter(user=self.manager_a).values_list("alert_type", flat=True))
        self.assertIn("stock_update", types)
        self.assertIn("zero_stock", types)

    @patch("notifications.service._send_whatsapp_request", return_value=True)
    def test_expiry_alert_is_generated_before_expiry(self, _wa_mock):
        Stock.objects.create(
            product=self.product,
            variant=self.variant,
            location=self.location_a,
            quantity=7,
            expiry_date=timezone.localdate() + timedelta(days=1),
        )

        self.assertTrue(
            Alert.objects.filter(user=self.manager_a, alert_type="expiry").exists()
        )
        self.assertTrue(
            Alert.objects.filter(user=self.admin, alert_type="expiry").exists()
        )

    @patch("notifications.service._send_whatsapp_request", return_value=True)
    def test_flagged_or_thumbs_up_detection_triggers_alert(self, _wa_mock):
        flagged_product = Product.objects.create(
            name="Biscuits thumbs up",
            price=15,
            location=self.location_a,
        )
        flagged_variant = ProductVariant.objects.create(
            product=flagged_product,
            location=self.location_a,
            name="Pack",
            sku="BIS-THUMB",
            price=15,
            attributes={"flagged": True},
        )

        Stock.objects.create(
            product=flagged_product,
            variant=flagged_variant,
            location=self.location_a,
            quantity=2,
            expiry_date=timezone.localdate() + timedelta(days=9),
        )

        self.assertTrue(
            Alert.objects.filter(user=self.manager_a, alert_type="flagged").exists()
        )

    @patch("notifications.service._send_whatsapp_request", return_value=True)
    def test_duplicate_notifications_are_not_created_for_same_event_key(self, _wa_mock):
        stock = Stock.objects.create(
            product=self.product,
            variant=self.variant,
            location=self.location_a,
            quantity=4,
            expiry_date=timezone.localdate() + timedelta(days=3),
        )
        baseline = Alert.objects.filter(user=self.manager_a).count()

        stock.save(update_fields=["updated_at"])
        after = Alert.objects.filter(user=self.manager_a).count()

        self.assertEqual(after, baseline)

    @patch("notifications.service._send_whatsapp_request", return_value=True)
    def test_email_and_whatsapp_use_user_profile_contacts(self, wa_mock):
        Stock.objects.create(
            product=self.product,
            variant=self.variant,
            location=self.location_a,
            quantity=3,
            expiry_date=timezone.localdate() + timedelta(days=7),
        )

        recipients = {recipient for email in mail.outbox for recipient in email.to}
        self.assertIn(self.admin.email, recipients)
        self.assertIn(self.manager_a.email, recipients)
        self.assertNotIn(self.manager_b.email, recipients)

        called_numbers = {call.args[0] for call in wa_mock.call_args_list}
        self.assertIn(self.admin.phone_number, called_numbers)
        self.assertIn(self.manager_a.phone_number, called_numbers)
        self.assertNotIn(self.manager_b.phone_number, called_numbers)
