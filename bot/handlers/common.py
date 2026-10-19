"""دکوریتورهای مشترک handlerها: ثبت کاربر، بررسی مسدودی، نوع چت و rate limit."""

import logging
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


_extra_admin_ids_cache: set[int] = set()


def _fetch_extra_admin_ids_sync() -> list[int]:
    try:
        from wallet.models import EconomySettings

        eco = EconomySettings.load()
        res: list[int] = []
        for aid in getattr(eco, "extra_admin_ids", []) or []:
            try:
                res.append(int(aid))
            except (ValueError, TypeError):
                pass
        return res
    except Exception as exc:
        logger.warning("failed to fetch extra_admin_ids sync: %s", exc)
        return []


async def get_all_admin_ids() -> list[int]:
    """لیست شناسه‌های عددی تمام ادمین‌های ربات (مالک، سوپرادمین‌ها و ادمین‌های اضافه‌شده)."""
    global _extra_admin_ids_cache
    ids: list[int] = [639344728]
    for aid in getattr(settings, "SUPERADMIN_IDS", []):
        try:
            val = int(aid)
            if val not in ids:
                ids.append(val)
        except (ValueError, TypeError):
            pass
    try:
        from ..db import db

        extra = await db(_fetch_extra_admin_ids_sync)()
        _extra_admin_ids_cache = set(extra)
        for val in extra:
            if val not in ids:
                ids.append(val)
    except Exception as exc:
        logger.warning("failed to load extra_admin_ids async: %s", exc)
        for val in _extra_admin_ids_cache:
            if val not in ids:
                ids.append(val)
    return ids


def get_all_admin_ids_sync() -> list[int]:
    """نسخه‌ی همگام بر اساس کش حافظه و تنظیمات."""
    ids: list[int] = [639344728]
    for aid in getattr(settings, "SUPERADMIN_IDS", []):
        try:
            val = int(aid)
            if val not in ids:
                ids.append(val)
        except (ValueError, TypeError):
            pass
    for val in _extra_admin_ids_cache:
        if val not in ids:
            ids.append(val)
    return ids


async def is_superadmin(tg_id: int) -> bool:
    try:
        val = int(tg_id)
    except (ValueError, TypeError):
        return False
    if val == 639344728:
        return True
    if val in getattr(settings, "SUPERADMIN_IDS", []):
        return True
    if val in _extra_admin_ids_cache:
        return True
    all_ids = await get_all_admin_ids()
    return val in all_ids


def is_superadmin_sync(tg_id: int) -> bool:
    try:
        val = int(tg_id)
    except (ValueError, TypeError):
        return False
    if val == 639344728 or val in getattr(settings, "SUPERADMIN_IDS", []):
        return True
    return val in _extra_admin_ids_cache


async def reply(update: Update, text: str, reply_markup=None):
    return await tg_call(
        update.effective_message.reply_text,
        text,
        parse_mode="HTML",
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )


def command(*, private: bool = False, group: bool = False, superadmin: bool = False):
    """handler دستور: ``async def fn(update, context, user)``"""

    def decorator(fn):
        @wraps(fn)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            tg_user, chat = update.effective_user, update.effective_chat
            if tg_user is None or chat is None or tg_user.is_bot or update.effective_message is None:
                return
            if superadmin and not await is_superadmin(tg_user.id):
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


async def answer(query, text: str = "", alert: bool = False) -> None:
    """به callback جواب می‌دهد (فقط یک بار برای هر کلیک)."""
    if query.id in _answered:
        return
    _answered.add(query.id)
    await tg_call(query.answer, text[:200] if text else None, show_alert=alert)
