from decimal import Decimal

from django.db import IntegrityError, models, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import Category, Product
from inventory.models import StockMovement
from inventory.services import InsufficientStock, change_stock
from sales.models import Sale, SaleItem


class OverviewRulesTests(TestCase):
    """One test per rule of the Exercise 6 Overview."""

    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user("rule_mgr", password="pw", role=User.Role.MANAGER)
        cls.cashier = User.objects.create_user("rule_cash", password="pw", role=User.Role.CASHIER)
        cls.category = Category.objects.create(name="Rules")

    def setUp(self):
        self.manager_client = APIClient()
        self.manager_client.force_authenticate(self.manager)
        self.cashier_client = APIClient()
        self.cashier_client.force_authenticate(self.cashier)

    def product(self, name, sku, price, stock=0):
        product = Product.objects.create(
            name=name, sku=sku, category=self.category, price=Decimal(price)
        )
        if stock:
            change_stock(product, stock, StockMovement.Reason.PURCHASE, self.manager)
        return product

    def new_sale(self):
        return self.cashier_client.post("/api/sales/").json()["id"]

    def add(self, sale_id, product, quantity):
        return self.cashier_client.post(
            f"/api/sales/{sale_id}/items/",
            {"product": product.pk, "quantity": quantity},
            format="json",
        )

    def stock(self, product):
        product.refresh_from_db()
        return product.stock_quantity

    # Rule: money is a Decimal, never a float -----------------------------

    def test_rule_money_is_decimal_never_float(self):
        for model, field in [
            (Product, "price"), (Sale, "total"), (SaleItem, "unit_price"), (SaleItem, "line_total"),
        ]:
            with self.subTest(model=model.__name__, field=field):
                self.assertIsInstance(model._meta.get_field(field), models.DecimalField)
        dime = self.product("Dime", "R-DIME", "0.10")
        twenty = self.product("Twenty", "R-TWENTY", "0.20")
        sale_id = self.new_sale()
       
        self.assertEqual(self.add(sale_id, dime, 3).json()["total"], "0.30")
        self.assertEqual(self.add(sale_id, twenty, 1).json()["total"], "0.50")

    # Rule: stock can never go below zero ---------------------------------

    def test_rule_stock_never_goes_below_zero(self):
        product = self.product("Rice", "R-RICE", "2.00", stock=2)
        # Layer 1: the service refuses.
        with self.assertRaises(InsufficientStock):
            change_stock(product, -3, StockMovement.Reason.SALE, self.manager)
        self.assertEqual(self.stock(product), 2)
        # Last line of defence: the database itself refuses a negative number.
        with self.assertRaises(IntegrityError), transaction.atomic():
            Product.objects.filter(pk=product.pk).update(stock_quantity=-1)
        self.assertEqual(self.stock(product), 2)

    # Rule: the price is copied into the sale line at sale time -----------

    def test_rule_price_is_copied_at_sale_time(self):
        product = self.product("Milk", "R-MILK", "2.00", stock=10)
        sale_id = self.new_sale()
        self.add(sale_id, product, 2)
        paid = self.cashier_client.post(
            f"/api/sales/{sale_id}/pay/", {"payment_method": "card"}, format="json"
        )
        self.assertEqual(paid.status_code, 200)

        # The shop raises the price afterwards.
        changed = self.manager_client.patch(
            f"/api/products/{product.pk}/", {"price": "5.00"}, format="json"
        )
        self.assertEqual(changed.status_code, 200)

        # The old receipt still shows what the customer really paid.
        receipt = self.cashier_client.get(f"/api/sales/{sale_id}/").json()
        self.assertEqual(receipt["items"][0]["unit_price"], "2.00")
        self.assertEqual(receipt["items"][0]["line_total"], "4.00")
        self.assertEqual(receipt["total"], "4.00")
        new_id = self.new_sale()
        self.assertEqual(self.add(new_id, product, 1).json()["total"], "5.00")

    # Rule: products are soft deleted, never removed ----------------------

    def test_rule_products_are_soft_deleted(self):
        product = self.product("Bread", "R-BREAD", "1.00", stock=5)
        sale_id = self.new_sale()
        self.add(sale_id, product, 1)
        self.cashier_client.post(
            f"/api/sales/{sale_id}/pay/", {"payment_method": "card"}, format="json"
        )

        response = self.manager_client.delete(f"/api/products/{product.pk}/")
        self.assertEqual(response.status_code, 204)

        product.refresh_from_db()
        self.assertFalse(product.is_active)                  # hidden, but the row is kept
        receipt = self.cashier_client.get(f"/api/sales/{sale_id}/").json()
        self.assertEqual(receipt["items"][0]["product_name"], "Bread")   # old sale still reads
        with self.assertRaises(ProtectedError):              # a real delete is blocked
            Product.objects.filter(pk=product.pk).delete()

    # Rule: paying is all or nothing --------------------------------------

    def test_rule_payment_is_all_or_nothing(self):
        plenty = self.product("Plenty", "R-PLENTY", "1.00", stock=10)
        scarce = self.product("Scarce", "R-SCARCE", "1.00", stock=1)
        sale_id = self.new_sale()
        self.add(sale_id, plenty, 2)
        self.add(sale_id, scarce, 3)                         # only 1 in stock
        movements_before = StockMovement.objects.count()

        response = self.cashier_client.post(
            f"/api/sales/{sale_id}/pay/", {"payment_method": "card"}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.stock(plenty), 10)             # the good line took nothing
        self.assertEqual(self.stock(scarce), 1)
        self.assertEqual(StockMovement.objects.count(), movements_before)
        self.assertEqual(Sale.objects.get(pk=sale_id).status, Sale.Status.OPEN)