"""جوین اجباری در مینی‌اپ: صفحه‌ی اصلی (هاب) و کارهایی که سکه جابه‌جا می‌کنند اول عضویت می‌خواهند."""

from functools import wraps

from django.conf import settings
from django.http import JsonResponse

from . import checks


def is_bot_admin(tg_id: int) -> bool:
    """مدیران ربات (مالک، SUPERADMIN_IDS و مدیران پنل با دسترسی) مثل ربات مستثنا هستند."""
    from core.models import BotAdmin

    if tg_id == getattr(settings, "OWNER_TG_ID", None) or tg_id in settings.SUPERADMIN_IDS:
        return True
    return BotAdmin.objects.filter(tg_id=tg_id).exclude(permissions=[]).exists()


def _fresh_allowed(tg_id: int) -> bool:
    """بررسی بدون کش («✅ عضو شدم») حداکثر هر ۳ ثانیه یک بار برای هر کاربر."""
    from core.redis import get_sync_redis

    try:
        return bool(get_sync_redis().set(f"fj:fresh:{tg_id}", "1", ex=3, nx=True))
    except Exception:
        return True


def join_required_response(user, fresh: bool = False) -> JsonResponse | None:
    """اگر کاربر باید اول عضو کانال‌ها شود، جوابی با فهرست همان کانال‌ها؛ وگرنه ``None``."""
    if not checks.active_channels() or is_bot_admin(user.tg_id):
        return None
    lacking = checks.missing_channels(user.tg_id, fresh and _fresh_allowed(user.tg_id))
    if not lacking:
        return None
    channels = [{"title": row["title"], "link": row["link"]} for row in lacking]
    return JsonResponse({"ok": False, "error": "join_required", "channels": channels}, status=403)


def joined_required(view):
    """برای viewهای مینی‌اپ با امضای ``view(request, user, payload)`` (بعد از ``authenticated``)."""

    @wraps(view)
    def wrapper(request, user, payload, *args, **kwargs):
        blocked = join_required_response(user)
        if blocked is not None:
            return blocked
        return view(request, user, payload, *args, **kwargs)

    return wrapper
