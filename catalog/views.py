from django.shortcuts import get_object_or_404
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.permissions import CashierReadManagerWrite

from .filters import ProductFilter
from .models import Category, Product
from .serializers import CategorySerializer, ProductSerializer


class CategoryViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [CashierReadManagerWrite]
    http_method_names = ["get", "post", "patch", "head", "options"]


class ProductViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ProductSerializer
    permission_classes = [CashierReadManagerWrite]
    filterset_class = ProductFilter
    search_fields = ["name", "sku"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        queryset = Product.objects.select_related("category")
        if self.action == "list":
            # Lists only show active products. Fetching one product by id also works for
            # an inactive one: old receipts and reports still point at it.
            queryset = queryset.filter(is_active=True)
        return queryset

    @action(detail=False, methods=["get"], url_path=r"barcode/(?P<code>[^/]+)")
    def by_barcode(self, request, code=None):
        product = get_object_or_404(self.get_queryset(), barcode=code, is_active=True)
        return Response(self.get_serializer(product).data)

    def perform_destroy(self, instance):
        # Soft delete (Rule 5): old sales point at this product.
        instance.is_active = False
        instance.save(update_fields=["is_active"])