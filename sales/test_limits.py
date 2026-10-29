from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import Category, Product


class QuantityLimitTests(TestCase):
    """Oversize numbers must give a 400 with a field error, never a 500."""

    @classmethod
    def setUpTestData(cls):
        cls.cashier = User.objects.create_user(
            "limit_cashier", password="pw", role=User.Role.CASHIER
        )
        category = Category.objects.create(name="Limits")
        cls.cheap = Product.objects.create(
            name="Rice", sku="LIM-1", category=category, price=Decimal("2.50")
        )
        # The most expensive price a money column (max_digits=10) can hold.
        cls.pricey = Product.objects.create(
            name="Gold bar", sku="LIM-2", category=category, price=Decimal("99999999.99")
        )
        cls.pricey2 = Product.objects.create(
            name="Diamond", sku="LIM-3", category=category, price=Decimal("99999999.99")
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.cashier)
        self.sale_id = self.client.post("/api/sales/").json()["id"]

    def add(self, product, quantity):
        return self.client.post(
            f"/api/sales/{self.sale_id}/items/",
            {"product": product.pk, "quantity": quantity},
            format="json",
        )

    def receipt(self):
        return self.client.get(f"/api/sales/{self.sale_id}/").json()

    def test_huge_quantity_is_a_400_with_a_field_error(self):
        response = self.add(self.cheap, 100_000_000)
        self.assertEqual(response.status_code, 400)
        self.assertIn("quantity", response.json())

    def test_quantity_beyond_the_integer_range_is_a_400(self):
        response = self.add(self.cheap, 10**12)
        self.assertEqual(response.status_code, 400)
        self.assertIn("quantity", response.json())

    def test_quantity_exactly_at_the_limit_is_accepted(self):
        response = self.add(self.cheap, 999)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["total"], "2497.50")

    def test_adding_to_an_existing_line_respects_the_limit(self):
        self.assertEqual(self.add(self.cheap, 900).status_code, 201)
        response = self.add(self.cheap, 200)          # 900 + 200 = 1100
        self.assertEqual(response.status_code, 400)
        self.assertIn("quantity", response.json())
        self.assertEqual(self.receipt()["items"][0]["quantity"], 900)  # unchanged
        self.assertEqual(self.add(self.cheap, 99).status_code, 201)    # 999 is fine

    def test_changing_a_line_above_the_limit_is_a_400(self):
        item_id = self.add(self.cheap, 1).json()["items"][0]["id"]
        response = self.client.patch(
            f"/api/sales/{self.sale_id}/items/{item_id}/", {"quantity": 1000}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("quantity", response.json())

    def test_a_line_total_too_big_for_the_column_is_a_400(self):
        response = self.add(self.pricey, 2)           # 2 x 99,999,999.99 does not fit
        self.assertEqual(response.status_code, 400)
        self.assertIn("quantity", response.json())

    def test_a_sale_total_too_big_for_the_column_is_a_400(self):
        self.assertEqual(self.add(self.pricey, 1).status_code, 201)   # a line may be the max
        response = self.add(self.pricey2, 1)          # the sale total would overflow
        self.assertEqual(response.status_code, 400)
        receipt = self.receipt()
        self.assertEqual(len(receipt["items"]), 1)    # the second line was not kept
        self.assertEqual(receipt["total"], "99999999.99")
    