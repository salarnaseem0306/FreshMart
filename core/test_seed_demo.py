import io

from django.core.management import call_command
from django.db.models import Sum
from django.test import TestCase

from accounts.models import User
from catalog.models import Category, Product
from inventory.models import StockMovement, Supplier


def counts():
    return {
        "users": User.objects.count(),
        "categories": Category.objects.count(),
        "suppliers": Supplier.objects.count(),
        "products": Product.objects.count(),
        "movements": StockMovement.objects.count(),
    }


class SeedDemoTests(TestCase):
    def seed(self):
        call_command("seed_demo", stdout=io.StringIO())

    def test_running_it_twice_leaves_the_same_row_counts(self):
        self.seed()
        first = counts()
        self.assertEqual(
            first,
            {"users": 3, "categories": 5, "suppliers": 3, "products": 40, "movements": 40},
        )
        self.seed()
        self.assertEqual(counts(), first)

    def test_seeded_stock_equals_its_movements(self):
        self.seed()
        self.seed()
        for product in Product.objects.all():
            total = product.movements.aggregate(total=Sum("change"))["total"] or 0
            self.assertEqual(product.stock_quantity, total, product.sku)

    def test_demo_users_have_the_right_roles_and_password(self):
        self.seed()
        self.assertEqual(User.objects.get(username="manager1").role, User.Role.MANAGER)
        for name in ("cashier1", "cashier2"):
            user = User.objects.get(username=name)
            self.assertEqual(user.role, User.Role.CASHIER)
            self.assertTrue(user.check_password("freshmart123"))