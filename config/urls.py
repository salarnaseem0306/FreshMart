from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("core.urls")),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("catalog.urls")),
    path("api/", include("inventory.urls")),
    path("api/", include("sales.urls")),
    path("api/", include("reports.urls")),
]