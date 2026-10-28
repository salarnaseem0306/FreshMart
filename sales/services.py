from decimal import Decimal

import logging

from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone

from catalog.models import Product
from inventory.models import StockMovement
from inventory.services import change_stock

from .models import Sale, SaleItem


logger = logging.getLogger(__name__)


class SaleStateError(Exception):
    """The sale is not in a state that allows this action (API answers 409)."""

class PaymentError(Exception):
    """The payment itself is not acceptable (API answers 400)."""


class InsufficientStockForSale(Exception):
    """One or more lines cannot be filled (API answers 400, naming each product)."""

    def __init__(self, shortages):
        self.shortages = shortages
        super().__init__("Not enough stock for some items.")

MAX_LINE_QUANTITY = 999
MAX_MONEY = Decimal("99999999.99")


class LimitExceeded(Exception):
    """A number is too big to accept or store (API answers 400 with a field error)."""


    def _checked_line(unit_price, quantity):
     """Return the line total, or raise LimitExceeded if this line would be too big."""
     if quantity > MAX_LINE_QUANTITY:
         raise LimitExceeded(
            f"At most {MAX_LINE_QUANTITY} units of one product per line "
            f"(this line would have {quantity})."
        )
         
     line_total = unit_price * quantity
     if line_total > MAX_MONEY:
        raise LimitExceeded("The total of this line is too large. Lower the quantity.")
     return line_total 

def _checked_line(unit_price, quantity):
    if quantity > MAX_LINE_QUANTITY:
        raise LimitExceeded(
            f"At most {MAX_LINE_QUANTITY} units of one product per line "
            f"(this line would have {quantity})."
        )
    line_total = unit_price * quantity
    if line_total > MAX_MONEY:
        raise LimitExceeded("The total of this line is too large. Lower the quantity.")
    return line_total           


def _lock_open_sale(sale_id):
    """Lock the sale row, then make sure it is still open."""
    sale = Sale.objects.select_for_update().get(pk=sale_id)
    if sale.status != Sale.Status.OPEN:
        raise SaleStateError(f"Sale #{sale.pk} is {sale.status}, not open.")
    return sale


def recalculate_total(sale):
    """The total always comes from the lines, never from the client."""
    total = sale.items.aggregate(t=Sum("line_total"))["t"] or Decimal("0.00")
    if total > MAX_MONEY:
        raise LimitExceeded(
            "The total of this sale would be too large. Remove an item or lower a quantity."
        )
    sale.total = total
    sale.save(update_fields=["total"])


@transaction.atomic
def add_item(sale_id, product, quantity):
    sale = _lock_open_sale(sale_id)
    item = SaleItem.objects.filter(sale=sale, product=product).first()
    if item:
        # Same product again: raise the quantity of the existing line (limit applies to the sum).
        new_quantity = item.quantity + quantity
        item.line_total = _checked_line(item.unit_price, new_quantity)
        item.quantity = new_quantity
        item.save(update_fields=["quantity", "line_total"])
    else:
        SaleItem.objects.create(
            sale=sale,
            product=product,
            quantity=quantity,
            unit_price=product.price,           # (Rule 4)
            line_total=_checked_line(product.price, quantity),
        )
    recalculate_total(sale)
    return sale


@transaction.atomic
def set_item_quantity(sale_id, item_id, quantity):
    sale = _lock_open_sale(sale_id)
    item = get_object_or_404(SaleItem, pk=item_id, sale=sale)
    item.line_total = _checked_line(item.unit_price, quantity)
    item.quantity = quantity
    item.save(update_fields=["quantity", "line_total"])
    recalculate_total(sale)
    return sale


@transaction.atomic
def remove_item(sale_id, item_id):
    sale = _lock_open_sale(sale_id)
    get_object_or_404(SaleItem, pk=item_id, sale=sale).delete()
    recalculate_total(sale)
    return sale

@transaction.atomic
def pay_sale(sale_id, payment_method, amount_received, user):
    # 0. Lock the sale itself and make sure it is still open.
    sale = Sale.objects.select_for_update().get(pk=sale_id)
    if sale.status != Sale.Status.OPEN:
        raise SaleStateError(f"Sale #{sale.pk} is {sale.status}, so it cannot be paid.")

    items = list(sale.items.order_by("product_id"))
    if not items:
        raise PaymentError("Cannot pay an empty sale.")

    # 1. Lock every product row, always in id order (prevents deadlocks).
    products = {
        p.pk: p
        for p in Product.objects.select_for_update()
        .filter(pk__in=[item.product_id for item in items])
        .order_by("pk")
    }

    # 2. Check ALL lines first, so the cashier hears about every short product at once.
    shortages = [
        {
            "product": item.product_id,
            "name": products[item.product_id].name,
            "requested": item.quantity,
            "available": products[item.product_id].stock_quantity,
        }
        for item in items
        if products[item.product_id].stock_quantity < item.quantity
    ]
    if shortages:
        raise InsufficientStockForSale(shortages)

    # 3. Take the stock, through the one allowed door.
    for item in items:
        change_stock(
            products[item.product_id],
            -item.quantity,
            StockMovement.Reason.SALE,
            user,
            sale=sale,
            note=f"Sale #{sale.pk}",
        )

    # 4. The total comes from the lines. Cash must cover it.
    total = sum((item.line_total for item in items), Decimal("0.00"))
    change = Decimal("0.00")
    if payment_method == Sale.PaymentMethod.CASH:
        if amount_received is None or amount_received < total:
            shortfall = total - (amount_received or Decimal("0.00"))
            raise PaymentError(
                f"Amount received does not cover the total of {total}. Short by {shortfall}."
            )
        change = amount_received - total

    sale.status = Sale.Status.PAID
    sale.payment_method = payment_method
    sale.total = total
    sale.paid_at = timezone.now()
    sale.save(update_fields=["status", "payment_method", "total", "paid_at"])

    transaction.on_commit(
    lambda: logger.info(
        "Sale payment successful | user_id=%s | sale_id=%s | amount=%s",
        user.pk,
        sale.pk,
        total,
      )
    )
    return sale, change

@transaction.atomic
def cancel_sale(sale_id):
    """Cancel an open sale. Nothing was reserved, so no stock moves."""
    sale = _lock_open_sale(sale_id)  # 409 if it is not open any more
    sale.status = Sale.Status.CANCELLED
    sale.save(update_fields=["status"])
    return sale


@transaction.atomic
def refund_sale(sale_id, user):
    """Refund a paid sale in full: put every line's stock back, in one transaction."""
    sale = Sale.objects.select_for_update().get(pk=sale_id)
    if sale.status != Sale.Status.PAID:
        raise SaleStateError(
            f"Sale #{sale.pk} is {sale.status}; only a paid sale can be refunded."
        )

    items = list(sale.items.order_by("product_id"))

    # Same lock order as pay_sale: product rows in id order.
    products = {
        p.pk: p
        for p in Product.objects.select_for_update()
        .filter(pk__in=[item.product_id for item in items])
        .order_by("pk")
    }

    for item in items:
        change_stock(
            products[item.product_id],
            item.quantity,                      # positive: stock comes back
            StockMovement.Reason.REFUND,
            user,
            sale=sale,
            note=f"Refund of sale #{sale.pk}",
        )

    sale.status = Sale.Status.REFUNDED
    sale.refunded_at = timezone.now()
    sale.save(update_fields=["status", "refunded_at"])

    transaction.on_commit(
    lambda: logger.info(
        "Sale refund successful | user_id=%s | sale_id=%s | amount=%s",
        user.pk,
        sale.pk,
        sale.total,
    )
    )

    return sale