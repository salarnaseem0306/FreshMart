import threading
from decimal import Decimal

from django.db import connection
from django.db.models import Sum
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import Category, Product
from inventory.models import StockMovement
from inventory.services import change_stock

from .models import Sale
from .services import (
    InsufficientStockForSale,
    PaymentError,
    add_item,
    pay_sale,
    refund_sale,
)


def make_user(username, role):
    return User.objects.create_user(username=username, password="pw", role=role)


def make_product(manager, name, sku, price="2.00", stock=0):
    category, _ = Category.objects.get_or_create(name="Test")
    product = Product.objects.create(
        name=name, sku=sku, category=category, price=Decimal(price)
    )
    if stock:
        # Opening stock goes through the one allowed door, so Rule 3 holds.
        change_stock(product, stock, StockMovement.Reason.PURCHASE, manager)
    return product


def stock_of(product):
    product.refresh_from_db()
    return product.stock_quantity


# --- Proof 1: paying is all or nothing -------------------------------------


class PayIsAllOrNothingTests(TestCase):
    def setUp(self):
        self.manager = make_user("mgr", User.Role.MANAGER)
        self.cashier = make_user("cash", User.Role.CASHIER)
        self.a = make_product(self.manager, "A", "A-1", stock=5)
        self.b = make_product(self.manager, "B", "B-1", stock=5)
        self.c = make_product(self.manager, "C", "C-1", stock=1)
        self.client = APIClient()
        self.client.force_authenticate(self.cashier)

    def test_short_third_line_changes_nothing(self):
        sale = Sale.objects.create(cashier=self.cashier)
        add_item(sale.pk, self.a, 2)
        add_item(sale.pk, self.b, 2)
        add_item(sale.pk, self.c, 3)  # only 1 in stock: the third line is short
        movements_before = StockMovement.objects.count()

        response = self.client.post(
            f"/api/sales/{sale.pk}/pay/", {"payment_method": "card"}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual([s["product"] for s in response.data["shortages"]], [self.c.pk])
        self.assertEqual(response.data["shortages"][0]["available"], 1)
        self.assertEqual(stock_of(self.a), 5)
        self.assertEqual(stock_of(self.b), 5)
        self.assertEqual(stock_of(self.c), 1)
        self.assertEqual(StockMovement.objects.count(), movements_before)
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.OPEN)

    def test_failure_after_stock_moved_rolls_everything_back(self):
        # Stock is taken first; the cash check fails afterwards. The transaction
        # must undo the stock changes that already happened.
        sale = Sale.objects.create(cashier=self.cashier)
        add_item(sale.pk, self.a, 2)
        add_item(sale.pk, self.b, 2)  # total 8.00
        movements_before = StockMovement.objects.count()

        with self.assertRaises(PaymentError):
            pay_sale(sale.pk, Sale.PaymentMethod.CASH, Decimal("5.00"), self.cashier)

        self.assertEqual(stock_of(self.a), 5)
        self.assertEqual(stock_of(self.b), 5)
        self.assertEqual(StockMovement.objects.count(), movements_before)
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.OPEN)


# --- Proof 2: two tills, one carton left -----------------------------------


