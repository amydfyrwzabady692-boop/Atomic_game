"""صفحه و API بازی‌های دونفره‌ی گرافیکی مینی‌اپ (شطرنج).

احراز هویت مثل بقیه‌ی مینی‌اپ با ``initData`` امضاشده‌ی تلگرام است. حرکت‌ها فقط در سرور و با
موتور قوانین اعتبارسنجی می‌شوند؛ هر کسی لینک را باز کند بازی را می‌بیند ولی فقط دو بازیکن
مسابقه می‌توانند حرکت کنند.
"""

import io
import time
from functools import lru_cache

from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from core.models import TelegramUser
from games.chess import live
from games.chess.pieces import piece_sprite
from games.models import MatchStatus

from . import board
from .services import ArcadeError
from .views import asset_version, authenticated, rate_limited

PIECE_PX = 192
PIECE_CODES = {f"{color}{kind}" for color in "wb" for kind in "kqrbnp"}


def render_page(request, token: str):
    return render(
        request,
        "arcade/board.html",
        {
            "token": token,
            "version": asset_version(),
            "dev_auth": settings.DEBUG and getattr(settings, "ARCADE_DEV_AUTH", False),
            "piece_base": reverse("arcade:piece", args=["wk"])[: -len("wk.png")],
        },
    )


@require_GET
def page(request, token: str):
    if board.live_match(token[:32]) is None:
        raise Http404
    return render_page(request, token[:32])


@lru_cache(maxsize=16)
def _piece_png(code: str) -> bytes:
    letter = code[1].upper() if code[0] == "w" else code[1].lower()
    buffer = io.BytesIO()
    piece_sprite(letter, PIECE_PX).save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


@require_GET
def piece(request, code: str):
    """تصویر یک مهره (همان مهره‌های صفحه‌ی شطرنج ربات)؛ برای همیشه کش می‌شود."""
    if code not in PIECE_CODES:
        raise Http404
    response = HttpResponse(_piece_png(code), content_type="image/png")
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


def _names(state: dict) -> dict:
    users = {u.pk: u.display_name for u in TelegramUser.objects.filter(pk__in=[state["w"], state["b"]])}
    return {"w": users.get(state["w"], ""), "b": users.get(state["b"], "")}


def _response(match, state: dict, user) -> JsonResponse:
    data = live.view(state, user.pk, time.time())
    data["players"] = _names(state)
    data["cancelled"] = match.status == MatchStatus.CANCELLED
    return JsonResponse({"ok": True, "changed": True, "state": data})


def _match(payload):
    match = board.live_match(str(payload.get("match_token") or "")[:32])
    if match is None:
        raise ArcadeError("match_not_found", 404)
    return match


def _guard(change):
    try:
        return change()
    except live.LiveError as exc:
        raise ArcadeError(exc.code, 404 if exc.code == "match_not_found" else 409) from exc


@csrf_exempt
@require_POST
@rate_limited("board", 120, 10)
@authenticated
def state(request, user, payload):
    """وضعیت فعلی. اگر کلاینت همان نسخه را داشته باشد فقط زمان باقی‌مانده برمی‌گردد."""
    match = _match(payload)
    current = match.state["board"]
    now = time.time()
    if match.status == MatchStatus.RUNNING and not current["over"] and now > (current["deadline"] or now):
        match, current, _ = _guard(lambda: board.update(match.pk, lambda s: live.check_timeout(s, now)))
    if payload.get("version") == current["version"] and match.status != MatchStatus.CANCELLED:
        left = max(0, int(current["deadline"] - now)) if current["deadline"] else 0
        return JsonResponse({"ok": True, "changed": False, "seconds_left": left})
    return _response(match, current, user)


def _int(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArcadeError("illegal_move", 400)
    return value


@csrf_exempt
@require_POST
@rate_limited("board_move", 30, 10)
@authenticated
def move(request, user, payload):
    match = _match(payload)
    if match.status != MatchStatus.RUNNING:
        raise ArcadeError("match_not_running", 409)
    src, dst = _int(payload.get("src")), _int(payload.get("dst"))
    promo = str(payload.get("promo") or "")[:1]
    now = time.time()
    match, current, _ = _guard(
        lambda: board.update(match.pk, lambda s: live.apply_move(s, user.pk, src, dst, promo, now))
    )
    return _response(match, current, user)


@csrf_exempt
@require_POST
@rate_limited("board_move", 30, 10)
@authenticated
def action(request, user, payload):
    """تسلیم یا پیشنهاد/قبول مساوی."""
    match = _match(payload)
    if match.status != MatchStatus.RUNNING:
        raise ArcadeError("match_not_running", 409)
    kind = payload.get("action")
    if kind == "resign":
        change = lambda s: live.resign(s, user.pk)  # noqa: E731
    elif kind == "draw":
        change = lambda s: live.offer_draw(s, user.pk)  # noqa: E731
    else:
        raise ArcadeError("bad_action", 400)
    match, current, _ = _guard(lambda: board.update(match.pk, change))
    return _response(match, current, user)
