from django.conf import settings
from django.db import models


class Supplier(models.Model):
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class StockMovement(models.Model):
    class Reason(models.TextChoices):
        PURCHASE = "purchase", "Purchase"
        SALE = "sale", "Sale"
        REFUND = "refund", "Refund"
        ADJUSTMENT = "adjustment", "Adjustment"

    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="movements"
    )
    change = models.IntegerField()  # positive = stock in, negative = stock out
    reason = models.CharField(max_length=20, choices=Reason.choices)
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, null=True, blank=True,
        related_name="movements",
    )
    sale = models.ForeignKey(
        "sales.Sale", on_delete=models.PROTECT, null=True, blank=True,
        related_name="movements",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(change=0),
                name="stockmovement_change_not_zero",
            ),
        ]

    def __str__(self):
        return f"{self.product_id}: {self.change:+d} ({self.reason})"