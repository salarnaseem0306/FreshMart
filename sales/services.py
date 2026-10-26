from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404

from .models import Sale, SaleItem


class SaleStateError(Exception):
    """The sale is not in a state that allows this action (API answers 409)."""


def _lock_open_sale(sale_id):
    """Lock the sale row, then make sure it is still open."""
    sale = Sale.objects.select_for_update().get(pk=sale_id)
    if sale.status != Sale.Status.OPEN:
        raise SaleStateError(f"Sale #{sale.pk} is {sale.status}, not open.")
    return sale


def recalculate_total(sale):
    """The total always comes from the lines, never from the client."""
    total = sale.items.aggregate(t=Sum("line_total"))["t"] or Decimal("0.00")
    sale.total = total
    sale.save(update_fields=["total"])


@transaction.atomic
def add_item(sale_id, product, quantity):
    sale = _lock_open_sale(sale_id)
    item = SaleItem.objects.filter(sale=sale, product=product).first()
    if item:
        # Same product again: raise the quantity of the existing line.
        item.quantity += quantity
        item.line_total = item.unit_price * item.quantity
        item.save(update_fields=["quantity", "line_total"])
    else:
        SaleItem.objects.create(
            sale=sale,
            product=product,
            quantity=quantity,
            unit_price=product.price,           # price frozen at this moment (Rule 4)
            line_total=product.price * quantity,
        )
    recalculate_total(sale)
    return sale


@transaction.atomic
def set_item_quantity(sale_id, item_id, quantity):
    sale = _lock_open_sale(sale_id)
    item = get_object_or_404(SaleItem, pk=item_id, sale=sale)
    item.quantity = quantity
    item.line_total = item.unit_price * quantity
    item.save(update_fields=["quantity", "line_total"])
    recalculate_total(sale)
    return sale


@transaction.atomic
def remove_item(sale_id, item_id):
    sale = _lock_open_sale(sale_id)
    get_object_or_404(SaleItem, pk=item_id, sale=sale).delete()
    recalculate_total(sale)
    return sale