from django.db import transaction
from django.db.models import F

import logging

from catalog.models import Product

from .models import StockMovement

logger = logging.getLogger(__name__)


class InsufficientStock(Exception):
    """Raised when a change would take a product's stock below zero."""

    def __init__(self, product, available, requested):
        self.product = product
        self.available = available
        self.requested = requested
        super().__init__(
            f"Not enough stock for '{product.name}': "
            f"{available} available, {abs(requested)} requested."
        )


@transaction.atomic
def change_stock(product, change, reason, user, supplier=None, sale=None, note=""):
    """The ONLY place allowed to change Product.stock_quantity.

    Updates the number in the database with an F() expression and writes the
    StockMovement row, both in one transaction: either both happen or neither.
    """
    if change == 0:
        raise ValueError("change must not be zero")

    queryset = Product.objects.filter(pk=product.pk)
    if change < 0:
        # Only update if enough stock remains; the check and the update are one
        # atomic SQL statement, so two callers can't both take the last unit.
        queryset = queryset.filter(stock_quantity__gte=-change)

    updated = queryset.update(stock_quantity=F("stock_quantity") + change)
    if not updated:
        product.refresh_from_db(fields=["stock_quantity"])
        raise InsufficientStock(product, product.stock_quantity, change)

    movement = StockMovement.objects.create(
        product=product,
        change=change,
        reason=reason,
        supplier=supplier,
        sale=sale,
        created_by=user,
        note=note,
    )
    product.refresh_from_db(fields=["stock_quantity"])

    transaction.on_commit(
    lambda: logger.info(
        "Stock adjusted | user_id=%s | product_id=%s | change=%s | reason=%s",
        user.pk,
        product.pk,
        change,
        reason,
      )
    )

    return movement