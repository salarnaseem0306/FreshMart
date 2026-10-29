from decimal import Decimal
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from catalog.models import Category, Product
from inventory.models import StockMovement
from inventory.services import change_stock
from sales.models import Sale
from sales.services import PaymentError, add_item, pay_sale


class PayChecksCashBeforeTouchingStockTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user("po_mgr", password="pw", role=User.Role.MANAGER)
        cls.cashier = User.objects.create_user("po_cash", password="pw", role=User.Role.CASHIER)
        category = Category.objects.create(name="Order")
        cls.rice = Product.objects.create(
            name="Rice", sku="PO-1", category=category, price=Decimal("2.00")
        )
        change_stock(cls.rice, 10, StockMovement.Reason.PURCHASE, cls.manager)

    def short_cash_sale(self):
        sale = Sale.objects.create(cashier=self.cashier)
        add_item(sale.pk, self.rice, 3)  # total 6.00
        return sale

    def test_short_cash_never_locks_products_or_moves_stock(self):
        sale = self.short_cash_sale()
        with patch("sales.services.change_stock") as change_stock_mock:
            with CaptureQueriesContext(connection) as queries:
                with self.assertRaises(PaymentError):
                    pay_sale(sale.pk, Sale.PaymentMethod.CASH, Decimal("1.00"), self.cashier)
        change_stock_mock.assert_not_called()
        product_locks = [
            q["sql"] for q in queries.captured_queries
            if "catalog_product" in q["sql"] and "FOR UPDATE" in q["sql"]
        ]
        self.assertEqual(product_locks, [])

    def test_short_cash_leaves_everything_untouched(self):
        sale = self.short_cash_sale()
        with self.assertRaises(PaymentError):
            pay_sale(sale.pk, Sale.PaymentMethod.CASH, Decimal("1.00"), self.cashier)
        sale.refresh_from_db()
        self.rice.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.OPEN)
        self.assertEqual(self.rice.stock_quantity, 10)
        self.assertEqual(StockMovement.objects.filter(reason=StockMovement.Reason.SALE).count(), 0)

    def test_enough_cash_still_pays_and_gives_change(self):
        sale = self.short_cash_sale()
        paid, change = pay_sale(sale.pk, Sale.PaymentMethod.CASH, Decimal("10.00"), self.cashier)
        self.assertEqual(paid.status, Sale.Status.PAID)
        self.assertEqual(change, Decimal("4.00"))
        self.rice.refresh_from_db()
        self.assertEqual(self.rice.stock_quantity, 7)