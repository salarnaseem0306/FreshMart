from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsCashierOrManager
from drf_spectacular.utils import extend_schema

from .serializers import MeResponseSerializer


class MeView(APIView):
    """Who am I? Returns the logged-in user's username and role."""

    permission_classes = [IsCashierOrManager]

    @extend_schema(responses=MeResponseSerializer)
    def get(self, request):
        return Response({"username": request.user.username, "role": request.user.role})