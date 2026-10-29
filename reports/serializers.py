from rest_framework import serializers


class DailyQuerySerializer(serializers.Serializer):
    date = serializers.DateField(required=False)


class TopProductsQuerySerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    limit = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=100,
        default=10,
    )



# Daily report response serializers

class PaymentMethodReportSerializer(serializers.Serializer):
    payment_method = serializers.CharField()
    count = serializers.IntegerField()
    revenue = serializers.CharField()


class CashierReportSerializer(serializers.Serializer):
    cashier = serializers.CharField()
    count = serializers.IntegerField()
    revenue = serializers.CharField()


class DailyReportResponseSerializer(serializers.Serializer):
    date = serializers.DateField()
    sales_count = serializers.IntegerField()
    revenue = serializers.CharField()
    refunds_count = serializers.IntegerField()
    refunds_total = serializers.CharField()
    by_payment_method = PaymentMethodReportSerializer(many=True)
    by_cashier = CashierReportSerializer(many=True)


# Top products response serializers

class TopProductRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    units = serializers.IntegerField()
    revenue = serializers.CharField()


class TopProductsResponseSerializer(serializers.Serializer):
    from_date = serializers.DateField(source="from")
    to_date = serializers.DateField(source="to")
    limit = serializers.IntegerField()
    by_revenue = TopProductRowSerializer(many=True)
    by_quantity = TopProductRowSerializer(many=True)


# Low stock response serializers

class LastSupplierSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class LowStockItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    sku = serializers.CharField()
    category = serializers.CharField()
    stock_quantity = serializers.IntegerField()
    reorder_level = serializers.IntegerField()
    last_supplier = LastSupplierSerializer(allow_null=True, required=False)
