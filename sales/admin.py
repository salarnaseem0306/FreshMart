from django.contrib import admin

from .models import Sale, SaleItem


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("id", "cashier", "status", "payment_method", "total", "created_at", "paid_at")
    list_filter = ("status", "payment_method")
    inlines = [SaleItemInline]