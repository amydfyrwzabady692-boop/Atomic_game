"""دستورات پیوی: /start /me /daily /invite /history /help"""

import logging
from html import escape

from django.utils import timezone
from telegram import InlineKeyboardMarkup, Update, WebAppInfo
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
from ..tg import tg_call
from . import wallet as wallet_handlers
from .common import answer, callback, command, reply

logger = logging.getLogger(__name__)


def main_menu(context, daily: bool = False) -> InlineKeyboardMarkup:
    """منوی اصلی پیوی: هر دکمه همان کار دستور هم‌نامش را می‌کند. دکمه‌ی جایزه‌ی روزانه فقط اگر روشن باشد.

    دکمه‌ی مینی‌اپ (web_app) فقط وقتی آدرس HTTPS مینی‌اپ تنظیم شده باشد اضافه می‌شود؛ تلگرام پیامی که دکمه‌ی
    web_app با آدرس نامعتبر داشته باشد را کامل رد می‌کند و آن‌وقت /start هیچ جوابی نمی‌داد.
    """
    add_link = f"https://t.me/{render.bot_username(context)}?startgroup=true"
    rows = []
    if render.arcade_ready():
        rows.append([ui.button(texts.MENU_MINIAPP_BTN, web_app=WebAppInfo(url=render.miniapp_home_url()), style=ui.SUCCESS)])
    rows += [
        [ui.button(texts.MENU_DUEL_BTN, "pm:duel", style=ui.SUCCESS), ui.button(texts.MENU_WALLET_BTN, "pm:wallet", style=ui.SUCCESS)],
        (
            [ui.button(texts.MENU_DAILY_BTN, "pm:daily", style=ui.SUCCESS), ui.button(texts.MENU_PROFILE_BTN, "pm:me", style=ui.PRIMARY)]
            if daily
            else [ui.button(texts.MENU_PROFILE_BTN, "pm:me", style=ui.PRIMARY)]
        ),
        [ui.button(texts.MENU_INVITE_BTN, "pm:invite", style=ui.PRIMARY), ui.button(texts.MENU_TOP_BTN, "pm:gtop", style=ui.PRIMARY)],
        [ui.button(texts.MENU_ADD_BTN, url=add_link, style=ui.PRIMARY)],
        [ui.button(texts.MENU_RULES_BTN, "pm:rules", style=ui.PRIMARY), ui.button(texts.MENU_HELP_BTN, "pm:help", style=ui.PRIMARY)],
        [ui.button(texts.MENU_SUPPORT_BTN, "pm:support", style=ui.PRIMARY)],
    ]
    return InlineKeyboardMarkup(rows)


@db
def _first_start(user: TelegramUser, payload: str):
    """اولین /start در پیوی: فعال‌سازی، ثبت دعوت‌کننده، هدیه‌ی ثبت‌نام و جایزه‌ی دعوت (هر چند نفر یک بار)."""
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
    referral = economy.check_referral_reward_on_join(referrer) if referrer else None
    return referrer, bonus, economy.get_settings().daily_enabled, referral


@db
def _mark_started(user: TelegramUser) -> bool:
    """زمان اولین استارت و آنبلاک (برای API ربات‌های دیگر). ``True`` یعنی اولین بار است."""
    first = user.started_at is None and not user.started_bot
    fields = []
    if user.started_at is None:
        user.started_at = timezone.now()
        fields.append("started_at")
    if user.blocked_bot:
        user.blocked_bot = False
        fields.append("blocked_bot")
    if fields:
        user.save(update_fields=fields)
    return first


@command(join=False)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    """/start: استارت همان لحظه ثبت و به ربات‌های دیگر (وب‌هوک API) اعلام می‌شود؛ بعد اگر جوین اجباری
    باشد، تا عضویت در کانال‌ها بقیه‌ی کار (خوش‌آمد، هدیه، دعوت، شرکت در مسابقه) منتظر می‌ماند."""
    from .. import partner_hooks, ratelimit
    from . import forcejoin

    if update.effective_chat.type != ChatType.PRIVATE:
        return
    payload = context.args[0] if context.args else ""
    first = await _mark_started(user)
    if first or await ratelimit.allow(f"hook:start:{user.tg_id}", 1, 30):
        partner_hooks.emit(context.application, "start", user_id=user.tg_id, first=first)
    if not await forcejoin.gate(update, context, user, payload):
        return
    await continue_start(update, context, user, payload)


async def continue_start(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, payload: str) -> None:
    name = escape(user.display_name)
    is_new = not user.started_bot
    if not user.started_bot:
        referrer, bonus, daily_on, referral = await _first_start(user, payload)
        bonus_line = texts.START_BONUS.format(amount=fa_num(bonus)) if bonus else ""
        text = texts.START_NEW.format(name=name, bonus=bonus_line)
        if referrer:
            text += "\n\n" + texts.REFERRED_BY.format(name=escape(referrer.display_name))
            notice = render.referral_text(referral, user) if referral else ""
            if notice:
                await tg_call(context.bot.send_message, referrer.tg_id, notice, parse_mode="HTML", retries=1)
    else:
        daily_on = await _daily_enabled()
        text = texts.START_BACK.format(name=name, coins=fa_num(user.coins))
    if payload.startswith(render.OPEN_PAYLOAD_PREFIX):
        # دکمه‌ی پشتیبان زیر صفحه‌ی بازی در گروه: صفحه‌ی بازی را با دکمه‌ی web_app همین‌جا باز می‌کنیم
        await _send_open_game(update, payload[len(render.OPEN_PAYLOAD_PREFIX) :])
        return
    if payload in wallet_handlers.SECTIONS:
        # دکمه‌های کیف پول مینی‌اپ: همان بخش مستقیم باز می‌شود (کاربر تازه اول خوش‌آمد را هم می‌بیند)
        if is_new:
            await reply(update, text, main_menu(context, daily=daily_on))
        await wallet_handlers.open_section(update, context, user, payload)
        return
    if payload == "join":
        text += "\n\n" + texts.START_JOIN_HINT
    await reply(update, text, main_menu(context, daily=daily_on))
    match_id = payload[len(render.JOIN_PAYLOAD_PREFIX) :]
    if payload.startswith(render.JOIN_PAYLOAD_PREFIX) and match_id.isdigit():
        await _join_from_link(update, context, user, int(match_id))


