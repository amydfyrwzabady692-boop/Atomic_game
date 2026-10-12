"""منوی ساخت مسابقه: /game ← انتخاب بازی ← (گزینه) ← ورودی ← تقسیم جایزه ← (مدت) ← زمان عضوگیری.

پیش‌نویس انتخاب‌ها در Redis نگه داشته می‌شود و فقط سازنده می‌تواند دکمه‌های منو را بزند.
"""

import json

from django.conf import settings
from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core import texts
from core.models import TelegramGroup, TelegramUser
from core.redis import get_redis
from core.texts import fa_num
from games import config as game_config
from games.catalog import GameInfo, catalog
from games.engine.services import MatchError

from .. import render, ui
from ..db import db
from ..tg import tg_call
from ..users import ensure_group, is_group_admin
from .common import answer, callback, command, manager_of, reply

DRAFT_TTL = 300
STEPS = ["variant", "fee", "split", "window", "join"]

ERROR_TEXTS = {
    "active_match_exists": texts.ACTIVE_MATCH_EXISTS,
    "game_disabled": texts.GAME_DISABLED,
    "fee_not_allowed": texts.FEE_NOT_ALLOWED,
    "lobby_closed": texts.LOBBY_CLOSED,
    "lobby_full": texts.LOBBY_FULL,
    "already_joined": texts.ALREADY_JOINED,
    "need_start": texts.NEED_START,
    "banned": texts.BANNED,
}


def error_text(exc: MatchError) -> str:
    if exc.code == "not_enough_coins":
        return texts.NOT_ENOUGH_COINS.format(
            balance=fa_num(exc.context.get("balance", 0)), needed=fa_num(exc.context.get("needed", 0))
        )
    return ERROR_TEXTS.get(exc.code, texts.ERROR_GENERIC)


def _draft_key(chat_id: int, message_id: int) -> str:
    return f"draft:{chat_id}:{message_id}"


async def _load_draft(chat_id: int, message_id: int) -> dict | None:
    raw = await get_redis().get(_draft_key(chat_id, message_id))
    return json.loads(raw) if raw else None


async def _save_draft(chat_id: int, message_id: int, draft: dict) -> None:
    await get_redis().set(_draft_key(chat_id, message_id), json.dumps(draft), ex=DRAFT_TTL)


def _btn(text: str, data: str, style: str = ""):
    return ui.button(text, data, style=style)


def _rows(buttons: list, per_row: int) -> list[list]:
    return [buttons[i : i + per_row] for i in range(0, len(buttons), per_row)]


def enabled_games(group: TelegramGroup) -> dict[str, GameInfo]:
    """بازی‌های قابل‌ساخت در این گروه. بازی‌های آرکید تا راه‌اندازی مینی‌اپ پیشنهاد نمی‌شوند."""
    arcade = render.arcade_ready()
    return {k: g for k, g in catalog().items() if group.game_enabled(k) and (arcade or not g.is_arcade)}


# ------------------------------------------------------------------ صفحه‌ها
def main_menu(group: TelegramGroup):
    """همه‌ی بازی‌ها روی یک صفحه: بازی‌های گروهی (آبی) و زیر آن همه‌ی بازی‌های آرکید (سبز)."""
    games = enabled_games(group)
    text_games = [g for g in games.values() if not g.is_arcade]
    arcade_games = [g for g in games.values() if g.is_arcade]
    rows = _rows([_btn(f"{g.emoji} {g.title_fa}", f"n:g:{g.key}", ui.PRIMARY) for g in text_games], 2)
    counts = []
    if text_games:
        counts.append(texts.GAME_MENU_TEXT_COUNT.format(n=fa_num(len(text_games))))
    if arcade_games:
        counts.append(texts.GAME_MENU_ARCADE_COUNT.format(n=fa_num(len(arcade_games))))
        # این دکمه فقط عنوان بخش است؛ با زدنش توضیح کوتاهی نشان داده می‌شود
        rows.append([_btn(texts.ARCADE_HEADER_BTN.format(n=fa_num(len(arcade_games))), "n:h")])
        rows += _rows([_btn(f"{g.emoji} {g.title_fa}", f"n:g:{g.key}", ui.SUCCESS) for g in arcade_games], 2)
    rows.append([_btn(texts.CLOSE_BTN, "n:x", ui.DANGER)])
    text = texts.GAME_MENU.format(counts="  ·  ".join(counts))
    if not render.arcade_ready():
        text += texts.GAME_MENU_ARCADE_OFF
    return text, InlineKeyboardMarkup(rows)


