from django.conf import settings
from django.urls import path

from . import views

app_name = "arcade"

urlpatterns = [
    path("", views.app, name="app"),
    path("play/<slug:game_key>/", views.app, name="play"),
    path("api/info", views.info, name="info"),
    path("api/session/start", views.session_start, name="session_start"),
    path("api/session/submit", views.session_submit, name="session_submit"),
    path("api/match/<str:token>/leaderboard", views.leaderboard, name="leaderboard"),
]

if settings.DEBUG:
    from . import dev_views

    urlpatterns += [
        path("dev/parity/", dev_views.parity, name="dev_parity"),
        path("dev/fixtures/<slug:game_key>.json", dev_views.fixture, name="dev_fixture"),
    ]
