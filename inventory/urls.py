from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import AdjustStockView, MovementListView, ReceiveStockView, SupplierViewSet

router = SimpleRouter()
router.register("suppliers", SupplierViewSet, basename="supplier")

urlpatterns = router.urls + [
    path("inventory/receive/", ReceiveStockView.as_view(), name="inventory-receive"),
    path("inventory/adjust/", AdjustStockView.as_view(), name="inventory-adjust"),
    path("inventory/movements/", MovementListView.as_view(), name="inventory-movements"),
]