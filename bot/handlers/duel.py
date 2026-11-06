"""/duel و دکمه‌های «حریف تصادفی» در پیوی: انتخاب بازی، مقدار سکه، جستجو و توافق با حریف."""

from telegram import Update
from telegram.ext import ContextTypes

from core import texts
from core.models import TelegramUser
from core.texts import fa_num
from games import duels
from games.models import Duel, DuelTicket

from .. import render
from ..db import db
from ..duels import duel_view, error_text, games_keyboard, load_duel, searching_view, stakes_keyboard
from ..tg import tg_call
from .common import answer, callback, command, reply


def _runner(context):
    return context.application.bot_data.get("duels")


@command(private=True)
async def duel(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    await reply(update, *await _home(user))


async def _home(user: TelegramUser):
    """صفحه‌ی اول: اگر جستجو یا دوئل در جریان است همان را نشان می‌دهد، وگرنه انتخاب بازی."""
    if not render.arcade_ready():
        return texts.DUEL_UNAVAILABLE, None
    active = await db(duels.active_duel)(user.pk)
    if active is not None:
        loaded, prizes = await load_duel(active.pk)
        return duel_view(loaded, loaded.side_of(user.pk), prizes)
    ticket = await db(duels.searching_ticket)(user.pk)
    if ticket is not None:
        return searching_view(ticket)
    return texts.DUEL_CHOOSE_GAME, games_keyboard()


async def _edit(query, text, keyboard) -> None:
    await tg_call(query.edit_message_text, text, parse_mode="HTML", reply_markup=keyboard)


@callback
async def duel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, query):
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    if action == "h":
        await answer(query)
        await _edit(query, *await _home(user))
        return
    if action == "i":  # ردیف عنوان بازی‌های آرکید
        await answer(query, texts.DUEL_ARCADE_NOTE.format(minutes=fa_num(duels.ARCADE_MINUTES), attempts=fa_num(duels.ARCADE_ATTEMPTS)), alert=True)
        return
    if not render.arcade_ready():
        await answer(query, texts.DUEL_UNAVAILABLE, alert=True)
        return
    try:
        if action == "g" and len(parts) == 3:
            await answer(query)
            fresh = await db(lambda: TelegramUser.objects.get(pk=user.pk))()
            info = {g.key: g for g in duels.available_games()}.get(parts[2])
            if info is None:
                raise duels.DuelError("bad_game")
            text = texts.DUEL_CHOOSE_STAKE.format(game=f"{info.emoji} {info.title_fa}", coins=fa_num(fresh.coins))
            await _edit(query, text, stakes_keyboard(info.key))
        elif action == "s" and len(parts) == 4:
            stake = None if parts[3] == "any" else int(parts[3]) if parts[3].isdigit() else -1
            result = await db(duels.search)(user, parts[2], stake)
            await answer(query)
            message_id = query.message.message_id
            if isinstance(result, DuelTicket) and result.match_id:
                # میز چندنفره همین الان پر و شروع شد؛ پیام شروع را DuelRunner برای همه می‌فرستد
                await db(duels.set_ticket_message)(result.pk, message_id)
                await _edit(query, texts.TABLE_FILLING, None)
            elif isinstance(result, DuelTicket):
                await db(duels.set_ticket_message)(result.pk, message_id)
                await _edit(query, *searching_view(result))
            else:
                await db(duels.set_duel_message)(result.pk, "b", message_id)
                await _show_duel(query, result.pk, user)
        elif action == "k" and len(parts) == 3:
            # مقدار سکه را خود کاربر می‌نویسد
            if parts[2] not in duels.duel_games():
                raise duels.DuelError("bad_game")
            context.user_data["duel_flow"] = {"kind": "search", "game": parts[2]}
            await answer(query)
            await _edit(query, texts.DUEL_CUSTOM_ASK.format(max=fa_num(duels.MAX_STAKE)), None)
        elif action == "ko" and len(parts) == 3 and parts[2].isdigit():
            context.user_data["duel_flow"] = {"kind": "offer", "duel": int(parts[2])}
            await answer(query)
            await tg_call(query.message.reply_text, texts.DUEL_CUSTOM_ASK.format(max=fa_num(duels.MAX_STAKE)), parse_mode="HTML")
        elif action == "x":
            await db(duels.cancel_search)(user)
            await answer(query, texts.DUEL_SEARCH_CANCELLED)
            await _edit(query, texts.DUEL_CHOOSE_GAME, games_keyboard())
        elif action == "o" and len(parts) == 4 and parts[2].isdigit() and parts[3].isdigit():
            result = await db(duels.offer)(user, int(parts[2]), int(parts[3]))
            await answer(query)
            await _after_change(query, context, result, user)
        elif action == "a" and len(parts) == 3 and parts[2].isdigit():
            result = await db(duels.accept)(user, int(parts[2]))
            await answer(query)
            await _after_change(query, context, result, user)
        elif action == "c" and len(parts) == 3 and parts[2].isdigit():
            result = await db(duels.cancel)(user, int(parts[2]))
            await answer(query)
            await _after_change(query, context, result, user)
    except duels.DuelError as exc:
        await answer(query, error_text(exc), alert=True)


