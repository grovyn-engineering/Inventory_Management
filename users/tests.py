from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from finance.models import Transaction
from inventory.models import Location, Product, ProductVariant, Stock
from notifications.models import Alert
from orders.models import Order


User = get_user_model()


class RoleAccessTests(TestCase):
    def setUp(self):
        self.location_a = Location.objects.create(name="Hyderabad")
        self.location_b = Location.objects.create(name="Bengaluru")

        self.manager = User.objects.create_user(
            username="manager",
            password="pass1234",
            role="manager",
            phone_number="9876543210",
            location=self.location_a,
        )
        self.worker = User.objects.create_user(
            username="worker",
            password="pass1234",
            role="worker",
            phone_number="9876543211",
            location=self.location_a,
        )
        self.admin = User.objects.create_user(
            username="admin",
            password="pass1234",
            role="admin",
            phone_number="9876543212",
            is_staff=True,
            is_superuser=True,
        )

        self.product_a = Product.objects.create(name="Item A", price=100, location=self.location_a)
        self.product_b = Product.objects.create(name="Item B", price=200, location=self.location_b)
        self.variant_a = ProductVariant.objects.create(
            product=self.product_a,
            name="Small",
            sku="ITEM-A-S",
            price=100,
        )
        self.variant_b = ProductVariant.objects.create(
            product=self.product_b,
            name="Large",
            sku="ITEM-B-L",
            price=200,
        )
        Stock.objects.create(
            product=self.product_a,
            variant=self.variant_a,
            location=self.location_a,
            quantity=10,
            expiry_date=date(2026, 5, 1),
        )
        Stock.objects.create(
            product=self.product_b,
            variant=self.variant_b,
            location=self.location_b,
            quantity=20,
            expiry_date=date(2026, 5, 1),
        )

        self.order_a = Order.objects.create(
            location=self.location_a,
            status="completed",
            total_amount=300,
            payment_method="cash",
        )
        self.order_b = Order.objects.create(
            location=self.location_b,
            status="completed",
            total_amount=700,
            payment_method="cash",
        )

        Transaction.objects.create(
            transaction_type="income",
            amount=300,
            payment_method="cash",
            order=self.order_a,
            location=self.location_a,
            description="Location A sale",
        )
        Transaction.objects.create(
            transaction_type="income",
            amount=700,
            payment_method="cash",
            order=self.order_b,
            location=self.location_b,
            description="Location B sale",
        )
        Alert.objects.create(
            user=self.manager,
            alert_type="low_stock",
            message="Manager alert",
            location=self.location_a,
        )
        Alert.objects.create(
            user=self.admin,
            alert_type="payment",
            message="Admin alert",
            location=self.location_b,
        )

    def test_logout_redirects_to_login_and_clears_session(self):
        self.client.force_login(self.manager)

        response = self.client.post(reverse("logout"), follow=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/login")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_manager_products_page_shows_only_location_products(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse("inventory_pages:products"))

        self.assertEqual(response.status_code, 200)
        products = list(response.context["products"])
        self.assertEqual(products, [self.product_a])

    def test_manager_products_api_returns_only_location_products(self):
        self.client.force_login(self.manager)

        response = self.client.get("/api/inventory/products/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual([item["id"] for item in payload], [self.product_a.id])

    def test_manager_revenue_api_blocks_other_location_id(self):
        self.client.force_login(self.manager)

        response = self.client.get(f"/api/finance/revenue/{self.location_b.id}/")

        self.assertEqual(response.status_code, 403)

    def test_worker_cannot_open_finance_dashboard(self):
        self.client.force_login(self.worker)

        response = self.client.get(reverse("finance_pages:dashboard"), follow=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("dashboard_worker"))

    def test_manager_sidebar_renders_console_sections(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse("dashboard_manager"))

        self.assertContains(response, "Product")
        self.assertContains(response, "Product Variant")
        self.assertContains(response, "Add Stock")
        self.assertContains(response, "Stock Entry")
        self.assertContains(response, "Location")

    def test_worker_sidebar_shows_inventory_console_without_operations(self):
        self.client.force_login(self.worker)

        response = self.client.get(reverse("dashboard_worker"))

        self.assertContains(response, "Product")
        self.assertContains(response, "Product Variant")
        self.assertContains(response, "Add Stock")
        self.assertContains(response, "Stock Entry")
        self.assertContains(response, "Location")

    def test_manager_notifications_dashboard_is_location_scoped(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse("notifications_pages:dashboard"))

        self.assertEqual(response.status_code, 200)
        alerts = list(response.context["alerts"])
        self.assertTrue(all(alert.location == self.location_a for alert in alerts))
        self.assertTrue(any(alert.message == "Manager alert" for alert in alerts))

    def test_admin_can_create_user_with_phone_number(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            "/api/users/create/",
            {
                "name": "Store Manager",
                "email": "manager2@example.com",
                "phone_number": "9876543213",
                "role": "manager",
                "location_id": self.location_a.id,
                "password": "pass1234",
                "confirm_password": "pass1234",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        created_user = User.objects.get(id=response.json()["data"]["user_id"])
        self.assertEqual(created_user.first_name, "Store Manager")
        self.assertEqual(created_user.email, "manager2@example.com")
        self.assertEqual(created_user.phone_number, "9876543213")
        self.assertEqual(created_user.username, "manager2@example.com")

    def test_create_user_rejects_duplicate_phone_number(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            "/api/users/create/",
            {
                "name": "Duplicate Phone",
                "email": "duplicate@example.com",
                "phone_number": "9876543210",
                "role": "manager",
                "location_id": self.location_a.id,
                "password": "pass1234",
                "confirm_password": "pass1234",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_create_user_rejects_password_mismatch(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            "/api/users/create/",
            {
                "name": "Mismatch User",
                "email": "mismatch@example.com",
                "phone_number": "9876543214",
                "role": "worker",
                "location_id": self.location_a.id,
                "password": "pass1234",
                "confirm_password": "wrongpass",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