def steps_for(info: GameInfo) -> list[str]:
    steps = []
    if info.variants:
        steps.append("variant")
    steps.append("fee")
    if info.max_players > 2:
        steps.append("split")
    if info.is_arcade:
        steps.append("window")
    steps.append("join")
    return steps


def next_step(draft: dict, info: GameInfo) -> str | None:
    for step in steps_for(info):
        if step not in draft:
            return step
    return None


def step_screen(step: str, draft: dict, info: GameInfo, group: TelegramGroup):
    common = {"emoji": info.emoji, "title": info.title_fa, "description": info.description_fa}
    if step == "variant":
        text = texts.CHOOSE_VARIANT.format(variant_title=info.variant_title_fa, **common)
        buttons = _rows([_btn(label, f"n:v:{value}", ui.PRIMARY) for value, label in info.variants.items()], 2)
    elif step == "fee":
        text = texts.CHOOSE_FEE.format(**common)
        fees = [f for f in settings.ENTRY_FEE_CHOICES if group.fee_allowed(f)] or [group.min_entry]
        # رایگان سبز، ورودی‌های سکه‌ای آبی
        buttons = _rows([_btn(render.fee_label(f), f"n:f:{f}", ui.PRIMARY if f else ui.SUCCESS) for f in fees], 3)
    elif step == "split":
        text = texts.CHOOSE_SPLIT.format(**common)
        buttons = _rows([_btn(texts.SPLIT_LABELS[key], f"n:s:{key}", ui.PRIMARY) for key in settings.PRIZE_SPLITS], 2)
    elif step == "window":
        text = texts.CHOOSE_WINDOW.format(suggested=fa_num(info.suggested_minutes), **common)
        buttons = [
            [
                _btn(
                    ("⭐ " if m == info.suggested_minutes else "") + texts.MINUTES_BTN.format(n=fa_num(m)),
                    f"n:w:{m}",
                    ui.SUCCESS if m == info.suggested_minutes else ui.PRIMARY,
                )
                for m in settings.PLAY_WINDOW_CHOICES
            ]
        ]
    else:
        text = texts.CHOOSE_JOIN_TIME.format(**common)
        buttons = [
            [
                _btn(
                    ("⭐ " if s == group.default_join_seconds else "") + texts.SECONDS_BTN.format(n=fa_num(s)),
                    f"n:t:{s}",
                    ui.SUCCESS if s == group.default_join_seconds else ui.PRIMARY,
                )
                for s in settings.JOIN_SECONDS_CHOICES
            ]
        ]
    buttons.append([_btn(texts.BACK_BTN, "n:b")])
    return text, InlineKeyboardMarkup(buttons)


