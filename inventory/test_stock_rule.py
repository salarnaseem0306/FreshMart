from decimal import Decimal

from django.db.models import Sum
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import Category, Product
from inventory.models import Supplier


class StockEqualsMovementsTests(TestCase):
    """Rule 3: stock_quantity is always the sum of the product's movements."""

    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user("seq_mgr", password="pw", role=User.Role.MANAGER)
        cls.cashier = User.objects.create_user("seq_cash", password="pw", role=User.Role.CASHIER)
        category = Category.objects.create(name="Seq")
        cls.supplier = Supplier.objects.create(name="Seq Supply")
        cls.a = Product.objects.create(name="A", sku="SEQ-A", category=category, price=Decimal("2.00"))
        cls.b = Product.objects.create(name="B", sku="SEQ-B", category=category, price=Decimal("1.50"))
        cls.c = Product.objects.create(name="C", sku="SEQ-C", category=category, price=Decimal("3.00"))

    def setUp(self):
        self.manager_client = APIClient()
        self.manager_client.force_authenticate(self.manager)
        self.cashier_client = APIClient()
        self.cashier_client.force_authenticate(self.cashier)

    # --- small helpers: every step goes through the real API -------------

    def receive(self, product, quantity):
        response = self.manager_client.post(
            "/api/inventory/receive/",
            {"product": product.pk, "quantity": quantity, "supplier": self.supplier.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    def adjust(self, product, change, expected_status=201):
        response = self.manager_client.post(
            "/api/inventory/adjust/",
            {"product": product.pk, "change": change, "note": "stock count"},
            format="json",
        )
        self.assertEqual(response.status_code, expected_status)

    def new_sale(self, *lines):
        sale_id = self.cashier_client.post("/api/sales/").json()["id"]
        for product, quantity in lines:
            response = self.cashier_client.post(
                f"/api/sales/{sale_id}/items/",
                {"product": product.pk, "quantity": quantity},
                format="json",
            )
            self.assertEqual(response.status_code, 201)
        return sale_id

    def pay(self, sale_id, expected_status=200, **body):
        body.setdefault("payment_method", "card")
        response = self.cashier_client.post(f"/api/sales/{sale_id}/pay/", body, format="json")
        self.assertEqual(response.status_code, expected_status)
        return response

    def refund(self, sale_id):
        response = self.manager_client.post(f"/api/sales/{sale_id}/refund/")
        self.assertEqual(response.status_code, 200)

    def cancel(self, sale_id):
        response = self.cashier_client.post(f"/api/sales/{sale_id}/cancel/")
        self.assertEqual(response.status_code, 200)

    def stock(self, product):
        product.refresh_from_db()
        return product.stock_quantity

    # --- the sequence ----------------------------------------------------

    def test_long_sequence_ends_with_stock_equal_to_the_sum_of_movements(self):
        # 1. Deliveries.                                   A 50, B 30, C 10
        self.receive(self.a, 50)
        self.receive(self.b, 30)
        self.receive(self.c, 10)
        # 2. Sale 1 (A x5, B x2) is paid.                  A 45, B 28
        sale1 = self.new_sale((self.a, 5), (self.b, 2))
        self.pay(sale1)
        # 3. Sale 2 (C x4) is paid.                        C 6
        sale2 = self.new_sale((self.c, 4))
        self.pay(sale2)
        # 4. Sale 3 wants 7 of C but only 6 are left: refused, nothing moves, then cancelled.
        sale3 = self.new_sale((self.c, 7))
        self.pay(sale3, expected_status=400)
        self.assertEqual(self.stock(self.c), 6)
        self.cancel(sale3)
        # 5. Sale 1 is refunded.                           A 50, B 30
        self.refund(sale1)
        # 6. Stock counts: A lost 3, B found 2.            A 47, B 32
        self.adjust(self.a, -3)
        self.adjust(self.b, 2)
        # 7. An adjustment below zero is refused.          C stays 6
        self.adjust(self.c, -100, expected_status=400)
        # 8. Another delivery.                             A 67
        self.receive(self.a, 20)
        # 9. Sale 4 (A x10, B x5, C x2) is paid in cash.   A 57, B 27, C 4
        sale4 = self.new_sale((self.a, 10), (self.b, 5), (self.c, 2))
        response = self.pay(sale4, payment_method="cash", amount_received="100.00")
        self.assertEqual(response.json()["change"], "66.50")
        # 10. Sale 5 (B x1) is paid with too little cash: refused, nothing moves.
        sale5 = self.new_sale((self.b, 1))
        self.pay(sale5, expected_status=400, payment_method="cash", amount_received="0.50")
        self.cancel(sale5)
        # 11. Sale 2 is refunded.                          C 8
        self.refund(sale2)

        # The numbers worked out by hand...
        self.assertEqual(
            [self.stock(self.a), self.stock(self.b), self.stock(self.c)], [57, 27, 8]
        )
        # ...and the rule itself: stock equals the sum of the movements, for every product.
        for product in Product.objects.all():
            total = product.movements.aggregate(total=Sum("change"))["total"] or 0
            self.assertEqual(product.stock_quantity, total, product.name)
            self.assertGreaterEqual(product.stock_quantity, 0)