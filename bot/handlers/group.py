"""رویدادهای گروه: عضویت در لابی، لغو، پیام‌های بازی، رتبه‌بندی و قوانین."""

from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.ext import ContextTypes

from core import texts
from core.models import TelegramGroup, TelegramUser
from core.texts import fa_num
from games.engine.services import MatchError
from leaderboard.queries import top_players

from .. import ratelimit
from ..db import db
from ..tg import tg_call
from ..users import deactivate_group, ensure_group, is_group_admin
from .common import GROUP_TYPES, answer, callback, command, manager_of, reply
from .flow import error_text


# ------------------------------------------------------------------ لابی
@callback
async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, query):
    manager = manager_of(context)
    active = manager.active.get(update.effective_chat.id)
    match_id = int(query.data.split(":")[1])
    if active is None or active.match_id != match_id:
        await answer(query, texts.LOBBY_CLOSED)
        return
    try:
        message = await manager.join(active, user)
    except MatchError as exc:
        await answer(query, error_text(exc), alert=exc.code in ("need_start", "not_enough_coins", "banned"))
        return
    await answer(query, message)


async def _can_cancel(context, active, chat_id: int, user: TelegramUser) -> bool:
    return user.tg_id == active.creator_tg_id or await is_group_admin(context.bot, chat_id, user.tg_id)


@callback
async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, query):
    manager = manager_of(context)
    chat_id = update.effective_chat.id
    active = manager.active.get(chat_id)
    match_id = int(query.data.split(":")[1])
    if active is None or active.match_id != match_id:
        await answer(query, texts.NOTHING_TO_CANCEL)
        return
    if not await _can_cancel(context, active, chat_id, user):
        await answer(query, texts.CANCEL_NOT_ALLOWED, alert=True)
        return
    await manager.cancel(active, "manual")


@command(group=True)
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    manager = manager_of(context)
    chat_id = update.effective_chat.id
    active = manager.active.get(chat_id)
    if active is None:
        await reply(update, texts.NOTHING_TO_CANCEL)
        return
    if not await _can_cancel(context, active, chat_id, user):
        await reply(update, texts.CANCEL_NOT_ALLOWED)
        return
    await manager.cancel(active, "manual")


# ------------------------------------------------------------------ پیام‌ها و دکمه‌های بازی
async def group_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """جواب‌های بازیکن‌ها. پیام ادیت‌شده اصلاً به این handler نمی‌رسد (فیلتر UpdateType.MESSAGE)."""
    message, tg_user = update.effective_message, update.effective_user
    if message is None or tg_user is None or tg_user.is_bot:
        return
    active = manager_of(context).active.get(update.effective_chat.id)
    if active is None or active.phase != "running" or active.game is None:
        return
    # پیام فورواردی یا ارسال‌شده از طریق ربات‌ها (inline) قبول نیست
    if message.forward_origin is not None or message.via_bot is not None:
        return
    player = active.players_by_tg.get(tg_user.id)
    if player is None:
        return
    if not await ratelimit.allow_message(tg_user.id):
        return
    await manager_of(context).on_message(
        active, player, message.text or "", message.message_id, message.date.timestamp()
    )


async def game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query, tg_user = update.callback_query, update.effective_user
    if query is None or tg_user is None:
        return

    async def answer_fn(text: str = "", alert: bool = False):
        await tg_call(query.answer, text[:200] if text else None, show_alert=alert)

    if not await ratelimit.allow_callback(tg_user.id):
        await answer_fn(texts.TOO_FAST)
        return
    manager = manager_of(context)
    active = manager.active.get(update.effective_chat.id)
    _, match_id, data = query.data.split(":", 2)
    if active is None or str(active.match_id) != match_id or active.phase != "running":
        await answer_fn(texts.LOBBY_CLOSED)
        return
    await manager.on_callback(active, tg_user.id, data, query.message.message_id if query.message else 0, answer_fn)


# ------------------------------------------------------------------ رتبه‌بندی و قوانین
def _top_keyboard(scope: str, period: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(("• " if key == period else "") + label, callback_data=f"top:{scope}:{key}")
                for key, label in texts.TOP_PERIODS.items()
            ]
        ]
    )


def top_text(rows, scope: str, period: str) -> str:
    text = texts.TOP_HEADER.format(
        scope=texts.TOP_SCOPE_GROUP if scope == "g" else texts.TOP_SCOPE_GLOBAL, period=texts.TOP_PERIODS[period]
    )
    if not rows:
        return text + texts.TOP_EMPTY
    for row in rows:
        name = escape(row.user.display_name)
        if row.title:
            name += f" «{escape(row.title)}»"
        text += texts.TOP_LINE.format(
            rank=texts.MEDALS.get(row.rank, f"{fa_num(row.rank)}."),
            badge=f"{row.badge} " if row.badge else "",
            name=name,
            coins=fa_num(row.coins),
            wins=fa_num(row.wins),
        )
    return text


@db
def _top_rows(chat_id: int | None, period: str):
    group_id = None
    if chat_id is not None:
        group = TelegramGroup.objects.filter(chat_id=chat_id).first()
        if group is None:
            return []
        group_id = group.pk
    return top_players(group_id, period)


@command(group=True)
async def top(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    await ensure_group(update.effective_chat)
    rows = await _top_rows(update.effective_chat.id, "week")
    await reply(update, top_text(rows, "g", "week"), _top_keyboard("g", "week"))


@command()
async def gtop(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    rows = await _top_rows(None, "week")
    await reply(update, top_text(rows, "a", "week"), _top_keyboard("a", "week"))


@callback
async def top_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, query):
    _, scope, period = query.data.split(":")
    if period not in texts.TOP_PERIODS or scope not in ("g", "a"):
        return
    rows = await _top_rows(update.effective_chat.id if scope == "g" else None, period)
    await tg_call(
        query.edit_message_text, top_text(rows, scope, period), parse_mode="HTML", reply_markup=_top_keyboard(scope, period)
    )


@command()
async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    await reply(update, texts.RULES)


# ------------------------------------------------------------------ اضافه/حذف شدن ربات
async def my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    change, chat = update.my_chat_member, update.effective_chat
    if change is None or chat is None or chat.type not in GROUP_TYPES + (ChatType.CHANNEL,):
        return
    status = change.new_chat_member.status
    if chat.type == ChatType.CHANNEL:
        return
    if status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR):
        was_out = change.old_chat_member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED)
        await ensure_group(chat)
        if was_out:
            await tg_call(context.bot.send_message, chat.id, texts.GROUP_WELCOME, parse_mode="HTML")
    elif status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        manager = manager_of(context)
        active = manager.active.get(chat.id)
        if active is not None:
            await manager.cancel(active, "admin")
        await deactivate_group(chat.id)


@db
def _migrate_group(old_chat_id: int, new_chat_id: int) -> None:
    if not TelegramGroup.objects.filter(chat_id=new_chat_id).exists():
        TelegramGroup.objects.filter(chat_id=old_chat_id).update(chat_id=new_chat_id)


async def migrated(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """گروه به سوپرگروه تبدیل شده و شناسه‌اش عوض شده؛ تنظیمات و سابقه‌ی گروه حفظ می‌شود."""
    message = update.effective_message
    if message is None or not message.migrate_to_chat_id:
        return
    manager = manager_of(context)
    active = manager.active.get(message.chat_id)
    if active is not None:
        await manager.cancel(active, "admin")
    await _migrate_group(message.chat_id, message.migrate_to_chat_id)