async def _join_from_link(update: Update, context, user: TelegramUser, match_id: int) -> None:
    """کسی که در گروه «شرکت» را زد ولی ربات را استارت نکرده بود، بعد از استارت خودکار عضو همان مسابقه می‌شود."""
    from games.engine.services import MatchError

    from .common import manager_of
    from .flow import error_text

    manager = manager_of(context)
    active = manager.get(match_id)
    if active is None or active.phase != "lobby":
        await reply(update, texts.JOIN_LINK_CLOSED)
        return
    try:
        await manager.join(active, await _fresh(user))
    except MatchError as exc:
        if exc.code == "already_joined":
            await reply(update, texts.JOIN_LINK_ALREADY.format(title=escape(active.info.title_fa), group=escape(active.group_title)))
            return
        await reply(update, error_text(exc))
        return
    await reply(update, texts.JOIN_LINK_OK.format(title=escape(active.info.title_fa), group=escape(active.group_title)))


@db
def _fresh(user: TelegramUser) -> TelegramUser:
    user.refresh_from_db()
    return user


@db
def _daily_enabled() -> bool:
    return economy.get_settings().daily_enabled


@db
def _open_match_token(token: str) -> str | None:
    """توکن مسابقه‌ی در جریانی که صفحه‌ی مینی‌اپ دارد (آرکید، شطرنج، دوز و …)؛ وگرنه ``None``."""
    from games.models import ACTIVE_STATUSES, Match

    match = Match.objects.filter(token=token[:32], status__in=ACTIVE_STATUSES).only("game_type", "token", "state").first()
    if match is None:
        return None
    from arcade import board

    if match.game_type.startswith("arcade_") or board.live_match(match.token) is not None:
        return match.token
    return None


async def _send_open_game(update: Update, token: str) -> None:
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
    from . import duel as duel_handlers
    from . import group as group_handlers
    from . import shop as shop_handlers

    if update.effective_chat.type != ChatType.PRIVATE:
        return

    sub = query.data.split(":", 1)[1] if ":" in query.data else ""
    # این صفحه‌ها همان پیام منو را عوض می‌کنند (پیام تازه نمی‌فرستند)
    if sub in ("back", "support:cancel"):
        context.user_data.pop("support_flow", None)
        await answer(query, texts.SUPPORT_CANCELLED if sub == "support:cancel" else "")
        text = texts.START_BACK.format(name=escape(user.display_name), coins=fa_num(user.coins))
        await tg_call(query.edit_message_text, text, parse_mode="HTML", reply_markup=main_menu(context, daily=await _daily_enabled()))
        return
    if sub == "wallet":
        context.user_data.pop("wallet_flow", None)
        await answer(query)
        text, markup = wallet_handlers.wallet_screen(user)
        await tg_call(query.edit_message_text, text, parse_mode="HTML", reply_markup=markup)
        return
    if sub in ("support", "support:reply"):
        await answer(query)
        await support_cmd.__wrapped__(update, context, user)
        return

    actions = {
        "daily": daily,
        "me": me,
        "invite": invite,
        "help": help_cmd,
        "history": history,
        "shop": shop_handlers.shop,
        "arcade": arcade_handlers.arcade,
        "duel": duel_handlers.duel,
        "rules": group_handlers.rules,
        "gtop": group_handlers.gtop,
    }
    handler = actions.get(sub)
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
        if result.amount > 0:
            text = texts.DAILY_OK.format(amount=fa_num(result.amount), streak=fa_num(result.streak))
        else:
            text = texts.DAILY_EMPTY.format(streak=fa_num(result.streak))
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
    return qs.count(), economy.get_settings()


@command(private=True)
async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    count, config = await _invite_counts(user)
    link = render.start_link(render.bot_username(context), f"ref_{user.tg_id}")
    if config.referral_reward <= 0:
        await reply(update, texts.INVITE_OFF.format(link=link, count=fa_num(count)))
        return
    every = max(1, config.referral_every)
    await reply(
        update,
        texts.INVITE.format(
            link=link,
            every=fa_num(every),
            reward=fa_num(config.referral_reward),
            count=fa_num(count),
            progress=fa_num(count % every),
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


@command(private=True)
async def support_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    context.user_data.pop("wallet_flow", None)
    context.user_data["support_flow"] = {"step": "awaiting_msg"}
    await reply(
        update,
        texts.SUPPORT_PROMPT,
        InlineKeyboardMarkup([[ui.button(texts.WALLET_CANCEL_BTN, "pm:support:cancel", style=ui.DANGER)]]),
    )
