"""دستورات سوپرادمین: /grant /ban /unban /broadcast /stats"""

import asyncio
import logging
import time
from html import escape

from django.db.models import Count, Sum
from django.utils import timezone
from telegram import Update
from telegram.ext import ContextTypes

from core import texts
from core.models import TelegramGroup, TelegramUser
from core.texts import fa_num
from core.textutils import parse_int
from games.catalog import catalog
from games.models import Match, MatchPlayer, MatchStatus
from leaderboard.queries import day_start
from wallet import economy
from wallet.services import InsufficientFunds

from ..db import db
from ..tg import tg_call
from ..users import find_user
from .common import command, reply

logger = logging.getLogger(__name__)


@command(superadmin=True)
async def grant(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    """اعطای سکه‌ی مجازی برای جوایز کانال/مسابقه. در ledger با نوع ADMIN_GRANT ثبت می‌شود."""
    amount = parse_int(context.args[1]) if len(context.args) == 2 else None
    if amount is None or amount == 0:
        await reply(update, texts.GRANT_USAGE)
        return
    target = await find_user(context.args[0])
    if target is None:
        await reply(update, texts.USER_NOT_FOUND)
        return
    try:
        # شناسه‌ی پیام دستور، کلید یکتا است تا تحویل دوباره‌ی همان update دوبار سکه ندهد
        nonce = f"{update.effective_chat.id}:{update.effective_message.message_id}"
        await db(economy.admin_grant)(target, amount, user.tg_id, nonce)
    except InsufficientFunds:
        await reply(update, texts.GRANT_FAILED)
        return
    logger.info("admin grant", extra={"admin": user.tg_id, "target": target.tg_id, "amount": amount})
    await reply(
        update,
        texts.GRANT_OK.format(amount=fa_num(amount), name=escape(target.display_name), balance=fa_num(target.coins)),
    )
    if amount > 0 and target.started_bot:
        await tg_call(
            context.bot.send_message,
            target.tg_id,
            texts.GRANT_RECEIVED.format(amount=fa_num(amount)),
            parse_mode="HTML",
        )


async def _set_ban(update: Update, context, banned: bool) -> None:
    if len(context.args) != 1:
        await reply(update, texts.BAN_USAGE)
        return
    target = await find_user(context.args[0])
    if target is None:
        await reply(update, texts.USER_NOT_FOUND)
        return
    await db(lambda: TelegramUser.objects.filter(pk=target.pk).update(is_banned=banned))()
    logger.info("ban changed", extra={"admin": update.effective_user.id, "target": target.tg_id, "banned": banned})
    template = texts.BAN_OK if banned else texts.UNBAN_OK
    await reply(update, template.format(name=escape(target.display_name)))


@command(superadmin=True)
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    await _set_ban(update, context, True)


@command(superadmin=True)
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    await _set_ban(update, context, False)


@db
def _broadcast_targets() -> list[int]:
    return list(TelegramUser.objects.filter(started_bot=True, is_banned=False).values_list("tg_id", flat=True))


async def _run_broadcast(bot, admin_chat_id: int, targets: list[int], send) -> None:
    ok = failed = 0
    for tg_id in targets:
        started = time.monotonic()
        if await send(tg_id) is not None:
            ok += 1
        else:
            failed += 1
        # حدود ۲۰ پیام در ثانیه تا به حد نرخ تلگرام نخوریم
        await asyncio.sleep(max(0.0, 0.05 - (time.monotonic() - started)))
    await tg_call(bot.send_message, admin_chat_id, texts.BROADCAST_DONE.format(ok=fa_num(ok), failed=fa_num(failed)))


@command(superadmin=True)
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    message = update.effective_message
    source = message.reply_to_message
    text = message.text.partition(" ")[2].strip() if message.text else ""
    if source is None and not text:
        await reply(update, texts.BROADCAST_USAGE)
        return
    bot = context.bot

    if source is not None:

        async def send(tg_id):
            return await tg_call(bot.copy_message, tg_id, source.chat_id, source.message_id, retries=1)
    else:

        async def send(tg_id):
            return await tg_call(bot.send_message, tg_id, text, retries=1)

    targets = await _broadcast_targets()
    await reply(update, texts.BROADCAST_STARTED.format(count=fa_num(len(targets))))
    context.application.create_task(_run_broadcast(bot, update.effective_chat.id, targets, send))


@db
def _stats() -> dict:
    today = day_start()
    top = (
        Match.objects.filter(status=MatchStatus.FINISHED)
        .values("game_type")
        .annotate(n=Count("id"))
        .order_by("-n")
        .first()
    )
    return {
        "users": TelegramUser.objects.count(),
        "dau": MatchPlayer.objects.filter(joined_at__gte=today).values("user_id").distinct().count(),
        "groups": TelegramGroup.objects.filter(is_active=True).count(),
        "matches": Match.objects.filter(status=MatchStatus.FINISHED).count(),
        "matches_today": Match.objects.filter(status=MatchStatus.FINISHED, finished_at__gte=today).count(),
        "top_game": top["game_type"] if top else None,
        "coins": TelegramUser.objects.aggregate(s=Sum("coins"))["s"] or 0,
        "now": timezone.now(),
    }


@command(superadmin=True)
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    data = await _stats()
    info = catalog(include_disabled=True).get(data["top_game"]) if data["top_game"] else None
    await reply(
        update,
        texts.STATS.format(
            users=fa_num(data["users"]),
            dau=fa_num(data["dau"]),
            groups=fa_num(data["groups"]),
            matches=fa_num(data["matches"]),
            matches_today=fa_num(data["matches_today"]),
            top_game=f"{info.emoji} {info.title_fa}" if info else "—",
            coins=fa_num(data["coins"]),
        ),
    )


@command(superadmin=True)
async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    """/backup — پشتیبان همین حالا در پیوی همین مدیر."""
    from ..backup import send_backup

    await reply(update, texts.BACKUP_STARTED)
    try:
        sent = await send_backup(context.bot, [user.tg_id])
    except Exception:
        logging.getLogger(__name__).exception("manual backup failed")
        sent = 0
    if not sent:
        await reply(update, texts.BACKUP_FAILED)
