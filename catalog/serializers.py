from rest_framework import serializers

from .models import Category, Product


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name"]


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    low_stock = serializers.BooleanField(source="is_low_stock", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "sku", "barcode", "category", "category_name",
            "price", "stock_quantity", "low_stock", "reorder_level", "is_active",
        ]
        # Stock never changes through the product API (Rule 3): only change_stock().
        read_only_fields = ["stock_quantity"]

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than zero.")
        return value

    def validate_barcode(self, value):
        # Treat an empty barcode as "none", so several products can lack one.
        return value or None