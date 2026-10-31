from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from django.views.generic import RedirectView

from core.dashboard import dashboard

urlpatterns = [
    path("admin/dashboard/", admin.site.admin_view(dashboard), name="admin_dashboard"),
    path("admin/", admin.site.urls),
    path("arcade/", include("arcade.urls")),
    # API ربات‌های دیگر (استارت این ربات و عضویت کانال‌ها؛ docs/forced-join-api.md)
    path("api/v1/", include("membership.urls")),
    path("healthz", lambda request: HttpResponse("ok")),
    # آدرس اصلی دامنه صفحه‌ی جدایی ندارد: به مینی‌اپ می‌رود. پارامترهای آدرس (مثل tgWebAppStartParam که
    # مسابقه‌ی لینک گروه را مشخص می‌کند) حتماً همراه می‌روند؛ وگرنه اگر در BotFather آدرس اصلی دامنه ثبت شده
    # باشد، دکمه‌ی «ورود به بازی» گروه به‌جای مسابقه صفحه‌ی اصلی را باز می‌کرد.
    path("", RedirectView.as_view(pattern_name="arcade:app", permanent=False, query_string=True)),
]
