"""دستورات پیوی: /start /me /daily /invite /history /help"""

from html import escape

from django.conf import settings
from django.utils import timezone
from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from core import texts
from core.models import TelegramUser
from core.texts import fa_num
from core.textutils import fa_date
from games.catalog import catalog
from leaderboard.progress import check_progress_achievements, xp_for_level
from leaderboard.queries import profile_stats
from wallet import economy
from wallet.models import CoinTransaction, TxType

from .. import render, ui
from ..db import db
from .common import answer, callback, command, reply


def main_menu(context, daily: bool = False) -> InlineKeyboardMarkup:
    """منوی اصلی پیوی: هر دکمه همان کار دستور هم‌نامش را می‌کند. دکمه‌ی جایزه‌ی روزانه فقط اگر روشن باشد."""
    add_link = f"https://t.me/{render.bot_username(context)}?startgroup=true"
    profile = ui.button(texts.MENU_PROFILE_BTN, "pm:me", style=ui.PRIMARY)
    first_row = [ui.button(texts.MENU_DAILY_BTN, "pm:daily", style=ui.SUCCESS), profile] if daily else [profile]
    return InlineKeyboardMarkup(
        [
            [ui.button(texts.MENU_ADD_BTN, url=add_link, style=ui.PRIMARY)],
            first_row,
            [
                ui.button(texts.MENU_WALLET_BTN, "pm:wallet", style=ui.SUCCESS),
                ui.button(texts.MENU_SHOP_BTN, "pm:shop", style=ui.PRIMARY),
            ],
            [
                ui.button(texts.MENU_ARCADE_BTN, "pm:arcade", style=ui.SUCCESS),
                ui.button(texts.MENU_INVITE_BTN, "pm:invite", style=ui.PRIMARY),
            ],
            [
                ui.button(texts.MENU_RULES_BTN, "pm:rules", style=ui.PRIMARY),
                ui.button(texts.MENU_HELP_BTN, "pm:help", style=ui.PRIMARY),
            ],
        ]
    )


@db
def _first_start(user: TelegramUser, payload: str):
    """اولین /start در پیوی: فعال‌سازی، ثبت دعوت‌کننده و هدیه‌ی ثبت‌نام."""
    referrer = None
    fields = ["started_bot"]
    user.started_bot = True
    if payload.startswith("ref_") and payload[4:].isdigit() and user.referred_by_id is None:
        candidate = TelegramUser.objects.filter(tg_id=int(payload[4:]), is_banned=False).first()
        # فقط کاربر تازه (بدون سابقه‌ی بازی) می‌تواند دعوت‌شده حساب شود
        if candidate and candidate.pk != user.pk and user.games_played == 0:
            user.referred_by = referrer = candidate
            fields.append("referred_by")
    user.save(update_fields=fields)
    tx = economy.grant_signup_bonus(user)
    bonus = tx.amount if tx is not None and not tx.duplicate else 0
    return referrer, bonus, economy.get_settings().daily_enabled


@command()
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    if update.effective_chat.type != ChatType.PRIVATE:
        return
    payload = context.args[0] if context.args else ""
    name = escape(user.display_name)
    if not user.started_bot:
        referrer, bonus, daily_on = await _first_start(user, payload)
        bonus_line = texts.START_BONUS.format(amount=fa_num(bonus)) if bonus else ""
        text = texts.START_NEW.format(name=name, bonus=bonus_line)
        if referrer:
            text += "\n\n" + texts.REFERRED_BY.format(name=escape(referrer.display_name))
    else:
        daily_on = await _daily_enabled()
        text = texts.START_BACK.format(name=name, coins=fa_num(user.coins))
    if payload.startswith(render.OPEN_PAYLOAD_PREFIX):
        # دکمه‌ی پشتیبان زیر صفحه‌ی بازی در گروه: صفحه‌ی بازی را با دکمه‌ی web_app همین‌جا باز می‌کنیم
        await _send_open_game(update, payload[len(render.OPEN_PAYLOAD_PREFIX) :])
        return
    if payload == "join":
        text += "\n\n" + texts.START_JOIN_HINT
    await reply(update, text, main_menu(context, daily=daily_on))


@db
def _daily_enabled() -> bool:
    return economy.get_settings().daily_enabled


@db
def _open_match_token(token: str) -> str | None:
    """توکن مسابقه‌ی در جریانی که صفحه‌ی مینی‌اپ دارد (آرکید، شطرنج، دوز و …)؛ وگرنه ``None``."""
    from games.models import ACTIVE_STATUSES, Match

    match = Match.objects.filter(token=token[:24], status__in=ACTIVE_STATUSES).only("game_type").first()
    if match is None:
        return None
    from arcade import board

    if match.game_type.startswith("arcade_") or board.live_match(match.token) is not None:
        return match.token
    return None


async def _send_open_game(update: Update, token: str) -> None:
    from telegram import WebAppInfo

    if not render.arcade_ready():
        await reply(update, texts.OPEN_GAME_NOT_CONFIGURED)
        return
    found = await _open_match_token(token) if token else None
    if found is None:
        await reply(update, texts.OPEN_GAME_GONE)
        return
    button = ui.button(texts.OPEN_GAME_BTN, web_app=WebAppInfo(url=render.game_page_url(found)), style=ui.SUCCESS)
    await reply(update, texts.OPEN_GAME, InlineKeyboardMarkup([[button]]))


@command()
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    await reply(update, texts.HELP_PRIVATE)


