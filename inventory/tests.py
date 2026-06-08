from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers
from rest_framework.test import APITestCase

from inventory.models import Category, Location, Product, ProductVariant, Stock, StockEntry
from inventory.serializers import CreateProductSerializer
from users.models import User


class InventoryApiTests(APITestCase):
    def setUp(self):
        self.location_a = Location.objects.create(name="Location A")
        self.location_b = Location.objects.create(name="Location B")
        self.admin_user = User.objects.create_user(
            username="admin",
            password="pass1234",
            role="admin",
        )
        self.manager_user = User.objects.create_user(
            username="manager",
            password="pass1234",
            role="manager",
            location=self.location_a,
        )
        self.product = Product.objects.create(
            name="Apple Juice",
            price=Decimal("10.00"),
            location=self.location_a,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            location=self.location_a,
            name="Bottle 500ml",
            sku="AJ-500",
            price=Decimal("10.00"),
        )
        Stock.objects.create(
            product=self.product,
            variant=self.variant,
            location=self.location_a,
            quantity=5,
            expiry_date=str(timezone.localdate() + timedelta(days=30)),
        )

    def authenticate(self, username, password="pass1234"):
        self.client.logout()
        self.assertTrue(self.client.login(username=username, password=password))

    def test_create_product_requires_authentication(self):
        response = self.client.post(
            "/api/inventory/create-product/",
            {"name": "Orange Juice", "price": "12.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertEqual(payload["message"], "Authentication failed")
        self.assertEqual(payload["errors"][0]["field"], "token")

    def test_products_api_rejects_invalid_jwt_with_standardized_error(self):
        response = self.client.get(
            "/api/inventory/products/",
            HTTP_AUTHORIZATION="Bearer invalid-token",
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["message"], "Authentication failed")
        self.assertEqual(response.data["errors"][0]["field"], "token")

    def test_create_product_rejects_invalid_name(self):
        self.authenticate("admin")

        response = self.client.post(
            "/api/inventory/create-product/",
            {"name": "!!!", "price": "12.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["message"], "Validation failed")
        self.assertTrue(any(error["field"] == "name" for error in response.data["errors"]))

    def test_create_product_allows_admin_without_location(self):
        self.authenticate("admin")

        response = self.client.post(
            "/api/inventory/create-product/",
            {"name": "Orange Juice", "category": "Juice", "unit": "Bottle", "is_active": True},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["success"])
        created = Product.objects.get(id=response.data["data"]["id"])
        self.assertEqual(created.category, "Juice")
        self.assertEqual(created.category_ref.name, "Juice")
        self.assertEqual(created.unit, "Bottle")
        self.assertTrue(created.is_active)

    def test_create_product_defaults_to_uncategorized_category(self):
        self.authenticate("admin")

        response = self.client.post(
            "/api/inventory/create-product/",
            {"name": "Plain Water", "price": "8.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        created = Product.objects.get(id=response.data["data"]["id"])
        self.assertEqual(created.category, "Uncategorized")
        self.assertEqual(created.category_ref.name, "Uncategorized")

    def test_create_product_accepts_existing_category_id(self):
        self.authenticate("admin")
        category = Category.objects.create(name="Snacks")

        response = self.client.post(
            "/api/inventory/create-product/",
            {
                "name": "Nachos",
                "price": "18.00",
                "category_id": category.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        created = Product.objects.get(id=response.data["data"]["id"])
        self.assertEqual(created.category_ref, category)
        self.assertEqual(created.category, "Snacks")

    def test_create_product_supports_discount_fields(self):
        self.authenticate("admin")

        response = self.client.post(
            "/api/inventory/create-product/",
            {
                "name": "Discounted Juice",
                "discount_type": "percentage",
                "discount_value": "12.50",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        created = Product.objects.get(id=response.data["data"]["id"])
        self.assertEqual(created.discount_type, "percentage")
        self.assertEqual(str(created.discount_value), "12.50")

    def test_create_product_serializer_without_request_context_returns_validation_error(self):
        serializer = CreateProductSerializer(
            data={"name": "Orange Juice", "price": "12.00"}
        )

        with self.assertRaises(serializers.ValidationError) as exc:
            serializer.is_valid(raise_exception=True)

        self.assertEqual(
            exc.exception.detail["non_field_errors"][0],
            "Request context missing.",
        )

    def test_add_stock_ignores_frontend_location_for_manager(self):
        self.authenticate("manager")

        response = self.client.post(
            "/api/inventory/add-stock/",
            {
                "variant_id": self.variant.id,
                "quantity": 5,
                "expiry_date": str(timezone.localdate() + timedelta(days=10)),
                "location_id": self.location_b.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertTrue(
            Stock.objects.filter(
                product=self.product,
                variant=self.variant,
                location=self.location_a,
                quantity=5,
                expiry_date=str(timezone.localdate() + timedelta(days=10)),
            ).exists()
        )
        self.assertFalse(
            Stock.objects.filter(
                product=self.product,
                variant=self.variant,
                location=self.location_b,
            ).exists()
        )

    def test_worker_cannot_create_product(self):
        worker = User.objects.create_user(
            username="worker",
            password="pass1234",
            role="worker",
            location=self.location_a,
        )
        self.client.force_login(worker)

        response = self.client.post(
            "/api/inventory/create-product/",
            {"name": "Worker Product"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["message"], "Validation failed")

    def test_worker_cannot_create_product_variant(self):
        worker = User.objects.create_user(
            username="worker-variant",
            password="pass1234",
            role="worker",
            location=self.location_a,
        )
        self.client.force_login(worker)

        response = self.client.post(
            "/api/inventory/create-product-variant/",
            {
                "product_id": self.product.id,
                "name": "Worker Variant",
                "sku": "WV-1",
                "price": "15.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["message"], "Validation failed")

    def test_create_product_variant_generates_barcode(self):
        self.authenticate("admin")

        response = self.client.post(
            "/api/inventory/create-product-variant/",
            {
                "product_id": self.product.id,
                "location_id": self.location_a.id,
                "name": "Bottle 1L",
                "sku": "AJ-1000",
                "price": "20.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        variant = ProductVariant.objects.get(id=response.data["data"]["id"])
        self.assertTrue(variant.barcode)
        self.assertEqual(variant.location, self.location_a)

    def test_create_stock_entry_updates_inventory(self):
        self.authenticate("manager")

        response = self.client.post(
            "/api/inventory/create-stock-entry/",
            {
                "variant_id": self.variant.id,
                "location_id": self.location_b.id,
                "quantity": 7,
                "supplier_name": "Supplier One",
                "supplier_phone": "9876543210",
                "received_date": str(timezone.localdate()),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(StockEntry.objects.count(), 1)
        self.assertTrue(
            Stock.objects.filter(
                product=self.product,
                variant=self.variant,
                location=self.location_a,
                expiry_date=None,
                quantity=7,
            ).exists()
        )

    def test_delete_product_returns_standard_success_response(self):
        self.authenticate("admin")

        response = self.client.delete(f"/api/inventory/products/{self.product.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["message"], "Product deleted successfully")
        self.assertIsNone(response.data["data"])
        self.assertFalse(Product.objects.filter(id=self.product.id).exists())

    def test_put_product_updates_product_for_admin(self):
        self.authenticate("admin")

        response = self.client.put(
            f"/api/inventory/products/{self.product.id}/",
            {"name": "Apple Juice Premium", "price": "12.50"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["message"], "Product updated successfully")
        self.assertEqual(response.data["data"]["name"], "Apple Juice Premium")
        self.assertIn("category_id", response.data["data"])
        self.assertEqual(str(response.data["data"]["price"]), "12.50")

    def test_patch_product_updates_only_provided_fields_for_manager(self):
        self.authenticate("manager")

        response = self.client.patch(
            f"/api/inventory/products/{self.product.id}/",
            {"price": "11.25"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["message"], "Product updated successfully")
        self.assertEqual(response.data["data"]["name"], "Apple Juice")
        self.assertEqual(str(response.data["data"]["price"]), "11.25")

    def test_update_product_returns_404_for_invalid_id(self):
        self.authenticate("admin")

        response = self.client.put(
            "/api/inventory/products/99999/",
            {"name": "Ghost Product", "price": "15.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["message"], "Resource not found")

    def test_patch_variant_updates_variant_for_admin(self):
        self.authenticate("admin")

        response = self.client.patch(
            f"/api/inventory/variants/{self.variant.id}/",
            {"name": "Bottle 750ml", "price": "14.50", "is_active": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["message"], "Variant updated successfully")
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.name, "Bottle 750ml")
        self.assertEqual(str(self.variant.price), "14.50")
        self.assertFalse(self.variant.is_active)

    def test_delete_category_with_products_returns_validation_error(self):
        self.authenticate("admin")
        category_id = self.product.category_ref_id

        response = self.client.delete(f"/api/inventory/categories/{category_id}/")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["message"], "Validation failed")
