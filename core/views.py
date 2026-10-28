from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from .serializers import HealthResponseSerializer


class HealthView(APIView):
    """Open endpoint: is the app up and can it reach the database?"""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        responses={
            200: HealthResponseSerializer,
            503: HealthResponseSerializer,
        }
    )
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            return Response({"status": "error"}, status=503)
        return Response({"status": "ok"})