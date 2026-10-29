from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import Category, Product


def rows(response):
    """The rows of a list endpoint, whether or not it is paginated."""
    data = response.json()
    return data["results"] if isinstance(data, dict) else data


class RetrieveProductTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cashier = User.objects.create_user(
            "ret_cash", password="pw", role=User.Role.CASHIER
        )
        category = Category.objects.create(name="Retrieve")
        cls.milk = Product.objects.create(
            name="Milk", sku="RET-1", barcode="8801", category=category, price=Decimal("2.50")
        )
        cls.old_tea = Product.objects.create(
            name="Old Tea", sku="RET-2", barcode="8802", category=category,
            price=Decimal("1.00"), is_active=False,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.cashier)

    def test_staff_can_fetch_one_product_by_id(self):
        response = self.client.get(f"/api/products/{self.milk.pk}/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], self.milk.pk)
        self.assertEqual(data["name"], "Milk")
        self.assertEqual(data["price"], "2.50")
        self.assertEqual(data["category_name"], "Retrieve")
        self.assertTrue(data["is_active"])

    def test_an_inactive_product_can_still_be_fetched_by_id(self):
        # Old receipts and reports still point at it, so it must stay readable.
        response = self.client.get(f"/api/products/{self.old_tea.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_active"])

    def test_an_inactive_product_stays_out_of_the_list_and_the_scanner(self):
        names = [row["name"] for row in rows(self.client.get("/api/products/"))]
        self.assertEqual(names, ["Milk"])
        self.assertEqual(self.client.get("/api/products/barcode/8802/").status_code, 404)

    def test_an_unknown_id_is_404(self):
        self.assertEqual(self.client.get("/api/products/999999/").status_code, 404)

    def test_no_token_is_401(self):
        response = APIClient().get(f"/api/products/{self.milk.pk}/")
        self.assertEqual(response.status_code, 401)