# ------------------------------------------------------------------ handlerها
@command(group=True)
async def game(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    chat = update.effective_chat
    group = await ensure_group(chat)
    manager = manager_of(context)
    if chat.id in manager.active:
        await reply(update, texts.ACTIVE_MATCH_EXISTS)
        return
    if not group.allow_user_created_games and not await is_group_admin(context.bot, chat.id, user.tg_id):
        await reply(update, texts.USERS_CANNOT_CREATE)
        return
    await db(game_config.reload)()
    if not enabled_games(group):
        await reply(update, texts.NO_GAMES_ENABLED)
        return
    text, keyboard = main_menu(group)
    if context.bot_data.get("reads_all") is False and not await is_group_admin(
        context.bot, chat.id, context.bot_data.get("bot_id", 0)
    ):
        text += texts.GAME_MENU_CANNOT_READ
    message = await reply(update, text, keyboard)
    if message:
        await _save_draft(chat.id, message.message_id, {"creator": user.tg_id})


async def _show(query, text, keyboard) -> None:
    await tg_call(query.edit_message_text, text, parse_mode="HTML", reply_markup=keyboard)


@callback
async def new_game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, query):
    chat = update.effective_chat
    message_id = query.message.message_id
    draft = await _load_draft(chat.id, message_id)
    if draft is None:
        await answer(query, texts.MENU_EXPIRED, alert=True)
        await tg_call(query.edit_message_reply_markup, None)
        return
    if draft["creator"] != user.tg_id:
        await answer(query, texts.NOT_YOUR_MENU, alert=True)
        return

    parts = query.data.split(":", 2)
    action = parts[1]
    value = parts[2] if len(parts) > 2 else ""
    group = await ensure_group(chat)
    games = enabled_games(group)

    if action == "x":
        await get_redis().delete(_draft_key(chat.id, message_id))
        await tg_call(query.message.delete)
        return
    if action == "m":
        draft = {"creator": user.tg_id}
        await _save_draft(chat.id, message_id, draft)
        await _show(query, *main_menu(group))
        return
    if action == "h":
        await answer(query, texts.ARCADE_HEADER_NOTE, alert=True)
        return
    if action == "g":
        if value not in games:
            await answer(query, texts.MENU_EXPIRED, alert=True)
            return
        draft = {"creator": user.tg_id, "game": value}
    info = games.get(draft.get("game", ""))
    if info is None:
        await _show(query, *main_menu(group))
        return

    if action == "b":
        done = [s for s in steps_for(info) if s in draft]
        if not done:
            draft = {"creator": user.tg_id}
            await _save_draft(chat.id, message_id, draft)
            await _show(query, *main_menu(group))
            return
        draft.pop(done[-1])
    elif action == "v" and value in info.variants:
        draft["variant"] = value
    elif action == "f" and value.isdigit() and group.fee_allowed(int(value)):
        draft["fee"] = int(value)
    elif action == "s" and value in settings.PRIZE_SPLITS:
        draft["split"] = value
    elif action == "w" and value.isdigit() and int(value) in settings.PLAY_WINDOW_CHOICES:
        draft["window"] = int(value)
    elif action == "t" and value.isdigit() and int(value) in settings.JOIN_SECONDS_CHOICES:
        draft["join"] = int(value)

    step = next_step(draft, info)
    await _save_draft(chat.id, message_id, draft)
    if step is not None:
        await _show(query, *step_screen(step, draft, info, group))
        return

    # همه‌ی انتخاب‌ها انجام شد: ساخت مسابقه و تبدیل همین پیام به لابی
    options = {}
    if draft.get("variant"):
        options["variant"] = draft["variant"]
    if info.is_arcade:
        options["window_minutes"] = draft["window"]
        options["attempts"] = settings.ARCADE_DEFAULT_ATTEMPTS
    split = settings.PRIZE_SPLITS[draft.get("split", "100")]
    manager = manager_of(context)
    await get_redis().delete(_draft_key(chat.id, message_id))
    try:
        active = await manager.create_lobby(
            group,
            user,
            info,
            fee=draft["fee"],
            split=split,
            join_seconds=draft["join"],
            options=options,
            menu_message_id=message_id,
        )
    except MatchError as exc:
        await answer(query, error_text(exc), alert=True)
        await tg_call(query.message.delete)
        return
    # سازنده خودکار عضو می‌شود (اگر بتواند)
    try:
        await manager.join(active, user)
    except MatchError as exc:
        await answer(query, error_text(exc), alert=True)
