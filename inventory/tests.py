from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import Category, Product
from inventory.models import StockMovement, Supplier
from inventory.services import change_stock


def rows(response):
    data = response.json()
    return data["results"] if isinstance(data, dict) else data


class InventoryApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user(
            "inv_mgr", password="pw", role=User.Role.MANAGER
        )
        category = Category.objects.create(name="Inv")
        cls.supplier = Supplier.objects.create(name="Acme Supply")
        cls.product = Product.objects.create(
            name="Rice", sku="INV-1", category=category, price=Decimal("2.00")
        )
        cls.inactive = Product.objects.create(
            name="Old stock", sku="INV-2", category=category, price=Decimal("1.00"),
            is_active=False,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def stock(self):
        self.product.refresh_from_db()
        return self.product.stock_quantity

    def receive(self, **override):
        payload = {"product": self.product.pk, "quantity": 10,
                   "supplier": self.supplier.pk, "note": "Delivery"}
        payload.update(override)
        return self.client.post("/api/inventory/receive/", payload, format="json")

    def adjust(self, **override):
        payload = {"product": self.product.pk, "change": -1, "note": "Count"}
        payload.update(override)
        return self.client.post("/api/inventory/adjust/", payload, format="json")

    def put_in_stock(self, quantity):
        change_stock(self.product, quantity, StockMovement.Reason.PURCHASE,
                     self.manager, supplier=self.supplier)

    # --- receive ---------------------------------------------------------

    def test_receive_adds_stock_and_writes_a_purchase_movement(self):
        response = self.receive(quantity=10, note="Delivery 1")
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["reason"], "purchase")
        self.assertEqual(data["change"], 10)
        self.assertEqual(data["supplier_name"], "Acme Supply")
        self.assertEqual(data["created_by"], "inv_mgr")
        self.assertEqual(self.stock(), 10)
        self.assertEqual(StockMovement.objects.filter(product=self.product).count(), 1)

    def test_receive_rejects_bad_input_and_changes_nothing(self):
        cases = [
            ("zero quantity", {"quantity": 0}, "quantity"),
            ("negative quantity", {"quantity": -5}, "quantity"),
            ("unknown product", {"product": 999999}, "product"),
            ("inactive product", {"product": self.inactive.pk}, "product"),
            ("unknown supplier", {"supplier": 999999}, "supplier"),
        ]
        for label, override, field in cases:
            with self.subTest(label):
                response = self.receive(**override)
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json())
        self.assertEqual(self.stock(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)

    # --- adjust ----------------------------------------------------------

    def test_adjust_changes_stock_both_ways_and_records_the_reason(self):
        self.put_in_stock(10)
        down = self.adjust(change=-3, note="Broken jars")
        self.assertEqual(down.status_code, 201)
        self.assertEqual(down.json()["reason"], "adjustment")
        self.assertEqual(down.json()["change"], -3)
        self.assertEqual(self.stock(), 7)
        up = self.adjust(change=2, note="Found behind the shelf")
        self.assertEqual(up.status_code, 201)
        self.assertEqual(self.stock(), 9)

    def test_adjusting_below_zero_is_a_400_and_changes_nothing(self):
        self.put_in_stock(5)
        movements_before = StockMovement.objects.count()
        response = self.adjust(change=-6, note="Too much")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Not enough stock", response.json()["detail"])
        self.assertEqual(self.stock(), 5)
        self.assertEqual(StockMovement.objects.count(), movements_before)

    def test_adjust_needs_a_note_and_a_non_zero_change(self):
        self.put_in_stock(5)
        zero = self.adjust(change=0)
        self.assertEqual(zero.status_code, 400)
        self.assertIn("change", zero.json())
        no_note = self.client.post(
            "/api/inventory/adjust/", {"product": self.product.pk, "change": 1}, format="json"
        )
        self.assertEqual(no_note.status_code, 400)
        self.assertIn("note", no_note.json())
        blank_note = self.adjust(change=1, note="")
        self.assertEqual(blank_note.status_code, 400)
        self.assertEqual(self.stock(), 5)

    # --- history and suppliers -------------------------------------------

    def test_movement_history_is_paginated_and_newest_first(self):
        self.put_in_stock(10)
        self.adjust(change=-2, note="Spoiled")
        response = self.client.get("/api/inventory/movements/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 2)
        self.assertEqual([m["reason"] for m in data["results"]], ["adjustment", "purchase"])

    def test_suppliers_can_be_created_updated_and_listed(self):
        created = self.client.post(
            "/api/suppliers/",
            {"name": "Beta Foods", "phone": "0300-1", "email": "beta@example.com"},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        supplier_id = created.json()["id"]
        patched = self.client.patch(
            f"/api/suppliers/{supplier_id}/", {"phone": "0300-2"}, format="json"
        )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json()["phone"], "0300-2")
        names = [row["name"] for row in rows(self.client.get("/api/suppliers/"))]
        self.assertIn("Beta Foods", names)
        bad_email = self.client.post(
            "/api/suppliers/", {"name": "Bad", "email": "not-an-email"}, format="json"
        )
        self.assertEqual(bad_email.status_code, 400)
        self.assertIn("email", bad_email.json())
        blank_name = self.client.post("/api/suppliers/", {"name": ""}, format="json")
        self.assertEqual(blank_name.status_code, 400)
        self.assertIn("name", blank_name.json())