@callback
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, query):
    """دکمه‌های منوی پیوی؛ هر کدام همان handler دستور متناظر را (بدون بررسی دوباره‌ی نرخ) اجرا می‌کند."""
    from . import arcade as arcade_handlers
    from . import group as group_handlers
    from . import shop as shop_handlers
    from . import wallet as wallet_handlers

    if update.effective_chat.type != ChatType.PRIVATE:
        return
    actions = {
        "daily": daily,
        "me": me,
        "invite": invite,
        "help": help_cmd,
        "shop": shop_handlers.shop,
        "arcade": arcade_handlers.arcade,
        "rules": group_handlers.rules,
        "wallet": wallet_handlers.wallet_cmd,
        "back": start,
    }
    handler = actions.get(query.data.split(":", 1)[1])
    if handler is not None:
        await answer(query)  # این دکمه‌ها پیام تازه می‌فرستند؛ لازم نیست کاربر منتظر آن بماند
        await handler.__wrapped__(update, context, user)


def profile_text(user: TelegramUser, stats: dict) -> str:
    games = catalog(include_disabled=True)
    best = games.get(stats["best_game"]) if stats["best_game"] else None
    decor = stats["decor"]
    win_rate = round(user.wins * 100 / user.games_played) if user.games_played else 0
    frame = decor.get("frame", "")
    text = texts.PROFILE.format(
        frame=f"{frame} " if frame else "",
        name=escape(user.display_name) + (f" {decor['emoji']}" if decor.get("emoji") else ""),
        title=f"  «{escape(decor['title'])}»" if decor.get("title") else "",
        coins=fa_num(user.coins),
        level=fa_num(user.level),
        xp=fa_num(user.xp),
        next_xp=fa_num(xp_for_level(user.level + 1)),
        games=fa_num(user.games_played),
        wins=fa_num(user.wins),
        win_rate=fa_num(win_rate),
        best_game=f"{best.emoji} {best.title_fa}" if best else texts.NO_BEST_GAME,
        streak=texts.PROFILE_STREAK.format(streak=fa_num(user.daily_streak)) if stats.get("daily") else "",
        badges=" ".join(stats["badges"]) or texts.NO_BADGES,
    )
    if stats["records"]:
        parts = []
        for key, score in stats["records"]:
            info = games.get("arcade_" + key)
            if info:
                parts.append(f"{info.emoji} {fa_num(score)}")
        if parts:
            text += texts.PROFILE_ARCADE.format(records="  ".join(parts))
    return text


@command()
async def me(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    stats = await _profile(user)
    await reply(update, profile_text(user, stats))


@db
def _profile(user: TelegramUser) -> dict:
    return {**profile_stats(user), "daily": economy.get_settings().daily_enabled}


@db
def _claim_daily(user: TelegramUser):
    result = economy.claim_daily(user)
    achievements = check_progress_achievements(user) if result.claimed else []
    user.refresh_from_db()
    return result, achievements


@command(private=True)
async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    result, achievements = await _claim_daily(user)
    if result.disabled:
        await reply(update, texts.DAILY_DISABLED)
        return
    if result.claimed:
        text = texts.DAILY_OK.format(amount=fa_num(result.amount), streak=fa_num(result.streak))
    else:
        left = int((result.next_at - timezone.now()).total_seconds())
        text = texts.DAILY_ALREADY.format(hours=fa_num(left // 3600), minutes=fa_num(left % 3600 // 60))
    if result.rescue:
        text += texts.RESCUE_OK.format(amount=fa_num(result.rescue))
    for a in achievements:
        text += "\n\n" + texts.ACHIEVEMENT_UNLOCKED.format(emoji=a.emoji, title=a.title, reward=fa_num(a.reward_coins))
    await reply(update, text)


@db
def _invite_counts(user: TelegramUser):
    qs = TelegramUser.objects.filter(referred_by=user)
    return qs.count(), qs.filter(referral_rewarded=True).count(), economy.get_settings()


@command(private=True)
async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    count, rewarded, config = await _invite_counts(user)
    link = render.start_link(render.bot_username(context), f"ref_{user.tg_id}")
    if config.referral_reward <= 0:
        await reply(update, texts.INVITE_OFF.format(link=link, count=fa_num(count), rewarded=fa_num(rewarded)))
        return
    every = max(1, config.referral_every)
    await reply(
        update,
        texts.INVITE.format(
            link=link,
            every=fa_num(every),
            reward=fa_num(config.referral_reward),
            hours=fa_num(settings.REFERRAL_MIN_ACCOUNT_AGE_HOURS),
            count=fa_num(count),
            rewarded=fa_num(rewarded),
            progress=fa_num(rewarded % every),
        ),
    )


@db
def _last_transactions(user: TelegramUser):
    return list(CoinTransaction.objects.filter(user=user).order_by("-id")[:20])


@command(private=True)
async def history(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    rows = await _last_transactions(user)
    if not rows:
        await reply(update, texts.HISTORY_EMPTY)
        return
    labels = dict(TxType.choices)
    text = texts.HISTORY_HEADER
    for tx in rows:
        text += texts.HISTORY_LINE.format(
            sign="🟢 +" if tx.amount >= 0 else "🔴 −",
            amount=fa_num(abs(tx.amount)),
            type=labels.get(tx.type, tx.type),
            date=fa_date(timezone.localtime(tx.created_at)),
        )
    await reply(update, text)
