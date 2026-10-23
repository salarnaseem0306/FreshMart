from rest_framework import serializers

from catalog.models import Product

from .models import StockMovement, Supplier


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "phone", "email"]


class ReceiveStockSerializer(serializers.Serializer):
    # Receiving stock for a deactivated product is almost certainly a mistake.
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True)
    )
    quantity = serializers.IntegerField(min_value=1)
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all())
    note = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


class AdjustStockSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    change = serializers.IntegerField()  # + found stock, - lost or broken
    note = serializers.CharField(max_length=255)  # required: why are we adjusting?

    def validate_change(self, value):
        if value == 0:
            raise serializers.ValidationError("Change must not be zero.")
        return value


class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    supplier_name = serializers.CharField(
        source="supplier.name", read_only=True, allow_null=True
    )
    created_by = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            "id", "product", "product_name", "change", "reason",
            "supplier", "supplier_name", "sale", "created_by", "note", "created_at",
        ]