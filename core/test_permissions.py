from django.test import TestCase
from django.urls import get_resolver, resolve
from rest_framework.test import APIClient

from accounts.models import User

EVERYONE = {"anonymous", "cashier", "manager"}
STAFF = {"cashier", "manager"}
MANAGER_ONLY = {"manager"}

# (method, url, who may call it).
# The ids in the URLs do not have to exist: DRF checks permissions before it looks
# anything up. A role that is not allowed gets 403 (no token at all: 401); an allowed
# role gets anything except 401/403 (200, 400 or 404 all mean "permission passed").
ENDPOINTS = [
    # open
    ("get", "/api/health/", EVERYONE),
    ("post", "/api/auth/login/", EVERYONE),
    ("post", "/api/auth/refresh/", EVERYONE),
    # accounts
    ("get", "/api/auth/me/", STAFF),
    # catalog: staff may read, only managers may change
    ("get", "/api/categories/", STAFF),
    ("post", "/api/categories/", MANAGER_ONLY),
    ("patch", "/api/categories/1/", MANAGER_ONLY),
    ("get", "/api/products/", STAFF),
    ("get", "/api/products/barcode/123/", STAFF),
    ("post", "/api/products/", MANAGER_ONLY),
    ("patch", "/api/products/1/", MANAGER_ONLY),
    ("delete", "/api/products/1/", MANAGER_ONLY),
    # inventory: managers only
    ("get", "/api/suppliers/", MANAGER_ONLY),
    ("post", "/api/suppliers/", MANAGER_ONLY),
    ("patch", "/api/suppliers/1/", MANAGER_ONLY),
    ("post", "/api/inventory/receive/", MANAGER_ONLY),
    ("post", "/api/inventory/adjust/", MANAGER_ONLY),
    ("get", "/api/inventory/movements/", MANAGER_ONLY),
    # sales: cashier or manager, but refunds are for managers only
    ("get", "/api/sales/", STAFF),
    ("post", "/api/sales/", STAFF),
    ("get", "/api/sales/1/", STAFF),
    ("post", "/api/sales/1/items/", STAFF),
    ("patch", "/api/sales/1/items/1/", STAFF),
    ("delete", "/api/sales/1/items/1/", STAFF),
    ("post", "/api/sales/1/pay/", STAFF),
    ("post", "/api/sales/1/cancel/", STAFF),
    ("post", "/api/sales/1/refund/", MANAGER_ONLY),
    # reports: managers only
    ("get", "/api/reports/daily/", MANAGER_ONLY),
    ("get", "/api/reports/top-products/", MANAGER_ONLY),
    ("get", "/api/reports/low-stock/", MANAGER_ONLY),
]


def call(client, method, url):
    if method in ("post", "patch"):
        return getattr(client, method)(url, {}, format="json")
    return getattr(client, method)(url)


def api_url_names():
    """The name of every route under /api/ (so a forgotten endpoint is noticed)."""
    names = set()

    def walk(patterns):
        for pattern in patterns:
            if hasattr(pattern, "url_patterns"):
                walk(pattern.url_patterns)
            elif pattern.name:
                names.add(pattern.name)

    for top in get_resolver().url_patterns:
        if hasattr(top, "url_patterns") and str(top.pattern).startswith("api/"):
            walk(top.url_patterns)
    return names


class PermissionSweepTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user(
            "sweep_mgr", password="pw", role=User.Role.MANAGER
        )
        cls.cashier = User.objects.create_user(
            "sweep_cash", password="pw", role=User.Role.CASHIER
        )

    def client_for(self, who):
        client = APIClient()
        if who == "manager":
            client.force_authenticate(self.manager)
        elif who == "cashier":
            client.force_authenticate(self.cashier)
        return client

    def test_every_endpoint_answers_each_role_correctly(self):
        for method, url, allowed in ENDPOINTS:
            for who in ("anonymous", "cashier", "manager"):
                with self.subTest(endpoint=f"{method.upper()} {url}", who=who):
                    status = call(self.client_for(who), method, url).status_code
                    if who in allowed:
                        self.assertNotIn(status, (401, 403))
                    elif who == "anonymous":
                        self.assertEqual(status, 401)
                    else:
                        self.assertEqual(status, 403)

    def test_the_table_lists_every_api_route(self):
        listed = {resolve(url).url_name for _, url, _ in ENDPOINTS}
        missing = api_url_names() - listed
        self.assertEqual(missing, set(), f"Add these routes to ENDPOINTS: {sorted(missing)}")