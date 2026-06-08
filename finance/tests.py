from decimal import Decimal

from rest_framework.test import APITestCase

from finance.models import Transaction
from inventory.models import Location
from users.models import User


class FinanceApiTests(APITestCase):
    def setUp(self):
        self.location_a = Location.objects.create(name="Finance A")
        self.location_b = Location.objects.create(name="Finance B")
        self.manager_user = User.objects.create_user(
            username="finance-manager",
            password="pass1234",
            role="manager",
            location=self.location_a,
        )
        Transaction.objects.create(
            transaction_type="income",
            amount=Decimal("100.00"),
            payment_method="cash",
            location=self.location_a,
            description="Sale",
        )

    def authenticate(self, username, password="pass1234"):
        self.client.logout()
        self.assertTrue(self.client.login(username=username, password=password))

    def test_location_revenue_blocks_cross_location_access(self):
        self.authenticate("finance-manager")

        response = self.client.get(f"/api/finance/revenue/{self.location_b.id}/")

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["message"], "Permission denied")
