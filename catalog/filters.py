import django_filters
from django.db.models import F

from .models import Product


class ProductFilter(django_filters.FilterSet):
    low_stock = django_filters.BooleanFilter(method="filter_low_stock")

    class Meta:
        model = Product
        fields = ["category"]

    def filter_low_stock(self, queryset, name, value):
        if value:
            return queryset.filter(stock_quantity__lte=F("reorder_level"))
        return queryset.filter(stock_quantity__gt=F("reorder_level"))