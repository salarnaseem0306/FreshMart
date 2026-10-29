from django.test import TestCase
from rest_framework.test import APIClient


class APIDocumentationPermissionTests(TestCase):

    def test_anonymous_cannot_access_docs(self):
        response = APIClient().get("/api/docs/")
        self.assertEqual(response.status_code, 401)

    def test_anonymous_cannot_access_schema(self):
        response = APIClient().get("/api/schema/")
        self.assertEqual(response.status_code, 401)