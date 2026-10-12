"""صفحه و API مینی‌اپ آرکید.

احراز هویت همه‌ی endpointها با ``initData`` امضاشده‌ی تلگرام است (نه کوکی)، برای همین
CSRF لازم نیست. همه‌ی endpointها rate limit دارند.
"""

import json
import logging
from functools import wraps

from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from core.models import TelegramUser
from core.redis import get_sync_redis
from games.catalog import arcade_enabled
from games.models import MatchPlayer, MatchStatus

from . import services
from .auth import InitDataError, validate_init_data
from .models import ArcadeRecord, ArcadeSession
from .services import ArcadeError
from .sim import all_simulators, get_simulator

logger = logging.getLogger(__name__)

MAX_BODY = 1_500_000


def error(code: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "error": code}, status=status)


def client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")


def allow(key: str, limit: int, window: int) -> bool:
    redis = get_sync_redis()
    count = redis.incr(key)
    if count == 1:
        redis.expire(key, window)
    return count <= limit


def rate_limited(name: str, limit: int, window: int):
    """محدودیت نرخ بر اساس IP (و در viewهای احرازشده، بر اساس کاربر هم)."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not allow(f"rl:web:{name}:{client_ip(request)}", limit, window):
                return error("rate_limited", 429)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def authenticated(view):
    """بدنه‌ی JSON را می‌خواند، initData را اعتبارسنجی می‌کند و کاربر را به view می‌دهد."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if len(request.body) > MAX_BODY:
            return error("too_large", 413)
        try:
            payload = json.loads(request.body or b"{}")
        except ValueError:
            return error("bad_json")
        if not isinstance(payload, dict):
            return error("bad_json")
        try:
            user = user_from_init_data(payload.get("initData") or "")
        except InitDataError as exc:
            return error(f"auth_{exc}", 401)
        if user.is_banned:
            return error("banned", 403)
        if not allow(f"rl:web:user:{user.pk}", 40, 10):
            return error("rate_limited", 429)
        try:
            return view(request, user, payload, *args, **kwargs)
        except ArcadeError as exc:
            return error(exc.code, exc.status)

    return wrapper


def user_from_init_data(init_data: str) -> TelegramUser:
    # حالت توسعه: فقط وقتی صریحاً فعال شده باشد، بدون تلگرام هم می‌شود صفحه را در مرورگر تست کرد
    if settings.DEBUG and getattr(settings, "ARCADE_DEV_AUTH", False) and init_data.startswith("dev:"):
        try:
            tg_id = int(init_data[4:])
        except ValueError as exc:
            raise InitDataError("malformed") from exc
        user, _ = TelegramUser.objects.get_or_create(tg_id=tg_id, defaults={"first_name": f"dev{tg_id}"})
        return user
    data = validate_init_data(init_data)
    tg_user = data["user"]
    user, _ = TelegramUser.objects.get_or_create(
        tg_id=data["user_id"],
        defaults={
            "first_name": (tg_user.get("first_name") or "")[:128],
            "username": (tg_user.get("username") or "")[:64],
        },
    )
    return user


_asset_version_cache: dict[str, str] = {}


def asset_version() -> str:
    """نسخه‌ی فایل‌های استاتیک بازی‌ها (از زمان آخرین تغییر) تا مرورگر و تلگرام نسخه‌ی کهنه را کش نکنند."""
    if settings.DEBUG or "v" not in _asset_version_cache:
        from pathlib import Path

        root = Path(__file__).resolve().parent / "static" / "arcade"
        latest = max((p.stat().st_mtime for p in root.rglob("*") if p.is_file()), default=0)
        _asset_version_cache["v"] = format(int(latest), "x")
    return _asset_version_cache["v"]


def game_meta(sim) -> dict:
    return {
        "key": sim.key,
        "title": sim.title_fa,
        "emoji": sim.emoji,
        "howto": sim.howto_fa,
        "rules": list(sim.rules_fa),
        "tick_ms": sim.TICK_MS,
    }


# ---------------------------------------------------------------------- صفحه‌ها
@require_GET
def app(request, game_key: str | None = None):
    """نقطه‌ی ورود مینی‌اپ. لینک مستقیم گروه ``?startapp=<token>`` به همین صفحه می‌رسد و
    خود صفحه از ``start_param`` می‌فهمد مربوط به کدام مسابقه است."""
    if game_key is not None and get_simulator(game_key) is None:
        raise Http404
    start_param = request.GET.get("tgWebAppStartParam", "")
    if game_key is None and start_param:
        from . import board, board_views

        if board.live_match(start_param[:32]) is not None:
            return board_views.render_page(request, start_param[:32])
    games = [game_meta(sim) for key, sim in all_simulators().items() if arcade_enabled(key)]
    return render(
        request,
        "arcade/app.html",
        {
            "game_key": game_key or "",
            "start_param": request.GET.get("tgWebAppStartParam", ""),
            "games": games,
            "version": asset_version(),
            "dev_auth": settings.DEBUG and getattr(settings, "ARCADE_DEV_AUTH", False),
        },
    )


