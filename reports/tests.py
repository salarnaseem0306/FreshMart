from decimal import Decimal
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.models import User
from catalog.models import Category, Product
from inventory.models import StockMovement, Supplier
from inventory.services import change_stock
from sales.models import Sale
from sales.services import add_item, cancel_sale, pay_sale, refund_sale


class ReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user("mgr", password="pw", role=User.Role.MANAGER)
        cls.cashier1 = User.objects.create_user("cash1", password="pw", role=User.Role.CASHIER)
        cls.cashier2 = User.objects.create_user("cash2", password="pw", role=User.Role.CASHIER)
        category = Category.objects.create(name="Test")
        cls.supplier = Supplier.objects.create(name="Acme Supply")
        cls.rice = Product.objects.create(name="Rice", sku="R-1", category=category, price=Decimal("2.00"))
        cls.tea = Product.objects.create(name="Tea", sku="T-1", category=category, price=Decimal("5.00"))
        cls.salt = Product.objects.create(name="Salt", sku="S-1", category=category, price=Decimal("1.00"))
        for product, qty in [(cls.rice, 100), (cls.tea, 100), (cls.salt, 3)]:
            change_stock(product, qty, StockMovement.Reason.PURCHASE, cls.manager, supplier=cls.supplier)

        cash, card = Sale.PaymentMethod.CASH, Sale.PaymentMethod.CARD
        s1 = Sale.objects.create(cashier=cls.cashier1)           # paid, cash, 6.00
        add_item(s1.pk, cls.rice, 3)
        pay_sale(s1.pk, cash, Decimal("10.00"), cls.cashier1)
        s2 = Sale.objects.create(cashier=cls.cashier2)           # paid, card, 10.00
        add_item(s2.pk, cls.tea, 2)
        pay_sale(s2.pk, card, None, cls.cashier2)
        s3 = Sale.objects.create(cashier=cls.cashier1)           # paid, then refunded, 2.00
        add_item(s3.pk, cls.rice, 1)
        pay_sale(s3.pk, card, None, cls.cashier1)
        refund_sale(s3.pk, cls.manager)
        s4 = Sale.objects.create(cashier=cls.cashier1)           # cancelled
        add_item(s4.pk, cls.tea, 1)
        cancel_sale(s4.pk)
        s5 = Sale.objects.create(cashier=cls.cashier1)           # still open
        add_item(s5.pk, cls.rice, 1)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.manager)
        self.today = timezone.localdate().isoformat()

    def test_daily_report_numbers_and_query_count(self):
        with self.assertNumQueries(4):
            response = self.client.get("/api/reports/daily/", {"date": self.today})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Three sales were paid today (one was refunded later the same day); cancelled and open are out.
        self.assertEqual(data["sales_count"], 3)
        self.assertEqual(data["revenue"], "18.00")
        self.assertEqual(data["refunds_count"], 1)
        self.assertEqual(data["refunds_total"], "2.00")
        self.assertEqual(data["net_revenue"], "16.00")
        methods = {row["payment_method"]: row for row in data["by_payment_method"]}
        self.assertEqual(methods["cash"]["revenue"], "6.00")
        self.assertEqual(methods["card"]["revenue"], "12.00")
        self.assertEqual([r["cashier"] for r in data["by_cashier"]], ["cash2", "cash1"])
        self.assertEqual(data["by_cashier"][1]["revenue"], "8.00")

    def test_daily_report_defaults_to_today(self):
        data = self.client.get("/api/reports/daily/").json()
        self.assertEqual(data["date"], self.today)
        self.assertEqual(data["sales_count"], 3)

    def test_daily_report_for_an_empty_day_has_zeros_and_same_query_count(self):
        with self.assertNumQueries(4):
            data = self.client.get("/api/reports/daily/", {"date": "2000-01-01"}).json()
        self.assertEqual(data["sales_count"], 0)
        self.assertEqual(data["revenue"], "0.00")
        self.assertEqual(data["net_revenue"], "0.00")
        self.assertEqual(data["by_payment_method"], [])
        self.assertEqual(data["by_cashier"], [])

    def test_daily_report_rejects_a_bad_date(self):
        response = self.client.get("/api/reports/daily/", {"date": "not-a-date"})
        self.assertEqual(response.status_code, 400)

    def test_top_products_by_revenue_and_by_quantity(self):
        with self.assertNumQueries(2):
            response = self.client.get(
                "/api/reports/top-products/", {"from": self.today, "to": self.today, "limit": 5}
            )
        data = response.json()
        self.assertEqual([r["name"] for r in data["by_revenue"]], ["Tea", "Rice"])
        self.assertEqual(data["by_revenue"][0]["revenue"], "10.00")
        self.assertEqual([r["name"] for r in data["by_quantity"]], ["Rice", "Tea"])
        self.assertEqual(data["by_quantity"][0]["units"], 3)  # the refunded rice is not counted

    def test_top_products_limit_and_empty_dates(self):
        data = self.client.get("/api/reports/top-products/", {"from": "", "to": "", "limit": 1}).json()
        self.assertEqual(len(data["by_revenue"]), 1)
        self.assertEqual(len(data["by_quantity"]), 1)

    def test_top_products_rejects_from_after_to(self):
        response = self.client.get("/api/reports/top-products/", {"from": "2026-12-31", "to": "2026-01-01"})
        self.assertEqual(response.status_code, 400)

    def test_low_stock_lists_only_low_products_with_last_supplier(self):
        with self.assertNumQueries(1):
            response = self.client.get("/api/reports/low-stock/")
        rows = response.json()
        self.assertEqual([r["name"] for r in rows], ["Salt"])
        self.assertEqual(rows[0]["last_supplier"]["name"], "Acme Supply")

    def test_low_stock_uses_the_supplier_of_the_last_purchase(self):
        newer = Supplier.objects.create(name="Beta Supply")
        change_stock(self.salt, 2, StockMovement.Reason.PURCHASE, self.manager, supplier=newer)
        rows = self.client.get("/api/reports/low-stock/").json()
        self.assertEqual(rows[0]["last_supplier"]["name"], "Beta Supply")

