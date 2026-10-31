from django.urls import re_path

from . import api

# آدرس‌ها با یا بدون / آخر
urlpatterns = [
    re_path(r"^me/?$", api.me, name="api_me"),
    re_path(r"^(?:user|started)/?$", api.user, name="api_user"),
    re_path(r"^check/?$", api.check, name="api_check"),
]