class TwoTillsLastCartonTests(TransactionTestCase):
    def setUp(self):
        self.manager = make_user("mgr", User.Role.MANAGER)
        self.cashier1 = make_user("cash1", User.Role.CASHIER)
        self.cashier2 = make_user("cash2", User.Role.CASHIER)
        self.milk = make_product(self.manager, "Milk", "MILK-1", price="2.50", stock=1)
        self.sale1 = Sale.objects.create(cashier=self.cashier1)
        self.sale2 = Sale.objects.create(cashier=self.cashier2)
        add_item(self.sale1.pk, self.milk, 1)
        add_item(self.sale2.pk, self.milk, 1)

    def test_exactly_one_till_gets_the_last_carton(self):
        barrier = threading.Barrier(2)
        results = {}

        def till(sale, cashier):
            try:
                barrier.wait(timeout=10)  # both tills press "pay" together
                pay_sale(sale.pk, Sale.PaymentMethod.CARD, None, cashier)
                results[sale.pk] = "paid"
            except InsufficientStockForSale:
                results[sale.pk] = "short"
            except Exception as exc:  # anything else is a bug
                results[sale.pk] = f"error: {exc!r}"
            finally:
                connection.close()  # each thread has its own connection

        threads = [
            threading.Thread(target=till, args=(self.sale1, self.cashier1)),
            threading.Thread(target=till, args=(self.sale2, self.cashier2)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertCountEqual(results.values(), ["paid", "short"])
        self.assertEqual(stock_of(self.milk), 0)
        self.assertEqual(Sale.objects.filter(status=Sale.Status.PAID).count(), 1)
        self.assertEqual(
            StockMovement.objects.filter(reason=StockMovement.Reason.SALE).count(), 1
        )


class NaiveOversellDemo(TransactionTestCase):
    """Why locking exists: the classic 'read, check, then write' race.

    This is NOT our production code. It is the naive version, to show the bug
    that pay_sale() is built to prevent: both tills sell the same last carton.
    """

    def test_naive_check_then_write_sells_the_last_carton_twice(self):
        manager = make_user("mgr", User.Role.MANAGER)
        milk = make_product(manager, "Milk", "MILK-1", stock=1)
        barrier = threading.Barrier(2)
        sold = []

        def naive_till():
            try:
                product = Product.objects.get(pk=milk.pk)  # 1. read: stock is 1
                barrier.wait(timeout=10)                   # both have now read 1
                if product.stock_quantity >= 1:            # 2. check (on stale data)
                    Product.objects.filter(pk=milk.pk).update(
                        stock_quantity=product.stock_quantity - 1   # 3. write 0
                    )
                    sold.append(True)
            finally:
                connection.close()

        threads = [threading.Thread(target=naive_till) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(sold), 2)  # two cartons "sold"...
        self.assertEqual(stock_of(milk), 0)  # ...but only one ever existed


# --- Proof 3: refunds ------------------------------------------------------


class RefundTests(TestCase):
    def setUp(self):
        self.manager = make_user("mgr", User.Role.MANAGER)
        self.cashier = make_user("cash", User.Role.CASHIER)
        self.milk = make_product(self.manager, "Milk", "MILK-1", price="2.50", stock=10)
        self.sale = Sale.objects.create(cashier=self.cashier)
        add_item(self.sale.pk, self.milk, 3)
        self.manager_client = APIClient()
        self.manager_client.force_authenticate(self.manager)
        self.cashier_client = APIClient()
        self.cashier_client.force_authenticate(self.cashier)

    def _pay(self):
        pay_sale(self.sale.pk, Sale.PaymentMethod.CARD, None, self.cashier)

    def test_refund_puts_stock_back_through_movements(self):
        self._pay()
        self.assertEqual(stock_of(self.milk), 7)

        response = self.manager_client.post(f"/api/sales/{self.sale.pk}/refund/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "refunded")
        self.assertEqual(stock_of(self.milk), 10)
        movements = list(
            StockMovement.objects.filter(sale=self.sale)
            .order_by("id")
            .values_list("reason", "change")
        )
        self.assertEqual(movements, [("sale", -3), ("refund", 3)])
        # Rule 3: stock equals the sum of its movements.
        total = self.milk.movements.aggregate(total=Sum("change"))["total"]
        self.assertEqual(total, stock_of(self.milk))

    def test_refunding_twice_returns_409(self):
        self._pay()
        refund_sale(self.sale.pk, self.manager)
        response = self.manager_client.post(f"/api/sales/{self.sale.pk}/refund/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(stock_of(self.milk), 10)  # not put back a second time

    def test_open_sale_cannot_be_refunded(self):
        response = self.manager_client.post(f"/api/sales/{self.sale.pk}/refund/")
        self.assertEqual(response.status_code, 409)

    def test_cashier_cannot_refund(self):
        self._pay()
        response = self.cashier_client.post(f"/api/sales/{self.sale.pk}/refund/")
        self.assertEqual(response.status_code, 403)