async def custom_stake_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser) -> bool:
    """کاربر «✍️ مبلغ دلخواه» زده و حالا عدد را در پیوی فرستاده است (جستجوی تازه یا پیشنهاد در توافق)."""
    from core.textutils import parse_int

    flow = context.user_data.get("duel_flow")
    message = update.effective_message
    if not flow or message is None:
        return False
    text = (message.text or "").strip()
    if text in texts.CANCEL_WORDS:
        context.user_data.pop("duel_flow", None)
        await reply(update, texts.DUEL_CHOOSE_GAME, games_keyboard())
        return True
    amount = parse_int(text)
    if amount is None or not 0 <= amount <= duels.MAX_STAKE:
        await reply(update, texts.DUEL_CUSTOM_BAD.format(max=fa_num(duels.MAX_STAKE)))
        return True
    context.user_data.pop("duel_flow", None)
    try:
        if flow.get("kind") == "offer":
            result = await db(duels.offer)(user, int(flow["duel"]), amount)
            runner = _runner(context)
            if runner is not None:
                await runner.notify(result.pk)
            else:
                loaded, prizes = await load_duel(result.pk)
                await reply(update, *duel_view(loaded, loaded.side_of(user.pk), prizes))
            return True
        result = await db(duels.search)(user, flow["game"], amount)
    except duels.DuelError as exc:
        await reply(update, error_text(exc))
        return True
    if isinstance(result, DuelTicket) and result.match_id:
        await reply(update, texts.TABLE_FILLING)
        return True
    if isinstance(result, DuelTicket):
        text, keyboard = searching_view(result)
        sent = await reply(update, text, keyboard)
        if sent is not None:
            await db(duels.set_ticket_message)(result.pk, sent.message_id)
        return True
    loaded, prizes = await load_duel(result.pk)
    sent = await reply(update, *duel_view(loaded, loaded.side_of(user.pk), prizes))
    if sent is not None:
        await db(duels.set_duel_message)(result.pk, "b", sent.message_id)
    return True


async def _show_duel(query, duel_id: int, user: TelegramUser) -> None:
    loaded, prizes = await load_duel(duel_id)
    await _edit(query, *duel_view(loaded, loaded.side_of(user.pk), prizes))


async def _after_change(query, context, result: Duel, user: TelegramUser) -> None:
    """پیام دو طرف همین حالا به‌روز می‌شود (نه در دور بعدی بررسی دوره‌ای)."""
    runner = _runner(context)
    if runner is not None:
        await runner.notify(result.pk)
    else:
        await _show_duel(query, result.pk, user)