class RefundOnALaterDayTests(TestCase):
    """A refund today must not change the numbers of the day the sale was paid."""

    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user("mgr2", password="pw", role=User.Role.MANAGER)
        cls.cashier = User.objects.create_user("cash", password="pw", role=User.Role.CASHIER)
        category = Category.objects.create(name="Test2")
        cls.product = Product.objects.create(
            name="Milk", sku="M-1", category=category, price=Decimal("5.00")
        )
        change_stock(cls.product, 10, StockMovement.Reason.PURCHASE, cls.manager)

    def test_refund_today_does_not_rewrite_yesterday(self):
        client = APIClient()
        client.force_authenticate(self.manager)
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)

        sale = Sale.objects.create(cashier=self.cashier)
        add_item(sale.pk, self.product, 1)
        pay_sale(sale.pk, Sale.PaymentMethod.CARD, None, self.cashier)
        # Pretend the sale was paid yesterday.
        Sale.objects.filter(pk=sale.pk).update(paid_at=timezone.now() - timedelta(days=1))

        before = client.get("/api/reports/daily/", {"date": yesterday.isoformat()}).json()
        refund_sale(sale.pk, self.manager)  # the refund happens today
        after = client.get("/api/reports/daily/", {"date": yesterday.isoformat()}).json()
        today_report = client.get("/api/reports/daily/", {"date": today.isoformat()}).json()

        # Yesterday is history: it must be identical before and after the refund.
        self.assertEqual(after, before)
        self.assertEqual(after["sales_count"], 1)
        self.assertEqual(after["revenue"], "5.00")
        self.assertEqual(after["refunds_count"], 0)
        self.assertEqual(after["net_revenue"], "5.00")
        # Today carries the refund, and only the refund.
        self.assertEqual(today_report["sales_count"], 0)
        self.assertEqual(today_report["revenue"], "0.00")
        self.assertEqual(today_report["refunds_count"], 1)
        self.assertEqual(today_report["refunds_total"], "5.00")
        self.assertEqual(today_report["net_revenue"], "-5.00")
