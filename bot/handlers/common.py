"""دکوریتورهای مشترک handlerها: ثبت کاربر، بررسی مسدودی، نوع چت و rate limit."""

import logging
from functools import wraps

from django.conf import settings
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from core import texts

from .. import ratelimit, render
from ..runner import MatchManager
from ..tg import tg_call
from ..users import ensure_user

logger = logging.getLogger(__name__)

GROUP_TYPES = (ChatType.GROUP, ChatType.SUPERGROUP)


def manager_of(context: ContextTypes.DEFAULT_TYPE) -> MatchManager:
    return context.application.bot_data["manager"]


def is_superadmin(tg_id: int) -> bool:
    return tg_id in settings.SUPERADMIN_IDS


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
            if superadmin and not is_superadmin(tg_user.id):
                return
            if not await ratelimit.allow(f"rl:cmd:{tg_user.id}", 3, 2):
                return
            if private and chat.type != ChatType.PRIVATE:
                keyboard = InlineKeyboardMarkup(
                    [[InlineKeyboardButton(texts.ONLY_PRIVATE_BTN, url=render.start_link(render.bot_username(context), "hi"))]]
                )
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
        if query is None or tg_user is None or query.message is None:
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
