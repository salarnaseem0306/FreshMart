from rest_framework.response import Response
from rest_framework.views import APIView


class MeView(APIView):
    """Who am I? Returns the logged-in user's username and role."""

    def get(self, request):
        return Response({"username": request.user.username, "role": request.user.role})