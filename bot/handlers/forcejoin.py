"""جوین اجباری در ربات و رویدادهایی که ربات‌های دیگر (API) لازم دارند.

- قبل از هر کاری در پیوی، شرکت در مسابقه‌ی گروه و ساخت مسابقه، عضویت کاربر در کانال‌های فعال بررسی
  می‌شود (``membership.checks``: getChatMember با کش مشترک Redis). کسی که عضو نیست پیامی با دکمه‌ی هر کانال
  و «✅ عضو شدم» می‌گیرد؛ کاری که می‌خواست (مثلاً پارامتر /start: دعوت، شرکت در مسابقه) نگه داشته می‌شود و
  بعد از تأیید عضویت ادامه پیدا می‌کند. مدیران ربات مستثنا هستند.
- ورود و خروج کاربر در کانال‌هایی که ربات ادمینشان است (``chat_member``) همان لحظه کش را درست می‌کند و به
  وب‌هوک ربات‌های دیگر فرستاده می‌شود؛ بلاک و آنبلاک ربات در پیوی (``my_chat_member``) هم همین‌طور.
"""

import asyncio
import logging
from html import escape

from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes

from core import texts
from core.models import TelegramUser
from core.redis import get_redis
from membership import checks

from .. import partner_hooks, render, ui
from ..db import db
from ..tg import tg_call
from .common import admin_permissions, answer, callback, reply

logger = logging.getLogger(__name__)

CHECK_DATA = "fj:ok"
PENDING_SECONDS = 3600


@db
def active_channels() -> list[dict]:
    return checks.active_channels()


async def is_joined(bot, chat, user_id: int, fresh: bool = False) -> bool | None:
    """عضو هست؟ ``None`` یعنی معلوم نشد (ربات ادمین نیست یا تلگرام جواب نداد) و کاربر گیر نمی‌افتد."""
    redis = get_redis()
    key = checks.member_key(chat, user_id)
    if not fresh:
        try:
            value = await redis.get(key)
        except Exception:
            value = None
        if value is not None:
            return value == "1"
    try:
        member = await bot.get_chat_member(chat, user_id)
    except BadRequest as exc:
        text = str(exc).lower()
        if "user not found" not in text and "participant_id_invalid" not in text:
            logger.warning("forced join check failed", extra={"chat": chat, "error": str(exc)})
            return None
        joined = False
    except (TelegramError, OSError) as exc:
        logger.warning("forced join check failed", extra={"chat": chat, "error": str(exc)})
        return None
    else:
        joined = checks.status_joined(str(member.status), getattr(member, "is_member", None))
    try:
        await redis.set(key, "1" if joined else "0", ex=checks.JOINED_TTL if joined else checks.NOT_JOINED_TTL)
    except Exception:
        pass
    return joined


async def missing(bot, user_id: int, fresh: bool = False) -> list[dict]:
    rows = await active_channels()
    if not rows:
        return []
    results = await asyncio.gather(*(is_joined(bot, row["chat_id"], user_id, fresh) for row in rows))
    return [row for row, joined in zip(rows, results, strict=True) if joined is False]


async def allowed(context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, fresh: bool = False) -> bool:
    if not await active_channels() or await admin_permissions(user.tg_id):
        return True
    return not await missing(context.bot, user.tg_id, fresh)


def prompt(channels: list[dict]) -> tuple[str, InlineKeyboardMarkup]:
    count = texts.FJ_COUNT_ONE if len(channels) == 1 else texts.FJ_COUNT_MANY.format(n=texts.fa_num(len(channels)))
    lines = "\n".join(f"• {escape(row['title'])}" for row in channels)
    rows = [
        [ui.button(texts.FJ_JOIN_BTN.format(title=row["title"])[:60], url=row["link"], style=ui.PRIMARY)]
        for row in channels
        if row["link"]
    ]
    rows.append([ui.button(texts.FJ_CHECK_BTN, CHECK_DATA, style=ui.SUCCESS)])
    return texts.FJ_PROMPT.format(count=count, channels=lines), InlineKeyboardMarkup(rows)


async def _remember_payload(user_id: int, payload: str) -> None:
    try:
        if payload:
            await get_redis().set(f"fj:pending:{user_id}", payload, ex=PENDING_SECONDS)
        else:
            await get_redis().delete(f"fj:pending:{user_id}")
    except Exception:
        pass


async def _take_payload(user_id: int) -> str:
    try:
        redis = get_redis()
        value = await redis.get(f"fj:pending:{user_id}")
        await redis.delete(f"fj:pending:{user_id}")
    except Exception:
        return ""
    return value or ""


