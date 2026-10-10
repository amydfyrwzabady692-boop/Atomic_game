from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

from core.dashboard import dashboard

urlpatterns = [
    path("admin/dashboard/", admin.site.admin_view(dashboard), name="admin_dashboard"),
    path("admin/", admin.site.urls),
    path("arcade/", include("arcade.urls")),
    path("healthz", lambda request: HttpResponse("ok")),
]
