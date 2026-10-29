from datetime import timedelta
from drf_spectacular.utils import extend_schema

from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsManager

from .queries import daily_report, low_stock, top_products
from .serializers import (
    DailyQuerySerializer,
    DailyReportResponseSerializer,
    LowStockItemSerializer,
    TopProductsQuerySerializer,
    TopProductsResponseSerializer,
)


class DailyReportView(APIView):
    permission_classes = [IsManager]

    @extend_schema(responses=DailyReportResponseSerializer)

    def get(self, request):
        query = DailyQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        day = query.validated_data.get("date") or timezone.localdate()
        return Response(daily_report(day))


class TopProductsView(APIView):
    permission_classes = [IsManager]
    @extend_schema(responses=TopProductsResponseSerializer)

    def get(self, request):
        params = request.query_params
        # "from" is a Python keyword, so map it by hand. Empty values (?from=&to=) mean "not given".
        raw = {
            "date_from": params.get("from"),
            "date_to": params.get("to"),
            "limit": params.get("limit"),
        }
        query = TopProductsQuerySerializer(data={k: v for k, v in raw.items() if v})
        query.is_valid(raise_exception=True)

        date_to = query.validated_data.get("date_to") or timezone.localdate()
        date_from = query.validated_data.get("date_from") or date_to - timedelta(days=30)
        if date_from > date_to:
            raise ValidationError({"from": "'from' must not be after 'to'."})
        return Response(top_products(date_from, date_to, query.validated_data["limit"]))


class LowStockView(APIView):
    permission_classes = [IsManager]
    @extend_schema(responses=LowStockItemSerializer(many=True))

    def get(self, request):
        return Response(low_stock())