"""عضویت کاربر در کانال‌ها: getChatMember با کش مشترک Redis.

ربات (``bot/handlers/forcejoin.py``، با کلاینت خودش) و سرویس وب (این ماژول، برای API ربات‌های دیگر و
مینی‌اپ) هر دو همین کلیدهای کش را می‌خوانند و می‌نویسند. عضو بودن ۱۰ دقیقه کش می‌شود و عضو نبودن چند ثانیه؛
ورود و خروج کاربر در کانال‌هایی که ربات ادمینشان است (رویداد ``chat_member``) همان لحظه کش را درست می‌کند.

اگر عضویت معلوم نشود (ربات ادمین کانال نیست، کانال پاک شده، تلگرام در دسترس نیست) کاربر گیر نمی‌افتد:
جوین اجباریِ بدتنظیم‌شده نباید همه را از ربات بیرون نگه دارد.
"""

import logging
import time

from django.conf import settings

from core.redis import get_sync_redis

logger = logging.getLogger(__name__)

JOINED_STATUSES = ("creator", "administrator", "member")
JOINED_TTL = 600
NOT_JOINED_TTL = 15
CHANNELS_TTL = 20
TELEGRAM_TIMEOUT = 4
TELEGRAM_DOWN_SECONDS = 60  # بعد از خطای شبکه تا این مدت دوباره امتحان نمی‌شود (صفحه‌ها معطل timeout نمانند)
ASK_BUDGET = 8.0  # حداکثر ثانیه‌ای که یک درخواست صرف پرسیدن از تلگرام می‌کند

_channels: dict = {"rows": [], "at": float("-inf")}


def member_key(chat, user_id: int) -> str:
    """کلید کش؛ ``chat`` شناسه‌ی عددی یا ‎@username است (بدون حساسیت به حروف بزرگ)."""
    return f"fj:m:{str(chat).lower()}:{user_id}"


def status_joined(status: str, is_member=None) -> bool:
    """عضو حساب می‌شود: سازنده، ادمین، عضو و عضو محدودشده‌ای که هنوز در کانال است."""
    return status in JOINED_STATUSES or (status == "restricted" and bool(is_member))


def channel_dict(row) -> dict:
    return {
        "id": row.pk,
        "chat_id": row.chat_id,
        "title": row.title or row.handle,
        "handle": row.handle,
        "username": row.username,
        "link": row.link,
    }


def active_channels() -> list[dict]:
    """کانال‌های فعال جوین اجباری (چند ثانیه در حافظه؛ تغییر پنل در همین پروسه همان لحظه دیده می‌شود)."""
    if time.monotonic() - _channels["at"] > CHANNELS_TTL:
        from .models import ForcedChannel

        _channels["rows"] = [channel_dict(row) for row in ForcedChannel.objects.filter(is_active=True)]
        _channels["at"] = time.monotonic()
    return _channels["rows"]


def forget_channels() -> None:
    _channels["at"] = float("-inf")


def remember(chat, user_id: int, joined: bool) -> None:
    try:
        get_sync_redis().set(member_key(chat, user_id), "1" if joined else "0", ex=JOINED_TTL if joined else NOT_JOINED_TTL)
    except Exception:
        logger.warning("membership cache unavailable", exc_info=True)


def cached(chat, user_id: int) -> bool | None:
    try:
        value = get_sync_redis().get(member_key(chat, user_id))
    except Exception:
        return None
    return None if value is None else value == "1"


# ------------------------------------------------------------------ Bot API از سرویس وب
def _telegram_down() -> bool:
    try:
        return bool(get_sync_redis().exists("fj:tg_down"))
    except Exception:
        return False


def telegram(method: str, **params) -> dict | None:
    """یک متد Bot API (با همان پروکسی ربات). خطای شبکه ``None``؛ جواب تلگرام همان‌طور که هست.

    اگر تلگرام از این سرور در دسترس نباشد (مثلاً پروکسی برای سرویس وب تنظیم نشده)، یک دقیقه دوباره امتحان نمی‌شود."""
    import httpx

    if not settings.BOT_TOKEN or _telegram_down():
        return None
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/{method}"
    try:
        with httpx.Client(proxy=settings.TELEGRAM_PROXY or None, timeout=TELEGRAM_TIMEOUT) as client:
            return client.post(url, json=params).json()
    except Exception as exc:  # شبکه، پروکسی یا جواب خراب
        logger.warning("telegram api unreachable from web", extra={"method": method, "error": str(exc)})
        try:
            get_sync_redis().set("fj:tg_down", "1", ex=TELEGRAM_DOWN_SECONDS)
        except Exception:
            pass
        return None


def error_code(description: str) -> str:
    text = (description or "").lower()
    if "not enough rights" in text or "member list is inaccessible" in text or "admin" in text:
        return "bot_not_admin"
    if "chat not found" in text:
        return "chat_not_found"
    return "telegram_error"


def ask_telegram(chat, user_id: int) -> tuple[bool | None, str]:
    """(عضو هست؟، کد خطا). ``None`` یعنی معلوم نشد."""
    data = telegram("getChatMember", chat_id=chat, user_id=user_id)
    if data is None:
        return None, "network"
    if not data.get("ok"):
        description = data.get("description") or ""
        if "user not found" in description.lower() or "participant_id_invalid" in description.lower():
            return False, ""  # کاربری که هیچ‌وقت در کانال نبوده
        return None, error_code(description)
    result = data.get("result") or {}
    return status_joined(result.get("status", ""), result.get("is_member")), ""


def is_member(chat, user_id: int, fresh: bool = False, ask: bool = True) -> tuple[bool | None, str]:
    """``ask=False``: فقط کش (وقتی وقت این درخواست برای پرسیدن از تلگرام تمام شده)."""
    if not fresh or not ask:
        hit = cached(chat, user_id)
        if hit is not None or not ask:
            return hit, "" if hit is not None else "timeout"
    joined, error = ask_telegram(chat, user_id)
    if joined is not None:
        remember(chat, user_id, joined)
    return joined, error


def members(chats: list, user_id: int, fresh: bool = False) -> list[tuple[bool | None, str]]:
    """عضویت در چند چت؛ بعد از ``ASK_BUDGET`` ثانیه دیگر از تلگرام پرسیده نمی‌شود و فقط کش خوانده می‌شود."""
    started = time.monotonic()
    return [is_member(chat, user_id, fresh, ask=time.monotonic() - started < ASK_BUDGET) for chat in chats]


def missing_channels(user_id: int, fresh: bool = False) -> list[dict]:
    """کانال‌های فعالی که کاربر قطعاً عضوشان نیست."""
    rows = active_channels()
    results = members([row["chat_id"] for row in rows], user_id, fresh)
    return [row for row, (joined, _) in zip(rows, results, strict=True) if joined is False]