async def gate(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, payload: str = "") -> bool:
    """``True`` یعنی کاربر می‌تواند ادامه بدهد؛ وگرنه پیام عضویت فرستاده شده و ``payload`` (پارامتر /start)
    تا تأیید عضویت نگه داشته می‌شود."""
    if not await active_channels() or await admin_permissions(user.tg_id):
        return True
    lacking = await missing(context.bot, user.tg_id)
    if not lacking:
        return True
    await _remember_payload(user.tg_id, payload)
    text, markup = prompt(lacking)
    query = update.callback_query
    if query is not None:
        await answer(query, texts.FJ_ALERT)
        await tg_call(context.bot.send_message, update.effective_chat.id, text, parse_mode="HTML", reply_markup=markup)
    else:
        await reply(update, text, markup)
    return False


async def gate_in_group(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser) -> bool:
    """ساخت مسابقه در گروه: کسی که عضو نیست دکمه‌ای برای رفتن به پیوی ربات و عضویت می‌گیرد."""
    if await allowed(context, user):
        return True
    link = render.start_link(render.bot_username(context), "fj")
    keyboard = InlineKeyboardMarkup([[ui.button(texts.FJ_GROUP_BTN, url=link, style=ui.PRIMARY)]])
    await reply(update, texts.FJ_GROUP_NEED.format(name=escape(user.display_name)), keyboard)
    return False


@callback
async def check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, query):
    """«✅ عضو شدم»: دوباره (بدون کش) می‌پرسد؛ اگر عضو شده بود کار نگه‌داشته‌شده ادامه پیدا می‌کند."""
    lacking = await missing(context.bot, user.tg_id, fresh=True)
    if lacking:
        names = "\n".join(f"• {row['title']}" for row in lacking)
        await answer(query, texts.FJ_STILL_MISSING.format(channels=names), alert=True)
        text, markup = prompt(lacking)
        await tg_call(query.edit_message_text, text, parse_mode="HTML", reply_markup=markup)
        return
    await answer(query, texts.FJ_VERIFIED.replace("<b>", "").replace("</b>", ""))
    await tg_call(query.edit_message_text, texts.FJ_VERIFIED, parse_mode="HTML")
    if update.effective_chat.type == ChatType.PRIVATE:
        from .private import continue_start

        await continue_start(update, context, user, await _take_payload(user.tg_id))


# ------------------------------------------------------------------ رویدادها برای ربات‌های دیگر
JOINED_STATUSES = (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER)


async def chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ورود/خروج کاربر در چتی که ربات ادمینش است: کش عضویت همان لحظه درست می‌شود و برای کانال‌ها
    رویداد join/leave به وب‌هوک ربات‌های دیگر می‌رود."""
    change, chat = update.chat_member, update.effective_chat
    if change is None or chat is None or change.new_chat_member.user.is_bot:
        return
    user_id = change.new_chat_member.user.id
    new = change.new_chat_member
    joined = checks.status_joined(str(new.status), getattr(new, "is_member", None))
    was = checks.status_joined(str(change.old_chat_member.status), getattr(change.old_chat_member, "is_member", None))
    redis = get_redis()
    ttl = checks.JOINED_TTL if joined else checks.NOT_JOINED_TTL
    chats = [chat.id] + ([f"@{chat.username}"] if chat.username else [])
    try:
        for ref in chats:
            await redis.set(checks.member_key(ref, user_id), "1" if joined else "0", ex=ttl)
    except Exception:
        pass
    if chat.type == ChatType.CHANNEL and joined != was:
        partner_hooks.emit(
            context.application,
            "join" if joined else "leave",
            user_id=user_id,
            chat_id=chat.id,
            chat_username=chat.username or "",
            chat_title=chat.title or "",
        )


@db
def _set_blocked(tg_user, blocked: bool) -> bool:
    """``True`` اگر وضعیت عوض شد."""
    user = TelegramUser.objects.filter(tg_id=tg_user.id).first()
    if user is None:
        if blocked:
            return False
        user = TelegramUser.objects.create(
            tg_id=tg_user.id, first_name=(tg_user.first_name or "")[:128], username=(tg_user.username or "")[:64]
        )
    if user.blocked_bot == blocked:
        return False
    user.blocked_bot = blocked
    user.save(update_fields=["blocked_bot"])
    return True


async def private_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """کاربر ربات را در پیوی بلاک یا آنبلاک کرد (``my_chat_member``)."""
    change = update.my_chat_member
    if change is None or change.from_user is None or change.from_user.is_bot:
        return
    blocked = change.new_chat_member.status == ChatMemberStatus.BANNED
    if await _set_blocked(change.from_user, blocked):
        partner_hooks.emit(context.application, "block" if blocked else "unblock", user_id=change.from_user.id)
