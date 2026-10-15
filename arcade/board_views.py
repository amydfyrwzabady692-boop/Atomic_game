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


def render_page(request, token: str, practice: bool = False):
    match = None if practice else board.live_match(token)
    template = "arcade/board.html" if match is None or match.game_type == "chess" else "arcade/grid.html"
    return render(
        request,
        template,
        {
            "token": token,
            "version": asset_version(),
            "dev_auth": settings.DEBUG and getattr(settings, "ARCADE_DEV_AUTH", False),
            "piece_base": reverse("arcade:piece", args=["wk"])[: -len("wk.png")],
            "practice": practice,
            "menu_url": reverse("arcade:app"),
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
    sides = board.rules_for(state).players(state)
    users = {u.pk: u.display_name for u in TelegramUser.objects.filter(pk__in=list(sides.values()))}
    return {side: users.get(uid, "") for side, uid in sides.items()}


def _response(match, state: dict, user) -> JsonResponse:
    data = board.rules_for(state).view(state, user.pk, time.time())
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
        match, current, _ = _guard(
            lambda: board.update(match.pk, lambda s: board.rules_for(s).check_timeout(s, now))
        )
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
    # در دوز و دوز چهارتایی فقط ``src`` (خانه یا ستون) لازم است
    src, dst = _int(payload.get("src")), _int(payload.get("dst", 0))
    promo = str(payload.get("promo") or "")[:1]
    now = time.time()
    match, current, _ = _guard(
        lambda: board.update(match.pk, lambda s: board.rules_for(s).apply_move(s, user.pk, src, dst, promo, now))
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
        change = lambda s: board.rules_for(s).resign(s, user.pk)  # noqa: E731
    elif kind == "draw":
        change = lambda s: board.rules_for(s).offer_draw(s, user.pk)  # noqa: E731
    else:
        raise ArcadeError("bad_action", 400)
    match, current, _ = _guard(lambda: board.update(match.pk, change))
    return _response(match, current, user)


# ---------------------------------------------------------------------- شطرنج با کامپیوتر
COMPUTER_ID = 0  # هیچ کاربری شناسه‌ی صفر ندارد
PRACTICE_MOVE_SECONDS = 10**8  # تمرین ساعت ندارد
LEVEL_NAMES = {"easy": "آسان", "medium": "متوسط", "hard": "سخت"}


@require_GET
def practice_page(request):
    return render_page(request, "", practice=True)


def _practice_response(game, user) -> JsonResponse:
    data = live.view(game.state, user.pk, time.time())
    you = data["you"]
    computer = "کامپیوتر (" + LEVEL_NAMES.get(game.level, "") + ")"
    data["players"] = {you: user.display_name, ("b" if you == "w" else "w"): computer}
    data["cancelled"] = False
    data["practice"] = True
    data["game_id"] = game.pk
    data["level"] = game.level
    return JsonResponse({"ok": True, "changed": True, "state": data})


def _computer_moves(game) -> None:
    from games.chess import ai

    state = game.state
    if state["over"] or live.side_of(state, COMPUTER_ID) != live.position_of(state).turn:
        return
    move = ai.choose_move(live.position_of(state), game.level)
    if move is not None:
        live.apply_move(state, COMPUTER_ID, move.src, move.dst, move.promo, time.time())


def _practice_game(user, payload):
    from .models import ChessPractice

    game_id = payload.get("game_id")
    if isinstance(game_id, bool) or not isinstance(game_id, int):
        raise ArcadeError("match_not_found", 404)
    game = ChessPractice.objects.filter(pk=game_id, user=user).first()
    if game is None:
        raise ArcadeError("match_not_found", 404)
    return game


def _save(game) -> None:
    game.finished = bool(game.state["over"])
    game.save(update_fields=["state", "finished", "updated_at"])


@csrf_exempt
@require_POST
@rate_limited("practice_chess", 30, 10)
@authenticated
def practice_new(request, user, payload):
    """بازی تازه با کامپیوتر؛ رنگ بازیکن تصادفی است و اگر سیاه باشد کامپیوتر اول حرکت می‌کند."""
    import secrets

    from .models import ChessPractice

    level = payload.get("level") if payload.get("level") in LEVEL_NAMES else "medium"
    ChessPractice.objects.filter(user=user, finished=False).update(finished=True)
    white_is_user = secrets.randbelow(2) == 0
    sides = (user.pk, COMPUTER_ID) if white_is_user else (COMPUTER_ID, user.pk)
    game = ChessPractice(user=user, level=level, state=live.new_state(*sides, time.time(), PRACTICE_MOVE_SECONDS))
    _computer_moves(game)
    game.save()
    return _practice_response(game, user)


@csrf_exempt
@require_POST
@rate_limited("practice_chess", 30, 10)
@authenticated
def practice_state(request, user, payload):
    from .models import ChessPractice

    if payload.get("game_id") is None:  # ادامه‌ی آخرین بازی نیمه‌کاره
        game = ChessPractice.objects.filter(user=user, finished=False).order_by("-pk").first()
        if game is None:
            return JsonResponse({"ok": True, "changed": False, "none": True})
        return _practice_response(game, user)
    return _practice_response(_practice_game(user, payload), user)


@csrf_exempt
@require_POST
@rate_limited("practice_chess", 30, 10)
@authenticated
def practice_move(request, user, payload):
    game = _practice_game(user, payload)
    src, dst = _int(payload.get("src")), _int(payload.get("dst"))
    promo = str(payload.get("promo") or "")[:1]
    _guard(lambda: live.apply_move(game.state, user.pk, src, dst, promo, time.time()))
    _computer_moves(game)
    _save(game)
    return _practice_response(game, user)


@csrf_exempt
@require_POST
@rate_limited("practice_chess", 30, 10)
@authenticated
def practice_action(request, user, payload):
    game = _practice_game(user, payload)
    if payload.get("action") != "resign":
        raise ArcadeError("bad_action", 400)
    _guard(lambda: live.resign(game.state, user.pk))
    _save(game)
    return _practice_response(game, user)
