from django.contrib import admin

from .models import Category, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name", "sku", "barcode", "category", "price",
        "stock_quantity", "low_stock", "is_active",
    )
    list_filter = ("category", "is_active")
    search_fields = ("name", "sku", "barcode")
    # Stock changes only through StockMovement (Rule 3), never by editing here.
    readonly_fields = ("stock_quantity",)

    @admin.display(boolean=True, description="Low stock")
    def low_stock(self, obj):
        return obj.is_low_stock