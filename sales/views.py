from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .serializers import (
    AddItemSerializer, PaySaleSerializer, SaleSerializer, UpdateItemSerializer,
)
from .services import (
    InsufficientStockForSale, PaymentError, SaleStateError,
    add_item, pay_sale, remove_item, set_item_quantity,
)

from accounts.models import User
from core.pagination import StandardPagination
from core.permissions import IsCashierOrManager

from .filters import SaleFilter
from .models import Sale
from .serializers import AddItemSerializer, SaleSerializer, UpdateItemSerializer
from .services import SaleStateError, add_item, remove_item, set_item_quantity


class SaleViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = SaleSerializer
    permission_classes = [IsCashierOrManager]
    filterset_class = SaleFilter
    pagination_class = StandardPagination

    def get_queryset(self):
        queryset = Sale.objects.select_related("cashier").prefetch_related("items__product")
        if self.request.user.role != User.Role.MANAGER:
            # A cashier only ever sees (and touches) their own sales.
            queryset = queryset.filter(cashier=self.request.user)
        return queryset

    def _receipt(self, pk):
        return SaleSerializer(self.get_queryset().get(pk=pk)).data

    def create(self, request, *args, **kwargs):
        sale = Sale.objects.create(cashier=request.user)
        return Response(self._receipt(sale.pk), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="items")
    def items(self, request, pk=None):
        sale = self.get_object()
        serializer = AddItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            add_item(sale.pk, serializer.validated_data["product"],
                     serializer.validated_data["quantity"])
        except SaleStateError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(self._receipt(sale.pk), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "delete"], url_path=r"items/(?P<item_id>[0-9]+)")
    def item_detail(self, request, pk=None, item_id=None):
        sale = self.get_object()
        try:
            if request.method == "PATCH":
                serializer = UpdateItemSerializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                set_item_quantity(sale.pk, int(item_id), serializer.validated_data["quantity"])
            else:
                remove_item(sale.pk, int(item_id))
        except SaleStateError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(self._receipt(sale.pk))

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        sale = self.get_object()
        serializer = PaySaleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            _, change = pay_sale(
                sale.pk, data["payment_method"], data.get("amount_received"), request.user
            )
        except SaleStateError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except InsufficientStockForSale as exc:
            return Response(
                {"detail": str(exc), "shortages": exc.shortages},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except PaymentError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        receipt = dict(self._receipt(sale.pk))
        receipt["change"] = str(change)
        return Response(receipt)    