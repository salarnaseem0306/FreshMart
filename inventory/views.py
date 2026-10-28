import logging
from rest_framework import generics, mixins, status, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from core.permissions import IsManager

from .filters import StockMovementFilter
from .models import StockMovement, Supplier
from .serializers import (
    AdjustStockSerializer,
    ReceiveStockSerializer,
    StockMovementSerializer,
    SupplierSerializer,
)
from .services import InsufficientStock, change_stock

logger = logging.getLogger(__name__)


class SupplierViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsManager]
    http_method_names = ["get", "post", "patch", "head", "options"]


class ReceiveStockView(APIView):
    """Stock arrives from a supplier."""

    permission_classes = [IsManager]

    @extend_schema(
      request=ReceiveStockSerializer,
      responses={201: StockMovementSerializer},
    )

    def post(self, request):
        serializer = ReceiveStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            movement = change_stock(
                data["product"],
                data["quantity"],
                StockMovement.Reason.PURCHASE,
                request.user,
                supplier=data["supplier"],
                note=data["note"],
            )
        except Exception:
            logger.exception(
                "Unexpected stock receiving error | user_id=%s | product_id=%s",
                request.user.pk,
                data["product"].pk,
            )
            raise

        return Response(
            StockMovementSerializer(movement).data,
            status=status.HTTP_201_CREATED,
        )


class AdjustStockView(APIView):
    """Correct stock after a count (breakage, theft, found items)."""

    permission_classes = [IsManager]
    @extend_schema(
     request=AdjustStockSerializer,
     responses={
        201: StockMovementSerializer,
        400: None,
    },
    )
    def post(self, request):
        serializer = AdjustStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            movement = change_stock(
                data["product"],
                data["change"],
                StockMovement.Reason.ADJUSTMENT,
                request.user,
                note=data["note"],
            )

        except InsufficientStock as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception(
                "Unexpected stock adjustment error | user_id=%s | product_id=%s",
                request.user.pk,
                data["product"].pk,
            )
            raise

        return Response(
            StockMovementSerializer(movement).data,
            status=status.HTTP_201_CREATED,
        )


class MovementPagination(PageNumberPagination):
    page_size = 50


class MovementListView(generics.ListAPIView):
    """Stock history. It only ever grows, so it is paginated."""

    queryset = StockMovement.objects.select_related("product", "supplier", "created_by")
    serializer_class = StockMovementSerializer
    permission_classes = [IsManager]
    filterset_class = StockMovementFilter
    pagination_class = MovementPagination