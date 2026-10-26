from rest_framework import serializers

from catalog.models import Product

from .models import Sale, SaleItem


class SaleItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = SaleItem
        fields = ["id", "product", "product_name", "quantity", "unit_price", "line_total"]


class SaleSerializer(serializers.ModelSerializer):
    """The receipt. Output only: the client never sends prices or totals."""

    cashier = serializers.CharField(source="cashier.username", read_only=True)
    items = SaleItemSerializer(many=True, read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id", "cashier", "status", "payment_method",
            "total", "created_at", "paid_at", "items",
        ]


class AddItemSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True), required=False
    )
    barcode = serializers.CharField(required=False)
    quantity = serializers.IntegerField(min_value=1, default=1)

    def validate(self, attrs):
        has_product = "product" in attrs
        has_barcode = "barcode" in attrs
        if has_product == has_barcode:
            raise serializers.ValidationError("Send exactly one of 'product' or 'barcode'.")
        if has_barcode:
            code = attrs.pop("barcode")
            try:
                attrs["product"] = Product.objects.get(barcode=code, is_active=True)
            except Product.DoesNotExist:
                raise serializers.ValidationError(
                    {"barcode": "No active product has this barcode."}
                )
        return attrs


class UpdateItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)