from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User


class SuperuserRoleTests(TestCase):
    """A superuser made with createsuperuser must be able to use the manager endpoints."""

    def setUp(self):
        self.admin = User.objects.create_superuser("boss", "boss@example.com", "pw12345!")

    def test_create_superuser_makes_a_manager(self):
        self.assertEqual(self.admin.role, User.Role.MANAGER)
        self.assertTrue(self.admin.is_superuser)
        self.assertTrue(self.admin.is_staff)

    def test_an_explicit_role_is_still_respected_for_normal_users(self):
        cashier = User.objects.create_user("till", password="pw", role=User.Role.CASHIER)
        self.assertEqual(cashier.role, User.Role.CASHIER)

    def test_new_superuser_can_open_the_manager_endpoints(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        for url in [
            "/api/reports/daily/",
            "/api/reports/top-products/",
            "/api/reports/low-stock/",
            "/api/sales/",
            "/api/auth/me/",
        ]:
            with self.subTest(url=url):
                self.assertEqual(client.get(url).status_code, 200)
# Create your tests here.
