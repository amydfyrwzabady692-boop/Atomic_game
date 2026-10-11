from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from django.views.generic import RedirectView

from core.dashboard import dashboard

urlpatterns = [
    path("admin/dashboard/", admin.site.admin_view(dashboard), name="admin_dashboard"),
    path("admin/", admin.site.urls),
    path("arcade/", include("arcade.urls")),
    path("healthz", lambda request: HttpResponse("ok")),
    # آدرس اصلی دامنه صفحه‌ی جدایی ندارد: به فهرست بازی‌های آرکید می‌رود
    path("", RedirectView.as_view(pattern_name="arcade:app", permanent=False)),
]
