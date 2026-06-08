import hashlib
import hmac
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.utils import timezone
from rest_framework.test import APITestCase

from inventory.models import Location, Product, ProductVariant, Stock
from orders.models import Order
from orders.expired_orders_cleanup_service import cleanup_expired_orders_and_email
from users.models import User


class OrdersApiTests(APITestCase):
    def setUp(self):
        self.location_a = Location.objects.create(name="Orders A")
        self.location_b = Location.objects.create(name="Orders B")
        self.manager_user = User.objects.create_user(
            username="orders-manager",
            password="pass1234",
            role="manager",
            location=self.location_a,
        )
        self.admin_user = User.objects.create_user(
            username="orders-admin",
            password="pass1234",
            role="admin",
        )
        self.product = Product.objects.create(name="Coffee", price=Decimal("25.00"))
        self.location_product = Product.objects.create(
            name="Tea",
            price=Decimal("15.00"),
            location=self.location_a,
        )
        self.location_variant = ProductVariant.objects.create(
            product=self.location_product,
            location=self.location_a,
            name="Small",
            sku="TEA-SMALL",
            price=Decimal("15.00"),
            is_active=True,
        )
        self.location_product_b = Product.objects.create(
            name="Latte",
            price=Decimal("35.00"),
            location=self.location_b,
        )
        self.location_variant_b = ProductVariant.objects.create(
            product=self.location_product_b,
            location=self.location_b,
            name="Regular",
            sku="LATTE-REG",
            price=Decimal("35.00"),
            is_active=True,
        )
        Stock.objects.create(
            product=self.product,
            location=self.location_a,
            quantity=5,
            expiry_date="2030-01-01",
        )
        Stock.objects.create(
            product=self.location_product,
            variant=self.location_variant,
            location=self.location_a,
            quantity=7,
            expiry_date="2030-01-01",
        )
        Stock.objects.create(
            product=self.location_product_b,
            variant=self.location_variant_b,
            location=self.location_b,
            quantity=4,
            expiry_date="2030-01-01",
        )

    def authenticate(self, username, password="pass1234"):
        self.client.logout()
        self.assertTrue(self.client.login(username=username, password=password))

    def test_create_order_rejects_mismatched_location_for_manager(self):
        self.authenticate("orders-manager")

        response = self.client.post(
            "/api/orders/create-order/",
            {
                "location_id": self.location_b.id,
                "payment_method": "cash",
                "items": [{"product_id": self.product.id, "quantity": 1}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["message"], "Validation failed")
        self.assertTrue(any(error["field"] == "location_id" for error in response.data["errors"]))

    def test_verify_payment_rejects_cancelled_order(self):
        self.authenticate("orders-admin")
        order = Order.objects.create(
            location=self.location_a,
            status="cancelled",
            total_amount=Decimal("25.00"),
            razorpay_order_id="order_test_1",
        )
        signature = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            b"order_test_1|payment_test_1",
            hashlib.sha256,
        ).hexdigest()

        response = self.client.post(
            "/api/orders/verify-payment/",
            {
                "razorpay_order_id": "order_test_1",
                "razorpay_payment_id": "payment_test_1",
                "razorpay_signature": signature,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["message"], "Validation failed")
        self.assertTrue(any(error["field"] == "order_id" for error in response.data["errors"]))

    def test_products_by_location_returns_all_products_with_stock_for_location(self):
        self.authenticate("orders-admin")

        response = self.client.get(f"/products/{self.location_a.id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(any(item["_id"] == self.location_product.id for item in payload))
        self.assertFalse(any(item["_id"] == self.location_product_b.id for item in payload))

    def test_products_by_location_allows_manager_access_to_selected_location(self):
        self.authenticate("orders-manager")

        response = self.client.get(f"/products/{self.location_b.id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(any(item["_id"] == self.location_product_b.id for item in payload))

    def test_locations_api_returns_all_locations_for_manager(self):
        self.authenticate("orders-manager")

        response = self.client.get("/locations")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = {item["id"] for item in payload}
        self.assertEqual(ids, {self.location_a.id, self.location_b.id})

    def test_remove_cart_item_updates_session_cart(self):
        self.authenticate("orders-manager")
        session = self.client.session
        session["orders_cart_v1"] = [
            {"product_id": self.product.id, "variant_id": None, "quantity": 2},
            {"product_id": self.location_product.id, "variant_id": self.location_variant.id, "quantity": 1},
        ]
        session.save()

        response = self.client.post(
            "/api/orders/cart/remove-item/",
            {"product_id": self.product.id},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])

        updated_cart = self.client.session.get("orders_cart_v1") or []
        self.assertEqual(len(updated_cart), 1)
        self.assertEqual(updated_cart[0]["product_id"], self.location_product.id)


class ExpiredOrdersCleanupTests(APITestCase):
    def setUp(self):
        self.location_mumbai = Location.objects.create(name=" Mumbai ")
        self.location_hyderabad = Location.objects.create(name="Hyderabad")
        self.product = Product.objects.create(name="Rice", price=Decimal("50.00"))

    def _create_expired_order(self, location, days_old=31):
        order = Order.objects.create(
            location=location,
            status="completed",
            total_amount=Decimal("100.00"),
            payment_method="upi",
        )
        Order.objects.filter(id=order.id).update(created_at=timezone.now() - timedelta(days=days_old))
        order.refresh_from_db()
        return order

    @patch("orders.expired_orders_cleanup_service.EmailMessage.send", return_value=1)
    def test_cleanup_groups_by_normalized_location_and_deletes_after_email(self, mocked_send):
        self._create_expired_order(self.location_mumbai, days_old=45)
        self._create_expired_order(self.location_hyderabad, days_old=40)

        result = cleanup_expired_orders_and_email()

        self.assertEqual(result["attachments_sent"], 2)
        self.assertEqual(Order.objects.count(), 0)
        mocked_send.assert_called_once()

    @patch("orders.expired_orders_cleanup_service.EmailMessage.send", side_effect=Exception("SMTP failure"))
    def test_cleanup_does_not_delete_if_email_fails(self, mocked_send):
        self._create_expired_order(self.location_mumbai, days_old=35)

        with self.assertRaises(Exception):
            cleanup_expired_orders_and_email()

        self.assertEqual(Order.objects.count(), 1)
        mocked_send.assert_called_once()
