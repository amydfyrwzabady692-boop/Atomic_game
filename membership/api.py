"""API برای ربات‌های دیگر (مثلاً رباتی که استارت این ربات یا عضویت یک کانال را جوین اجباری گذاشته است).

احراز هویت با کلیدی است که مالک ربات از پنل /admin ← «API ربات‌ها» می‌سازد؛ کلید در هدر
``Authorization: Bearer <کلید>`` یا ``X-Api-Key`` یا پارامتر ``key`` می‌آید. همه‌ی آدرس‌ها هم GET و هم POST
(فرم یا JSON) می‌پذیرند تا از هر زبانی (حتی PHP ساده با file_get_contents) راحت صدا زده شوند:

- ``/api/v1/me`` — درستی کلید، یوزرنیم ربات و کانال‌های جوین اجباری این ربات
- ``/api/v1/user?user_id=…`` — این کاربر ربات را استارت کرده است؟ (و الان بلاکش نکرده)
- ``/api/v1/check?user_id=…&channels=@a,@b`` — استارت + عضویت در کانال‌ها (بدون channels: کانال‌های همین ربات).
  ربات باید در آن کانال‌ها ادمین باشد.

جزئیات و نمونه‌ها: docs/forced-join-api.md
"""

import json
import logging
import re
from functools import wraps

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from core.models import TelegramUser
from core.redis import get_sync_redis

from . import checks
from .models import PartnerKey

logger = logging.getLogger(__name__)

RATE_LIMIT, RATE_WINDOW = 300, 10  # درخواست در هر چند ثانیه برای هر کلید
MAX_CHANNELS = 10
USERNAME = re.compile(r"@?([A-Za-z][A-Za-z0-9_]{3,31})")


def _json(data: dict, status: int = 200) -> JsonResponse:
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


def _error(code: str, status: int) -> JsonResponse:
    return _json({"ok": False, "error": code}, status)


def _params(request) -> dict:
    data = dict(request.GET.items())
    if request.method == "POST":
        if (request.content_type or "").startswith("application/json"):
            try:
                body = json.loads(request.body or b"{}")
            except ValueError:
                body = None
            if isinstance(body, dict):
                data.update(body)
        else:
            data.update(request.POST.items())
    return data


def _key_text(request, params: dict) -> str:
    auth = request.headers.get("Authorization", "")
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    return (request.headers.get("X-Api-Key") or str(params.get("key") or "")).strip()


def _allowed(key: PartnerKey) -> bool:
    redis = get_sync_redis()
    name = f"rl:api:{key.pk}"
    count = redis.incr(name)
    if count == 1:
        redis.expire(name, RATE_WINDOW)
    if count > RATE_LIMIT:
        return False
    # آخرین استفاده: حداکثر دقیقه‌ای یک بار در دیتابیس نوشته می‌شود
    if redis.set(f"api:used:{key.pk}", "1", ex=60, nx=True):
        PartnerKey.objects.filter(pk=key.pk).update(last_used_at=timezone.now())
    return True


def partner_api(view):
    @csrf_exempt
    @wraps(view)
    def wrapper(request):
        if request.method not in ("GET", "POST"):
            return _error("method_not_allowed", 405)
        params = _params(request)
        text = _key_text(request, params)
        key = PartnerKey.objects.filter(key=text, is_active=True).first() if text else None
        if key is None:
            return _error("bad_key", 401)
        try:
            if not _allowed(key):
                return _error("rate_limited", 429)
        except Exception:  # بدون Redis هم API کار می‌کند (فقط محدودیت نرخ ندارد)
            logger.warning("partner api rate limit unavailable", exc_info=True)
        return view(request, key, params)

    return wrapper


def _user_id(params: dict) -> int | None:
    raw = str(params.get("user_id") or "").strip()
    if not raw.isdigit():
        return None
    value = int(raw)
    return value if 0 < value < 2**53 else None


def user_status(user_id: int) -> dict:
    """استارت = حداقل یک بار /start زده و الان ربات را بلاک نکرده است."""
    user = TelegramUser.objects.filter(tg_id=user_id).only("started_bot", "started_at", "blocked_bot").first()
    started = bool(user and (user.started_bot or user.started_at))
    blocked = bool(user and user.blocked_bot)
    return {
        "user_id": user_id,
        "started": started and not blocked,
        "blocked": blocked,
        "started_at": user.started_at.isoformat() if user and user.started_at else None,
    }


def parse_channels(params: dict) -> list | None:
    """``@name``، ``name``، لینک ``t.me/name`` یا شناسه‌ی عددی (‎-100…)؛ ``None`` یعنی ورودی نامعتبر."""
    raw = params.get("channels", params.get("channel", ""))
    items = raw if isinstance(raw, list) else str(raw).replace("\n", ",").split(",")
    result = []
    for item in items:
        item = str(item).strip()
        if not item:
            continue
        if "t.me/" in item:
            item = item.rstrip("/").rsplit("/", 1)[-1]
        if item.lstrip("-").isdigit():
            result.append(int(item))
            continue
        match = USERNAME.fullmatch(item)
        if match is None:
            return None
        result.append("@" + match.group(1))
    return result[:MAX_CHANNELS]


@partner_api
def me(request, key: PartnerKey, params: dict):
    from arcade.hub_views import bot_username

    return _json(
        {
            "ok": True,
            "name": key.name,
            "bot": bot_username(),
            "webhook": bool(key.webhook_url),
            "channels": [row["handle"] for row in checks.active_channels()],
        }
    )


@partner_api
def user(request, key: PartnerKey, params: dict):
    user_id = _user_id(params)
    if user_id is None:
        return _error("bad_user_id", 400)
    return _json({"ok": True, **user_status(user_id)})


@partner_api
def check(request, key: PartnerKey, params: dict):
    user_id = _user_id(params)
    if user_id is None:
        return _error("bad_user_id", 400)
    wanted = parse_channels(params)
    if wanted is None:
        return _error("bad_channels", 400)
    if wanted:
        chats = [(str(chat), chat) for chat in wanted]
    else:
        chats = [(row["handle"], row["chat_id"]) for row in checks.active_channels()]
    channels = []
    for (label, _), (joined, error) in zip(chats, checks.members([chat for _, chat in chats], user_id), strict=True):
        item = {"chat": label, "joined": bool(joined)}
        if joined is None:
            item["error"] = error or "unknown"
        channels.append(item)
    status = user_status(user_id)
    all_joined = all(item["joined"] for item in channels)
    return _json({"ok": True, **status, "channels": channels, "all_joined": all_joined, "passed": status["started"] and all_joined})
