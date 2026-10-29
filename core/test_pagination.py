from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import Category, Product
from inventory.models import Supplier


class EveryListIsPaginatedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user("pag_mgr", password="pw", role=User.Role.MANAGER)
        category = Category.objects.create(name="Pag")
        Product.objects.bulk_create(
            [
                Product(name=f"Item {i:03d}", sku=f"PAG-{i:03d}", category=category,
                        price=Decimal("1.00"))
                for i in range(55)
            ]
        )
        Supplier.objects.create(name="Pag Supply")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def test_product_list_is_paginated(self):
        first = self.client.get("/api/products/").json()
        self.assertIsInstance(first, dict)
        self.assertEqual(first["count"], 55)
        self.assertEqual(len(first["results"]), 50)
        self.assertIsNotNone(first["next"])
        second = self.client.get("/api/products/?page=2").json()
        self.assertEqual(len(second["results"]), 5)
        self.assertIsNone(second["next"])

    def test_category_and_supplier_lists_are_paginated(self):
        for url in ("/api/categories/", "/api/suppliers/"):
            with self.subTest(url=url):
                data = self.client.get(url).json()
                self.assertIsInstance(data, dict)
                self.assertIn("count", data)
                self.assertIn("results", data)

    def test_lists_that_were_already_paginated_still_are(self):
        for url in ("/api/sales/", "/api/inventory/movements/"):
            with self.subTest(url=url):
                data = self.client.get(url).json()
                self.assertIsInstance(data, dict)
                self.assertIn("results", data)