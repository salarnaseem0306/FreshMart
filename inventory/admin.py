from django.contrib import admin

from .models import StockMovement, Supplier


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email")
    search_fields = ("name", "email")


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("created_at", "product", "change", "reason", "supplier", "sale", "created_by")
    list_filter = ("reason", "supplier")
    search_fields = ("product__name", "product__sku")

    # History is read-only: nobody adds, edits or deletes movements here.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False