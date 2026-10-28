from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import Category, Product


def rows(response):
    """The rows of a list endpoint, whether or not it is paginated."""
    data = response.json()
    return data["results"] if isinstance(data, dict) else data


class CatalogApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user(
            "cat_mgr", password="pw", role=User.Role.MANAGER
        )
        cls.cashier = User.objects.create_user(
            "cat_cash", password="pw", role=User.Role.CASHIER
        )
        cls.dairy = Category.objects.create(name="Dairy")
        cls.bakery = Category.objects.create(name="Bakery")
        cls.milk = Product.objects.create(
            name="Fresh Milk 1L", sku="DAI-1", barcode="8901", category=cls.dairy,
            price=Decimal("2.50"), stock_quantity=20, reorder_level=10,
        )
        cls.bread = Product.objects.create(
            name="White Bread", sku="BAK-1", barcode="8902", category=cls.bakery,
            price=Decimal("1.20"), stock_quantity=3, reorder_level=10,
        )

    def setUp(self):
        self.manager_client = APIClient()
        self.manager_client.force_authenticate(self.manager)
        self.cashier_client = APIClient()
        self.cashier_client.force_authenticate(self.cashier)

    def names(self, response):
        return [row["name"] for row in rows(response)]

    # --- create / update -------------------------------------------------

    def test_manager_creates_a_product_and_cannot_set_its_stock(self):
        response = self.manager_client.post(
            "/api/products/",
            {
                "name": "Rice 5kg", "sku": "GRO-1", "barcode": "8903",
                "category": self.dairy.pk, "price": "12.50", "stock_quantity": 999,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["price"], "12.50")      # money stays a decimal string
        self.assertEqual(response.json()["stock_quantity"], 0)   # stock is read only (Rule 3)
        self.assertEqual(Product.objects.get(sku="GRO-1").stock_quantity, 0)

    def test_cashier_cannot_create_a_product(self):
        response = self.cashier_client.post(
            "/api/products/",
            {"name": "X", "sku": "X-1", "category": self.dairy.pk, "price": "1.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Product.objects.filter(sku="X-1").exists())

    def test_price_must_be_a_positive_amount_with_two_decimals(self):
        for index, bad_price in enumerate(["0", "-1", "1.234", "abc"]):
            with self.subTest(price=bad_price):
                response = self.manager_client.post(
                    "/api/products/",
                    {"name": "Bad", "sku": f"BAD-{index}", "category": self.dairy.pk,
                     "price": bad_price},
                    format="json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("price", response.json())

    def test_sku_must_be_unique(self):
        response = self.manager_client.post(
            "/api/products/",
            {"name": "Copy", "sku": "DAI-1", "category": self.dairy.pk, "price": "1.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("sku", response.json())

    def test_an_empty_barcode_means_no_barcode(self):
        for number in (1, 2):
            response = self.manager_client.post(
                "/api/products/",
                {"name": f"Loose {number}", "sku": f"LOOSE-{number}", "barcode": "",
                 "category": self.dairy.pk, "price": "1.00"},
                format="json",
            )
            self.assertEqual(response.status_code, 201)
        self.assertEqual(
            Product.objects.filter(sku__startswith="LOOSE-", barcode__isnull=True).count(), 2
        )

    def test_manager_updates_name_and_price(self):
        response = self.manager_client.patch(
            f"/api/products/{self.milk.pk}/",
            {"name": "Fresh Milk 1L (new)", "price": "2.75"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["price"], "2.75")
        self.milk.refresh_from_db()
        self.assertEqual(self.milk.name, "Fresh Milk 1L (new)")
        self.assertEqual(self.milk.price, Decimal("2.75"))

    def test_stock_cannot_be_changed_through_the_product_api(self):
        response = self.manager_client.patch(
            f"/api/products/{self.milk.pk}/", {"stock_quantity": 500}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.milk.refresh_from_db()
        self.assertEqual(self.milk.stock_quantity, 20)

    # --- search, filters, barcode ---------------------------------------

    def test_search_by_name_and_by_sku(self):
        self.assertEqual(self.names(self.cashier_client.get("/api/products/?search=milk")),
                         ["Fresh Milk 1L"])
        self.assertEqual(self.names(self.cashier_client.get("/api/products/?search=BAK-1")),
                         ["White Bread"])
        self.assertEqual(self.names(self.cashier_client.get("/api/products/?search=nothing")), [])

    def test_filter_by_category(self):
        response = self.cashier_client.get(f"/api/products/?category={self.bakery.pk}")
        self.assertEqual(self.names(response), ["White Bread"])

    def test_low_stock_filter_and_flag(self):
        low = self.cashier_client.get("/api/products/?low_stock=true")
        self.assertEqual(self.names(low), ["White Bread"])
        self.assertTrue(rows(low)[0]["low_stock"])
        fine = self.cashier_client.get("/api/products/?low_stock=false")
        self.assertEqual(self.names(fine), ["Fresh Milk 1L"])

    def test_barcode_lookup(self):
        found = self.cashier_client.get("/api/products/barcode/8901/")
        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.json()["name"], "Fresh Milk 1L")
        self.assertEqual(
            self.cashier_client.get("/api/products/barcode/0000/").status_code, 404
        )

    # --- soft delete (Rule 5) -------------------------------------------

    def test_delete_hides_the_product_but_keeps_the_row(self):
        response = self.manager_client.delete(f"/api/products/{self.bread.pk}/")
        self.assertEqual(response.status_code, 204)
        self.bread.refresh_from_db()                      # the row is still there
        self.assertFalse(self.bread.is_active)
        self.assertNotIn("White Bread", self.names(self.manager_client.get("/api/products/")))
        self.assertEqual(
            self.manager_client.get("/api/products/barcode/8902/").status_code, 404
        )

    # --- categories ------------------------------------------------------

    def test_create_category_and_reject_a_duplicate_name(self):
        created = self.manager_client.post("/api/categories/", {"name": "Snacks"}, format="json")
        self.assertEqual(created.status_code, 201)
        self.assertTrue(Category.objects.filter(name="Snacks").exists())
        duplicate = self.manager_client.post("/api/categories/", {"name": "Dairy"}, format="json")
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("name", duplicate.json())

    def test_rename_category_and_cashier_can_read_the_list(self):
        response = self.manager_client.patch(
            f"/api/categories/{self.bakery.pk}/", {"name": "Bread & Cakes"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        listed = self.cashier_client.get("/api/categories/")
        self.assertEqual(sorted(self.names(listed)), ["Bread & Cakes", "Dairy"])