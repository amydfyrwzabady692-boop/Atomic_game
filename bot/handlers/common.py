"""دکوریتورهای مشترک handlerها: ثبت کاربر، بررسی مسدودی، نوع چت و rate limit."""

import logging
import time
from functools import wraps

from django.conf import settings
from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from core import texts

from .. import ratelimit, render, ui
from ..runner import MatchManager
from ..tg import tg_call
from ..users import ensure_user

logger = logging.getLogger(__name__)

GROUP_TYPES = (ChatType.GROUP, ChatType.SUPERGROUP)


def manager_of(context: ContextTypes.DEFAULT_TYPE) -> MatchManager:
    return context.application.bot_data["manager"]


# ------------------------------------------------------------------ مدیران ربات و دسترسی‌ها
# مدیرهای اضافه‌شده از پنل /admin (با دسترسی‌هایشان) در دیتابیس‌اند؛ برای این‌که هر بررسی دسترسی یک کوئری
# نشود، فهرست چند ثانیه در حافظه می‌ماند. افزودن/حذف/تغییر از پنل کش را همان لحظه تازه می‌کند.
EXTRA_ADMINS_TTL = 30.0
_extra_admins: dict = {"perms": {}, "at": float("-inf")}


def _fetch_extra_admins() -> dict[int, frozenset[str]]:
    from core.models import BotAdmin
    from core.permissions import clean

    return {tg_id: frozenset(clean(perms)) for tg_id, perms in BotAdmin.objects.values_list("tg_id", "permissions")}


async def refresh_admin_ids() -> dict[int, frozenset[str]]:
    """مدیران پنل را از دیتابیس می‌خواند؛ اگر دیتابیس در دسترس نبود همان فهرست قبلی می‌ماند."""
    from ..db import db

    try:
        _extra_admins["perms"] = await db(_fetch_extra_admins)()
        _extra_admins["at"] = time.monotonic()
    except Exception as exc:
        logger.warning("failed to load bot admins: %s", exc)
    return _extra_admins["perms"]


async def _extra_admin_perms() -> dict[int, frozenset[str]]:
    if time.monotonic() - _extra_admins["at"] > EXTRA_ADMINS_TTL:
        return await refresh_admin_ids()
    return _extra_admins["perms"]


def _static_admin_ids() -> list[int]:
    ids = [settings.OWNER_TG_ID] if getattr(settings, "OWNER_TG_ID", None) else []
    return list(dict.fromkeys(ids + [int(x) for x in settings.SUPERADMIN_IDS]))


def is_owner(tg_id) -> bool:
    """مالک و سوپرادمین‌های .env: همه‌ی دسترسی‌ها را دارند و از پنل حذف نمی‌شوند."""
    try:
        return int(tg_id) in _static_admin_ids()
    except (TypeError, ValueError):
        return False


async def admin_permissions(tg_id) -> frozenset[str]:
    """دسترسی‌های این کاربر در پنل مدیریت (خالی یعنی مدیر نیست)."""
    from core.permissions import ALL

    try:
        value = int(tg_id)
    except (TypeError, ValueError):
        return frozenset()
    if value in _static_admin_ids():
        return ALL
    return (await _extra_admin_perms()).get(value, frozenset())


async def has_permission(tg_id, permission: str) -> bool:
    return permission in await admin_permissions(tg_id)


async def get_all_admin_ids(permission: str | None = None) -> list[int]:
    """شناسه‌ی مدیرانی که این دسترسی را دارند (بدون ``permission``: همه‌ی مدیران)؛ مالک و سوپرادمین‌ها اول."""
    extra = await _extra_admin_perms()
    chosen = [tg_id for tg_id, perms in sorted(extra.items()) if perms and (permission is None or permission in perms)]
    return list(dict.fromkeys(_static_admin_ids() + chosen))


async def is_superadmin(tg_id: int) -> bool:
    """آیا این کاربر مدیر ربات است (هر دسترسی‌ای داشته باشد)؟ هر بخش پنل دسترسی خودش را جدا بررسی می‌کند."""
    return bool(await admin_permissions(tg_id))


async def reply(update: Update, text: str, reply_markup=None):
    return await tg_call(
        update.effective_message.reply_text,
        text,
        parse_mode="HTML",
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )


def command(*, private: bool = False, group: bool = False, superadmin: bool = False, permission: str | None = None):
    """handler دستور: ``async def fn(update, context, user)``. ``superadmin`` یعنی فقط مدیران ربات و
    ``permission`` یعنی فقط مدیرانی که همین دسترسی را دارند (برای بقیه دستور بی‌صدا نادیده گرفته می‌شود)."""

    def decorator(fn):
        @wraps(fn)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            tg_user, chat = update.effective_user, update.effective_chat
            if tg_user is None or chat is None or tg_user.is_bot or update.effective_message is None:
                return
            if superadmin and not await is_superadmin(tg_user.id):
                return
            if permission and not await has_permission(tg_user.id, permission):
                return
            if not await ratelimit.allow(f"rl:cmd:{tg_user.id}", 3, 2):
                return
            if private and chat.type != ChatType.PRIVATE:
                link = render.start_link(render.bot_username(context), "hi")
                keyboard = InlineKeyboardMarkup([[ui.button(texts.ONLY_PRIVATE_BTN, url=link, style=ui.PRIMARY)]])
                await reply(update, texts.ONLY_PRIVATE, keyboard)
                return
            if group and chat.type not in GROUP_TYPES:
                await reply(update, texts.ONLY_GROUP)
                return
            user = await ensure_user(tg_user)
            if user.is_banned:
                if chat.type == ChatType.PRIVATE:
                    await reply(update, texts.BANNED)
                return
            await fn(update, context, user)

        return wrapper

    return decorator


def callback(fn):
    """handler دکمه‌ی اینلاین: ``async def fn(update, context, user, query)``"""

    @wraps(fn)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        tg_user = update.effective_user
        if query is None or tg_user is None:
            return
        if query.message is None:
            # پیام خیلی قدیمی است و دیگر در دسترس ربات نیست؛ فقط چرخک دکمه بسته می‌شود
            await tg_call(query.answer)
            return
        try:
            if not await ratelimit.allow_callback(tg_user.id):
                await answer(query, texts.TOO_FAST)
                return
            user = await ensure_user(tg_user)
            if user.is_banned:
                await answer(query, texts.BANNED, alert=True)
                return
            await fn(update, context, user, query)
        finally:
            if query.id not in _answered:
                await answer(query)
            _answered.discard(query.id)

    return wrapper


_answered: set[str] = set()


async def answer(query, text: str = "", alert: bool = False, url: str | None = None) -> None:
    """به callback جواب می‌دهد (فقط یک بار برای هر کلیک). با ``url`` (مثل ``t.me/<bot>?start=…``) تلگرام همان
    لینک را برای کاربر باز می‌کند؛ مثلاً پیوی ربات برای کسی که هنوز استارت نزده است."""
    if query.id in _answered:
        return
    _answered.add(query.id)
    if url:
        await tg_call(query.answer, url=url)
        return
    await tg_call(query.answer, text[:200] if text else None, show_alert=alert)
