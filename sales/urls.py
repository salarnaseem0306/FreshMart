from rest_framework.routers import SimpleRouter

from .views import SaleViewSet

router = SimpleRouter()
router.register("sales", SaleViewSet, basename="sale")

urlpatterns = router.urls