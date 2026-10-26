from decimal import Decimal

from django.db.models import Count, F, OuterRef, Subquery, Sum

from catalog.models import Product
from inventory.models import StockMovement
from sales.models import Sale, SaleItem

ZERO = Decimal("0.00")


def money(value):
    """Format monetary values as two-decimal strings."""
    return format(value if value is not None else ZERO, ".2f")


def daily_report(day):
    """Four queries, however many sales there are: the database does the adding."""
    paid = Sale.objects.filter(status=Sale.Status.PAID, paid_at__date=day)

    totals = paid.aggregate(count=Count("id"), revenue=Sum("total"))               # query 1
    refunds = Sale.objects.filter(refunded_at__date=day).aggregate(                # query 2
        count=Count("id"), total=Sum("total")
    )
    by_method = (                                                                   # query 3
        paid.values("payment_method")
        .annotate(count=Count("id"), revenue=Sum("total"))
        .order_by("payment_method")
    )
    by_cashier = (                                                                  # query 4
        paid.values("cashier_id", "cashier__username")
        .annotate(count=Count("id"), revenue=Sum("total"))
        .order_by("-revenue", "cashier_id")
    )

    return {
        "date": day.isoformat(),
        "sales_count": totals["count"],
        "revenue": money(totals["revenue"]),
        "refunds_count": refunds["count"],
        "refunds_total": money(refunds["total"]),
        "by_payment_method": [
       {
        "payment_method": row["payment_method"],
        "count": row["count"],
        "revenue": money(row["revenue"]),
        }
    for row in by_method
],
        "by_cashier": [
            {"cashier": row["cashier__username"], "count": row["count"], "revenue": money(row["revenue"])}
            for row in by_cashier
        ],
    }


def top_products(date_from, date_to, limit):
    """Two queries: best sellers by revenue and by units, paid sales only."""
    items = SaleItem.objects.filter(
        sale__status=Sale.Status.PAID,
        sale__paid_at__date__gte=date_from,
        sale__paid_at__date__lte=date_to,
    )
    grouped = items.values("product_id", "product__name").annotate(
        units=Sum("quantity"), revenue=Sum("line_total")
    )

    def shape(rows):
        return [
            {"id": r["product_id"], "name": r["product__name"],
             "units": r["units"], "revenue": money(r["revenue"])}
            for r in rows
        ]

    return {
        "from": date_from.isoformat(),
        "to": date_to.isoformat(),
        "limit": limit,
        "by_revenue": shape(grouped.order_by("-revenue", "product_id")[:limit]),
        "by_quantity": shape(grouped.order_by("-units", "product_id")[:limit]),
    }


def low_stock():
    """One query: the supplier of the last purchase comes from a subquery."""
    last_purchase = StockMovement.objects.filter(
        product=OuterRef("pk"),
        reason=StockMovement.Reason.PURCHASE,
        supplier__isnull=False,
    ).order_by("-created_at", "-id")

    products = (
        Product.objects.filter(is_active=True, stock_quantity__lte=F("reorder_level"))
        .select_related("category")
        .annotate(
            last_supplier_id=Subquery(last_purchase.values("supplier_id")[:1]),
            last_supplier_name=Subquery(last_purchase.values("supplier__name")[:1]),
        )
        .order_by("stock_quantity", "name")
    )
    return [
        {
            "id": p.pk,
            "name": p.name,
            "sku": p.sku,
            "category": p.category.name,
            "stock_quantity": p.stock_quantity,
            "reorder_level": p.reorder_level,
            "last_supplier": (
                {"id": p.last_supplier_id, "name": p.last_supplier_name}
                if p.last_supplier_id else None
            ),
        }
        for p in products
    ]