from django.conf import settings
from django.urls import path

from . import board_views, views

app_name = "arcade"

urlpatterns = [
    path("", views.app, name="app"),
    path("play/<slug:game_key>/", views.app, name="play"),
    path("api/info", views.info, name="info"),
    path("api/session/start", views.session_start, name="session_start"),
    path("api/session/submit", views.session_submit, name="session_submit"),
    path("api/match/<str:token>/leaderboard", views.leaderboard, name="leaderboard"),
    # صفحه‌ی گرافیکی بازی‌های دونفره (شطرنج)
    path("board/<str:token>/", board_views.page, name="board"),
    path("api/board/state", board_views.state, name="board_state"),
    path("api/board/move", board_views.move, name="board_move"),
    path("api/board/action", board_views.action, name="board_action"),
    path("piece/<slug:code>.png", board_views.piece, name="piece"),
    # شطرنج تمرینی با کامپیوتر
    path("chess/", board_views.practice_page, name="chess_practice"),
    path("api/practice/chess/new", board_views.practice_new, name="chess_practice_new"),
    path("api/practice/chess/state", board_views.practice_state, name="chess_practice_state"),
    path("api/practice/chess/move", board_views.practice_move, name="chess_practice_move"),
    path("api/practice/chess/action", board_views.practice_action, name="chess_practice_action"),
]

if settings.DEBUG:
    from . import dev_views

    urlpatterns += [
        path("dev/parity/", dev_views.parity, name="dev_parity"),
        path("dev/fixtures/<slug:game_key>.json", dev_views.fixture, name="dev_fixture"),
    ]