# ---------------------------------------------------------------------- API
@csrf_exempt
@require_POST
@rate_limited("info", 60, 10)
@authenticated
def info(request, user, payload):
    """اطلاعات صفحه‌ی شروع: بازی، تعداد تلاش باقی‌مانده، زمان باقی‌مانده و رکورد."""
    token = payload.get("match_token") or ""
    if token:
        from django.urls import reverse

        from . import board

        if board.live_match(str(token)[:32]) is not None:
            # مسابقه‌ی شطرنج است: کلاینت به صفحه‌ی گرافیکی خودش می‌رود
            return JsonResponse({"ok": True, "mode": "board", "url": reverse("arcade:board", args=[str(token)[:32]])})
        match = services.match_for_token(str(token)[:32])
        sim = get_simulator(match.game_type[len("arcade_") :])
        if sim is None:
            raise ArcadeError("unknown_game", 404)
        is_player = MatchPlayer.objects.filter(match=match, user=user).exists()
        used = services.attempts_used(match, user)
        total = services.attempts_allowed(match)
        running = match.status == MatchStatus.RUNNING and match.play_deadline is not None
        seconds_left = max(0, int((match.play_deadline - timezone.now()).total_seconds())) if running else 0
        best = max(
            (s.score for s in services.match_standings(match) if s.user_id == user.pk),
            default=0,
        )
        data = {
            "mode": "match",
            "status": match.status,
            "is_player": is_player,
            "attempts_left": max(0, total - used) if running and is_player and seconds_left > 0 else 0,
            "attempts_total": total,
            "seconds_left": seconds_left,
            "best": best,
            "variant": match.options.get("variant", ""),
        }
    else:
        sim = get_simulator(str(payload.get("game") or ""))
        if sim is None or not arcade_enabled(sim.key):
            raise ArcadeError("unknown_game", 404)
        data = {"mode": "practice", "attempts_left": -1, "attempts_total": -1, "seconds_left": -1, "best": 0}
    record = ArcadeRecord.objects.filter(user=user, game_key=sim.key).first()
    data.update({"ok": True, "game": game_meta(sim), "record": record.best_score if record else 0})
    return JsonResponse(data)


@csrf_exempt
@require_POST
@rate_limited("start", 20, 10)
@authenticated
def session_start(request, user, payload):
    if not allow(f"rl:web:start:{user.pk}", 12, 60):
        return error("rate_limited", 429)
    token = payload.get("match_token") or None
    game = payload.get("game") or None
    session, config = services.start_session(
        user, str(game)[:32] if game else None, str(token)[:32] if token else None
    )
    sim = get_simulator(session.game_key)
    return JsonResponse(
        {
            "ok": True,
            "session_id": str(session.pk),
            "seed": session.seed,
            "level_config": config,
            "tick_ms": sim.TICK_MS,
        }
    )


@csrf_exempt
@require_POST
@rate_limited("submit", 20, 10)
@authenticated
def session_submit(request, user, payload):
    session = services.submit_session(
        user,
        str(payload.get("session_id") or ""),
        payload.get("input_log"),
        payload.get("duration_ms"),
        payload.get("claimed_score"),
    )
    if session.flagged:
        logger.warning(
            "arcade session flagged",
            extra={"session": str(session.pk), "user": user.pk, "reason": session.reject_reason},
        )
    data = {
        "ok": session.status == ArcadeSession.Status.VERIFIED,
        "status": session.status,
        "verified_score": session.verified_score or 0,
        "level": session.level_reached,
    }
    if session.status != ArcadeSession.Status.VERIFIED:
        data["error"] = "rejected"
    record = ArcadeRecord.objects.filter(user=user, game_key=session.game_key).first()
    data["record"] = record.best_score if record else 0
    if session.match_id:
        match = session.match
        standings = services.match_standings(match)
        mine = next((i for i, s in enumerate(standings, start=1) if s.user_id == user.pk), 0)
        data.update(
            {
                "rank": mine,
                "players": len(standings),
                "best": next((s.score for s in standings if s.user_id == user.pk), 0),
                "attempts_left": max(0, services.attempts_allowed(match) - services.attempts_used(match, user)),
            }
        )
    return JsonResponse(data)


@require_GET
@rate_limited("board", 60, 10)
def leaderboard(request, token: str):
    try:
        match = services.match_for_token(token)
    except ArcadeError as exc:
        return error(exc.code, exc.status)
    standings = services.match_standings(match)
    running = match.status == MatchStatus.RUNNING and match.play_deadline is not None
    return JsonResponse(
        {
            "ok": True,
            "status": match.status,
            "seconds_left": max(0, int((match.play_deadline - timezone.now()).total_seconds())) if running else 0,
            "attempts_total": services.attempts_allowed(match),
            "rows": [
                {"rank": i, "name": s.name, "score": s.score, "attempts": s.attempts}
                for i, s in enumerate(standings, start=1)
            ],
        }
    )
