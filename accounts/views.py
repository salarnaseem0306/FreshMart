from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsCashierOrManager


class MeView(APIView):
    """Who am I? Returns the logged-in user's username and role."""

    permission_classes = [IsCashierOrManager]

    def get(self, request):
        return Response({"username": request.user.username, "role": request.user.role})