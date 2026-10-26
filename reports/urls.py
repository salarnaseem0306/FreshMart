from django.urls import path

from .views import DailyReportView, LowStockView, TopProductsView

urlpatterns = [
    path("reports/daily/", DailyReportView.as_view(), name="report-daily"),
    path("reports/top-products/", TopProductsView.as_view(), name="report-top-products"),
    path("reports/low-stock/", LowStockView.as_view(), name="report-low-stock"),
]