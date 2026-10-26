from django.conf import settings
from django.db import models


class Sale(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        CARD = "card", "Card"

    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN
    )
    payment_method = models.CharField(
        max_length=10, choices=PaymentMethod.choices, blank=True
    )
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Sale #{self.pk} ({self.status})"


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="sale_items"
    )
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    line_total = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="saleitem_quantity_gt_0",
            ),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.product_id} @ {self.unit_price}"