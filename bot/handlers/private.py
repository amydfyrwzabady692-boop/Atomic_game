"""دستورات پیوی: /start /me /daily /invite /history /help"""

from html import escape

from django.conf import settings
from django.utils import timezone
from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from core import texts
from core.models import TelegramUser
from core.texts import fa_num
from games.catalog import catalog
from leaderboard.progress import check_progress_achievements, xp_for_level
from leaderboard.queries import profile_stats
from wallet import economy
from wallet.models import CoinTransaction, TxType

from .. import render
from ..db import db
from ..tg import tg_call
from .common import command, reply


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
    return referrer, not tx.duplicate


@command()
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    if update.effective_chat.type != ChatType.PRIVATE:
        return
    payload = context.args[0] if context.args else ""
    name = escape(user.display_name)
    if not user.started_bot:
        referrer, got_bonus = await _first_start(user, payload)
        text = texts.START_NEW.format(name=name, bonus=fa_num(settings.SIGNUP_BONUS)) if got_bonus else ""
        if not text:
            text = texts.START_BACK.format(name=name, coins=fa_num(user.coins))
        if referrer:
            text += "\n\n" + texts.REFERRED_BY.format(name=escape(referrer.display_name))
    else:
        text = texts.START_BACK.format(name=name, coins=fa_num(user.coins))
    if payload == "join":
        text += "\n\n" + texts.START_JOIN_HINT
    await reply(update, text)


@command()
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    await reply(update, texts.HELP_PRIVATE)


def profile_text(user: TelegramUser, stats: dict) -> str:
    games = catalog()
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
        streak=fa_num(user.daily_streak),
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
    stats = await db(profile_stats)(user)
    await reply(update, profile_text(user, stats))


@db
def _claim_daily(user: TelegramUser):
    result = economy.claim_daily(user)
    achievements = check_progress_achievements(user) if result.claimed else []
    referrer = economy.try_reward_referral(user)
    user.refresh_from_db()
    return result, achievements, referrer


@command(private=True)
async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    result, achievements, referrer = await _claim_daily(user)
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
    if referrer:
        await tg_call(
            context.bot.send_message,
            referrer.tg_id,
            texts.REFERRAL_REWARDED.format(name=escape(user.display_name), amount=fa_num(settings.REFERRAL_REWARD)),
            parse_mode="HTML",
        )


@db
def _invite_counts(user: TelegramUser):
    qs = TelegramUser.objects.filter(referred_by=user)
    return qs.count(), qs.filter(referral_rewarded=True).count()


@command(private=True)
async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    count, rewarded = await _invite_counts(user)
    link = render.start_link(render.bot_username(context), f"ref_{user.tg_id}")
    await reply(
        update,
        texts.INVITE.format(
            link=link,
            reward=fa_num(settings.REFERRAL_REWARD),
            hours=fa_num(settings.REFERRAL_MIN_ACCOUNT_AGE_HOURS),
            count=fa_num(count),
            rewarded=fa_num(rewarded),
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
        local = timezone.localtime(tx.created_at)
        text += texts.HISTORY_LINE.format(
            sign="🟢 +" if tx.amount >= 0 else "🔴 −",
            amount=fa_num(abs(tx.amount)),
            type=labels.get(tx.type, tx.type),
            date=texts.fa_digits(local.strftime("%m/%d %H:%M")),
        )
    await reply(update, text)
