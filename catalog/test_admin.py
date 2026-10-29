from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from catalog.models import Category, Product


class ProductAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser("adm", password="pw")
        category = Category.objects.create(name="Admin")
        cls.product = Product.objects.create(
            name="Rice", sku="ADM-1", category=category, price=Decimal("2.00")
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_delete_page_is_forbidden(self):
        url = reverse("admin:catalog_product_delete", args=[self.product.pk])
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_delete_post_is_forbidden_and_product_survives(self):
        url = reverse("admin:catalog_product_delete", args=[self.product.pk])
        self.assertEqual(self.client.post(url, {"post": "yes"}).status_code, 403)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_bulk_delete_is_not_offered(self):
        response = self.client.get(reverse("admin:catalog_product_changelist"))
        self.assertNotContains(response, 'value="delete_selected"')
        self.assertContains(response, 'value="mark_inactive"')

    def test_mark_inactive_action_keeps_the_product(self):
        response = self.client.post(
            reverse("admin:catalog_product_changelist"),
            {"action": "mark_inactive", "_selected_action": [self.product.pk]},
        )
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)