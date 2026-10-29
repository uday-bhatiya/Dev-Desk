from django.contrib import admin
from django.urls import include, path

from .views import healthz

urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("", include("tickets.urls")),
]