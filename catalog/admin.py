from django.contrib import admin, messages

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

    actions = ["mark_inactive"]

    def has_delete_permission(self, request, obj=None):
        # Products are never deleted (Rule 5: soft delete). Use "Mark inactive".
        return False

    @admin.action(description="Mark selected products inactive")
    def mark_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} product(s) marked inactive.", messages.SUCCESS)

    @admin.display(boolean=True, description="Low stock")
    def low_stock(self, obj):
        return obj.is_low_stock