"""/settings — تنظیمات گروه، فقط برای ادمین‌ها (بررسی با getChatMember در هر کلیک)."""

from html import escape

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core import texts
from core.models import TelegramGroup, TelegramUser
from core.texts import fa_num
from games.catalog import catalog

from .. import ui
from ..db import db
from ..tg import tg_call
from ..users import ensure_group, is_group_admin
from .common import answer, callback, command, reply

MIN_CHOICES = [0, 50, 100, 250, 500]
MAX_CHOICES = [100, 250, 500, 1000, 5000]
JOIN_CHOICES = [30, 60, 120]


def _cycle(choices: list[int], current: int) -> int:
    later = [c for c in choices if c > current]
    return later[0] if later else choices[0]


def home_screen(group: TelegramGroup):
    games = catalog()
    enabled = sum(1 for key in games if group.game_enabled(key))
    yes_no = texts.YES if group.allow_user_created_games else texts.NO
    text = texts.SETTINGS_HEADER.format(
        min=fa_num(group.min_entry),
        max=fa_num(group.max_entry),
        join=fa_num(group.default_join_seconds),
        users=yes_no,
        enabled=fa_num(enabled),
        total=fa_num(len(games)),
    )
    keyboard = InlineKeyboardMarkup(
        [
            [ui.button(texts.SETTINGS_GAMES_BTN, "set:games", style=ui.PRIMARY)],
            [
                ui.button(texts.SETTINGS_MIN_BTN.format(v=fa_num(group.min_entry)), "set:min"),
                ui.button(texts.SETTINGS_MAX_BTN.format(v=fa_num(group.max_entry)), "set:max"),
            ],
            [ui.button(texts.SETTINGS_JOIN_BTN.format(v=fa_num(group.default_join_seconds)), "set:join")],
            [
                ui.button(
                    texts.SETTINGS_USERS_BTN.format(v=yes_no),
                    "set:users",
                    style=ui.SUCCESS if group.allow_user_created_games else ui.DANGER,
                )
            ],
            [ui.button(texts.CLOSE_BTN, "set:close", style=ui.DANGER)],
        ]
    )
    return text, keyboard


def games_screen(group: TelegramGroup):
    buttons = [
        ui.button(
            f"{texts.ON if group.game_enabled(key) else texts.OFF} {info.title_fa}",
            f"set:tg:{key}",
            style=ui.SUCCESS if group.game_enabled(key) else "",
        )
        for key, info in catalog().items()
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append([ui.button(texts.BACK_BTN, "set:home")])
    return texts.SETTINGS_GAMES_HEADER, InlineKeyboardMarkup(rows)


@db
def _apply(group_id: int, action: str, value: str) -> tuple[TelegramGroup, str]:
    """تغییر را اعمال می‌کند. ``(group, خطا)`` برمی‌گرداند."""
    group = TelegramGroup.objects.get(pk=group_id)
    if action == "min":
        group.min_entry = _cycle([c for c in MIN_CHOICES if c <= group.max_entry] or [0], group.min_entry)
    elif action == "max":
        group.max_entry = _cycle([c for c in MAX_CHOICES if c >= group.min_entry] or MAX_CHOICES, group.max_entry)
    elif action == "join":
        group.default_join_seconds = _cycle(JOIN_CHOICES, group.default_join_seconds)
    elif action == "users":
        group.allow_user_created_games = not group.allow_user_created_games
    elif action == "tg":
        all_keys = list(catalog())
        if value not in all_keys:
            return group, ""
        enabled = [k for k in all_keys if group.game_enabled(k)]
        if value in enabled:
            if len(enabled) == 1:
                return group, texts.SETTINGS_LAST_GAME
            enabled.remove(value)
        else:
            enabled.append(value)
        # لیست خالی یعنی «همه فعال»
        group.enabled_games = [] if len(enabled) == len(all_keys) else [k for k in all_keys if k in enabled]
    group.save()
    return group, ""


@command(group=True)
async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    chat = update.effective_chat
    if not await is_group_admin(context.bot, chat.id, user.tg_id):
        await reply(update, texts.ONLY_ADMIN)
        return
    group = await ensure_group(chat)
    await reply(update, *home_screen(group))


@callback
async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, query):
    chat = update.effective_chat
    if not await is_group_admin(context.bot, chat.id, user.tg_id):
        await answer(query, texts.ONLY_ADMIN, alert=True)
        return
    parts = query.data.split(":", 2)
    action = parts[1]
    value = parts[2] if len(parts) > 2 else ""
    group = await ensure_group(chat)
    if action == "close":
        await tg_call(query.message.delete)
        return
    if action in ("min", "max", "join", "users", "tg"):
        group, error = await _apply(group.pk, action, value)
        if error:
            await answer(query, error, alert=True)
            return
    screen = games_screen(group) if action in ("games", "tg") else home_screen(group)
    await tg_call(query.edit_message_text, screen[0], parse_mode="HTML", reply_markup=screen[1])


@db
def _set_prize(group_id: int, note: str) -> None:
    TelegramGroup.objects.filter(pk=group_id).update(prize_note=note)


@command(group=True)
async def prize_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    """جایزه‌ی ویژه‌ی مسابقه‌های گروه (مثلاً «شارژ ۲۰ هزاری برای نفر اول»). پرداختش بیرون از ربات است."""
    chat = update.effective_chat
    if not await is_group_admin(context.bot, chat.id, user.tg_id):
        await reply(update, texts.ONLY_ADMIN)
        return
    group = await ensure_group(chat)
    note = " ".join(context.args or []).strip()[:120]
    if not note:
        await reply(update, texts.PRIZE_USAGE)
        return
    if note == "-":
        await _set_prize(group.pk, "")
        await reply(update, texts.PRIZE_CLEARED)
        return
    await _set_prize(group.pk, note)
    await reply(update, texts.PRIZE_SET.format(note=escape(note)))
