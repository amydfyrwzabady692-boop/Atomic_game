"""مدیریت ربات: پنل /admin و دستورهای /grant /ban /unban /broadcast /stats /backup.

هر بخش پنل، هر دستور و هر مرحله‌ی پیام‌محور فقط برای مدیری کار می‌کند که دسترسی همان بخش را دارد
(``core.permissions``). مالک و SUPERADMIN_IDS همه‌ی دسترسی‌ها را دارند؛ بقیه‌ی مدیرها از بخش «مدیران»
با یک نقش آماده یا دسترسی‌های دلخواه اضافه می‌شوند. همه‌ی جابه‌جایی‌های سکه از ``wallet.services`` با
کلید یکتا می‌گذرد، پس دوبار زدن هیچ دکمه‌ای دوبار سکه نمی‌دهد یا کم نمی‌کند.
"""

import asyncio
import logging
import secrets
import time
from datetime import timedelta
from html import escape

from django.db.models import Count, Sum
from django.utils import timezone
from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core import permissions, texts
from core.models import BotAdmin, TelegramGroup, TelegramUser
from core.texts import fa_num
from core.textutils import fa_date, parse_int
from games import config as game_config
from games.catalog import catalog
from games.models import ACTIVE_STATUSES, GameSetting, Match, MatchPlayer, MatchStatus
from leaderboard.queries import day_start
from wallet import economy
from wallet.models import CoinTransaction, EconomySettings, SellRequest, TopUpRequest, TxType
from wallet.services import InsufficientFunds

from .. import ui
from ..db import db
from ..tg import tg_call
from ..users import find_user
from .common import (
    admin_permissions,
    answer,
    callback,
    command,
    get_all_admin_ids,
    has_permission,
    is_owner,
    is_superadmin,
    refresh_admin_ids,
    reply,
)

logger = logging.getLogger(__name__)

MAX_GRANT = 1_000_000
LIVE_PAGE = 8


# ================================================================== دستورها
@command(permission="coins")
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
            context.bot.send_message, target.tg_id, texts.GRANT_RECEIVED.format(amount=fa_num(amount)), parse_mode="HTML"
        )


@db
def _set_banned(target_pk: int, banned: bool) -> None:
    TelegramUser.objects.filter(pk=target_pk).update(is_banned=banned)


async def _set_ban(update: Update, context, banned: bool) -> None:
    if len(context.args) != 1:
        await reply(update, texts.BAN_USAGE)
        return
    target = await find_user(context.args[0])
    if target is None:
        await reply(update, texts.USER_NOT_FOUND)
        return
    if banned and await is_superadmin(target.tg_id):
        await reply(update, texts.ADMIN_CANT_BAN_ADMIN)
        return
    await _set_banned(target.pk, banned)
    logger.info("ban changed", extra={"admin": update.effective_user.id, "target": target.tg_id, "banned": banned})
    template = texts.BAN_OK if banned else texts.UNBAN_OK
    await reply(update, template.format(name=escape(target.display_name)))


@command(permission="users")
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    await _set_ban(update, context, True)


@command(permission="users")
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


async def _launch_broadcast(context, chat_id: int, send) -> int:
    targets = await _broadcast_targets()
    await tg_call(context.bot.send_message, chat_id, texts.BROADCAST_STARTED.format(count=fa_num(len(targets))))
    context.application.create_task(_run_broadcast(context.bot, chat_id, targets, send))
    return len(targets)


def _copier(bot, from_chat_id: int, message_id: int):
    async def send(tg_id):
        return await tg_call(bot.copy_message, tg_id, from_chat_id, message_id, retries=1)

    return send


@command(permission="broadcast")
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    message = update.effective_message
    source = message.reply_to_message
    text = message.text.partition(" ")[2].strip() if message.text else ""
    if source is None and not text:
        await reply(update, texts.BROADCAST_USAGE)
        return
    bot = context.bot
    if source is not None:
        send = _copier(bot, source.chat_id, source.message_id)
    else:

        async def send(tg_id):
            return await tg_call(bot.send_message, tg_id, text, retries=1)

    await _launch_broadcast(context, update.effective_chat.id, send)


# ------------------------------------------------------------------ آمار
@db
def _stats() -> dict:
    now = timezone.now()
    today = day_start()
    week, month = now - timedelta(days=7), now - timedelta(days=30)
    finished = Match.objects.filter(status=MatchStatus.FINISHED)
    top = list(
        finished.filter(finished_at__gte=week).values("game_type").annotate(n=Count("id")).order_by("-n")[:3]
    )

    def toman(model, status, field, since):
        return model.objects.filter(status=status, reviewed_at__gte=since).aggregate(s=Sum(field))["s"] or 0

    players = MatchPlayer.objects.values("user_id").distinct()
    return {
        "users": TelegramUser.objects.count(),
        "new_today": TelegramUser.objects.filter(created_at__gte=today).count(),
        "new_week": TelegramUser.objects.filter(created_at__gte=week).count(),
        "dau": players.filter(joined_at__gte=today).count(),
        "wau": players.filter(joined_at__gte=week).count(),
        "groups": TelegramGroup.objects.filter(is_active=True).count(),
        "matches": finished.count(),
        "matches_today": finished.filter(finished_at__gte=today).count(),
        "matches_week": finished.filter(finished_at__gte=week).count(),
        "live": Match.objects.filter(status__in=ACTIVE_STATUSES).count(),
        "top_games": [(row["game_type"], row["n"]) for row in top],
        "coins": TelegramUser.objects.aggregate(s=Sum("coins"))["s"] or 0,
        "topup": [toman(TopUpRequest, TopUpRequest.Status.APPROVED, "total_toman", t) for t in (today, week, month)],
        "sell": [toman(SellRequest, SellRequest.Status.PAID, "amount_toman", t) for t in (today, week, month)],
    }


def _stats_text(data: dict) -> str:
    games = catalog(include_disabled=True)
    top = "، ".join(
        f"{games[key].emoji} {games[key].title_fa} ({fa_num(n)})" if key in games else key for key, n in data["top_games"]
    )
    return texts.ADMIN_STATS.format(
        users=fa_num(data["users"]),
        new_today=fa_num(data["new_today"]),
        new_week=fa_num(data["new_week"]),
        dau=fa_num(data["dau"]),
        wau=fa_num(data["wau"]),
        groups=fa_num(data["groups"]),
        matches=fa_num(data["matches"]),
        matches_today=fa_num(data["matches_today"]),
        matches_week=fa_num(data["matches_week"]),
        live=fa_num(data["live"]),
        top_games=top or "—",
        coins=fa_num(data["coins"]),
        topup_today=fa_num(data["topup"][0]),
        topup_week=fa_num(data["topup"][1]),
        topup_month=fa_num(data["topup"][2]),
        sell_today=fa_num(data["sell"][0]),
        sell_week=fa_num(data["sell"][1]),
        sell_month=fa_num(data["sell"][2]),
    )


@command(permission="stats")
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    await reply(update, _stats_text(await _stats()))


@command(permission="admins")
async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    """/backup — پشتیبان همین حالا در پیوی همین مدیر."""
    from ..backup import send_backup

    await reply(update, texts.BACKUP_STARTED)
    try:
        sent = await send_backup(context.bot, [user.tg_id])
    except Exception:
        logger.exception("manual backup failed")
        sent = 0
    if not sent:
        await reply(update, texts.BACKUP_FAILED)


# ================================================================== پنل مدیریت ربات (/admin)
def _btn(text: str, data: str, style: str = ""):
    return ui.button(text, data, style=style)


def _back_to_panel() -> list:
    return [_btn(texts.ADMIN_BACK_TO_PANEL_BTN, "adm:home")]


def _markup(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([list(row) for row in rows if row])


def _pairs(buttons: list) -> list[list]:
    return [buttons[i : i + 2] for i in range(0, len(buttons), 2)]


@db
def _panel_numbers() -> dict:
    today = day_start()
    pending_topups = TopUpRequest.objects.filter(status=TopUpRequest.Status.PENDING)
    pending_sells = SellRequest.objects.filter(status=SellRequest.Status.PENDING)
    approved = TopUpRequest.objects.filter(status=TopUpRequest.Status.APPROVED, reviewed_at__gte=today).aggregate(
        n=Count("id"), toman=Sum("total_toman")
    )
    paid = SellRequest.objects.filter(status=SellRequest.Status.PAID, reviewed_at__gte=today).aggregate(
        n=Count("id"), toman=Sum("amount_toman")
    )
    return {
        "eco": EconomySettings.load(),
        "topups": pending_topups.count(),
        "sells": pending_sells.count(),
        "sells_toman": pending_sells.aggregate(s=Sum("amount_toman"))["s"] or 0,
        "approved": approved,
        "paid": paid,
        "live": Match.objects.filter(status__in=ACTIVE_STATUSES).count(),
        "users": TelegramUser.objects.count(),
        "dau": MatchPlayer.objects.filter(joined_at__gte=today).values("user_id").distinct().count(),
        "coins": TelegramUser.objects.aggregate(s=Sum("coins"))["s"] or 0,
    }


async def _role_label(tg_id: int, perms: frozenset[str]) -> str:
    return texts.ADMIN_ROLE_OWNER if is_owner(tg_id) else texts.ADMIN_ROLE.format(role=permissions.role_name(perms))


async def admin_panel_screen(user: TelegramUser):
    perms = await admin_permissions(user.tg_id)
    data = await _panel_numbers()
    eco = data["eco"]
    body = ""
    if "payments" in perms:
        body += texts.ADMIN_PANEL_PAYMENTS.format(
            topups=fa_num(data["topups"]),
            sells=fa_num(data["sells"]),
            sells_toman=fa_num(data["sells_toman"]),
            approved=fa_num(data["approved"]["n"] or 0),
            approved_toman=fa_num(data["approved"]["toman"] or 0),
            paid=fa_num(data["paid"]["n"] or 0),
            paid_toman=fa_num(data["paid"]["toman"] or 0),
        )
    if perms & {"stats", "games", "users"}:
        body += texts.ADMIN_PANEL_LIVE.format(
            live=fa_num(data["live"]), users=fa_num(data["users"]), dau=fa_num(data["dau"]), coins=fa_num(data["coins"])
        )
    if "settings" in perms:
        body += texts.ADMIN_PANEL_SETTINGS.format(
            price=fa_num(eco.coin_price_toman),
            sell_price=fa_num(eco.coin_sell_price_toman),
            fee=fa_num(eco.topup_fee_percent),
            card=f"<code>{escape(eco.card_number)}</code>" if eco.card_number else texts.ADMIN_NOT_SET,
            daily=texts.ADMIN_ON if eco.daily_enabled else texts.ADMIN_OFF,
        )
    text = texts.ADMIN_PANEL.format(
        name=escape(user.display_name), role=await _role_label(user.tg_id, perms), body=body
    )
    buttons = []
    if "payments" in perms:
        buttons += [
            _btn(texts.ADMIN_TOPUPS_BTN.format(n=fa_num(data["topups"])), "adm:topup:list:0", ui.SUCCESS if data["topups"] else ui.PRIMARY),
            _btn(texts.ADMIN_SELLS_BTN.format(n=fa_num(data["sells"])), "adm:sellreq:list:0", ui.DANGER if data["sells"] else ui.PRIMARY),
        ]
    if perms & {"users", "coins"}:
        buttons.append(_btn(texts.ADMIN_USERS_BTN, "adm:usr:find", ui.PRIMARY))
    if "games" in perms:
        buttons.append(_btn(texts.ADMIN_GAMES_BTN, "adm:games", ui.PRIMARY))
    if "settings" in perms:
        buttons.append(_btn(texts.ADMIN_SETTINGS_BTN, "adm:settings", ui.PRIMARY))
    if "admins" in perms:
        buttons.append(_btn(texts.ADMIN_ADMINS_BTN, "adm:admins:list", ui.PRIMARY))
    if "stats" in perms:
        buttons += [_btn(texts.ADMIN_STATS_BTN, "adm:stats:show", ui.PRIMARY), _btn(texts.ADMIN_AUDIT_BTN, "adm:audit", ui.PRIMARY)]
    if "support" in perms:
        buttons.append(_btn(texts.ADMIN_MSG_BTN, "adm:msg:start", ui.PRIMARY))
    if "broadcast" in perms:
        buttons.append(_btn(texts.ADMIN_BROADCAST_BTN, "adm:bcast:prompt", ui.PRIMARY))
    rows = _pairs(buttons)
    rows.append([_btn(texts.ADMIN_REFRESH_BTN, "adm:home"), _btn(texts.ADMIN_CLOSE_BTN, "adm:close", ui.DANGER)])
    return text, InlineKeyboardMarkup(rows)


@command(superadmin=True, private=True)
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    context.user_data.pop("admin_flow", None)
    await reply(update, *await admin_panel_screen(user))


# ------------------------------------------------------------------ رسیدهای شارژ و درخواست‌های فروش
@db
def _pending(kind: str) -> list:
    model = TopUpRequest if kind == "topup" else SellRequest
    return list(model.objects.filter(status=model.Status.PENDING).select_related("user").order_by("created_at", "pk"))


def _request_card(kind: str, req, index: int, total: int) -> str:
    when = fa_date(timezone.localtime(req.created_at))
    username = f"@{escape(req.user.username)}" if req.user.username else texts.NO_USERNAME
    if kind == "topup":
        return texts.ADMIN_TOPUP_ITEM.format(
            n=fa_num(index + 1), total=fa_num(total), name=escape(req.user.display_name), username=username,
            tg_id=req.user.tg_id, coins=fa_num(req.coins), amount=fa_num(req.amount_toman), fee=fa_num(req.fee_toman),
            toman=fa_num(req.total_toman), date=when, id=fa_num(req.pk),
        )  # fmt: skip
    return texts.ADMIN_SELL_ITEM.format(
        n=fa_num(index + 1), total=fa_num(total), name=escape(req.user.display_name), username=username,
        tg_id=req.user.tg_id, coins=fa_num(req.coins), toman=fa_num(req.amount_toman), card=escape(req.card_number),
        holder=escape(req.card_holder or "—"), date=when, id=fa_num(req.pk),
    )  # fmt: skip


async def show_request_list(update, context, user: TelegramUser, query, kind: str, index: int = 0, focus: int | None = None):
    """یک درخواست در انتظار (رسید شارژ با عکسش، یا درخواست فروش) با دکمه‌های رسیدگی و قبلی/بعدی."""
    from .wallet import sell_alert_keyboard, show_photo_or_text, topup_alert_keyboard

    requests = await _pending(kind)
    if not requests:
        empty = texts.ADMIN_NO_TOPUPS if kind == "topup" else texts.ADMIN_NO_SELLS
        await show_photo_or_text(update, context, query, empty, InlineKeyboardMarkup([_back_to_panel()]))
        return
    if focus is not None:
        index = next((i for i, r in enumerate(requests) if r.pk == focus), index)
    index = max(0, min(index, len(requests) - 1))
    req = requests[index]
    if kind == "topup":
        rows = [list(row) for row in topup_alert_keyboard(req.pk, req.user.tg_id, ":p").inline_keyboard]
    else:
        rows = [list(row) for row in sell_alert_keyboard(req.pk, req.user.tg_id, ":p").inline_keyboard]
    nav, prefix = [], "adm:topup:list:" if kind == "topup" else "adm:sellreq:list:"
    if index > 0:
        nav.append(_btn(texts.ADMIN_PREV_BTN, f"{prefix}{index - 1}"))
    if index < len(requests) - 1:
        nav.append(_btn(texts.ADMIN_NEXT_BTN, f"{prefix}{index + 1}"))
    if nav:
        rows.append(nav)
    rows.append(_back_to_panel())
    photo = req.receipt_photo_id if kind == "topup" and req.receipt_photo_id else None
    await show_photo_or_text(update, context, query, _request_card(kind, req, index, len(requests)), InlineKeyboardMarkup(rows), photo)


# ------------------------------------------------------------------ کاربران
@db
def _user_by_tg(tg_id: int) -> TelegramUser | None:
    return TelegramUser.objects.filter(tg_id=tg_id).first()


@db
def _user_card_data(tg_id: int) -> dict | None:
    target = TelegramUser.objects.filter(tg_id=tg_id).first()
    if target is None:
        return None
    txs = list(CoinTransaction.objects.filter(user=target).order_by("-id")[:8])
    topups = target.topup_requests.filter(status=TopUpRequest.Status.APPROVED).aggregate(s=Sum("total_toman"))["s"] or 0
    sells = target.sell_requests.filter(status=SellRequest.Status.PAID).aggregate(s=Sum("amount_toman"))["s"] or 0
    return {"user": target, "txs": txs, "topups": topups, "sells": sells}


def _user_card(data: dict) -> str:
    target = data["user"]
    labels = dict(TxType.choices)
    lines = [
        texts.ADMIN_USER_TX.format(
            sign="+" if tx.amount > 0 else "−",
            amount=fa_num(abs(tx.amount)),
            kind=labels.get(tx.type, tx.type),
            date=fa_date(timezone.localtime(tx.created_at)),
        )
        for tx in data["txs"]
    ]
    status = texts.ADMIN_USER_BANNED if target.is_banned else texts.ADMIN_USER_ACTIVE
    if not target.started_bot:
        status += texts.ADMIN_USER_NOT_STARTED
    return texts.ADMIN_USER_CARD.format(
        name=escape(target.display_name),
        username=f"  ·  @{escape(target.username)}" if target.username else "",
        tg_id=target.tg_id,
        joined=fa_date(timezone.localtime(target.created_at)),
        coins=fa_num(target.coins),
        level=fa_num(target.level),
        games=fa_num(target.games_played),
        wins=fa_num(target.wins),
        topups=fa_num(data["topups"]),
        sells=fa_num(data["sells"]),
        status=status,
        txs="\n".join(lines) or texts.ADMIN_USER_NO_TX,
    )


async def user_card_screen(admin_tg_id: int, tg_id: int):
    data = await _user_card_data(tg_id)
    if data is None:
        return texts.ADMIN_TARGET_NOT_FOUND, _markup([_btn(texts.ADMIN_FIND_OTHER_BTN, "adm:usr:find")], _back_to_panel())
    perms = await admin_permissions(admin_tg_id)
    target = data["user"]
    rows = []
    if "coins" in perms:
        rows.append(
            [_btn(texts.ADMIN_GIVE_BTN, f"adm:usr:give:{tg_id}", ui.SUCCESS), _btn(texts.ADMIN_TAKE_BTN, f"adm:usr:take:{tg_id}", ui.DANGER)]
        )
    second = []
    if "users" in perms:
        if target.is_banned:
            second.append(_btn(texts.ADMIN_UNBAN_BTN, f"adm:usr:unban:{tg_id}", ui.SUCCESS))
        else:
            second.append(_btn(texts.ADMIN_BAN_BTN, f"adm:usr:ban:{tg_id}", ui.DANGER))
    if "support" in perms:
        second.append(_btn(texts.ADMIN_USER_DM_BTN, f"adm:dm:{tg_id}", ui.PRIMARY))
    rows.append(second)
    rows.append([_btn(texts.ADMIN_REFRESH_BTN, f"adm:usr:show:{tg_id}"), _btn(texts.ADMIN_FIND_OTHER_BTN, "adm:usr:find")])
    rows.append(_back_to_panel())
    return _user_card(data), _markup(*rows)


def _cancel_to(data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_btn(texts.WALLET_CANCEL_BTN, data, ui.DANGER)]])


# ------------------------------------------------------------------ بازی‌ها و مسابقه‌های در جریان
@db
def _games_data() -> tuple[list, int]:
    game_config.sync_rows()
    game_config.reload()
    return list(catalog(include_disabled=True).values()), Match.objects.filter(status__in=ACTIVE_STATUSES).count()


def _games_screen(games: list, live: int):
    on = sum(1 for g in games if g.enabled)
    text = texts.ADMIN_GAMES.format(on=fa_num(on), off=fa_num(len(games) - on), live=fa_num(live))
    buttons = [
        _btn(
            texts.ADMIN_GAME_BTN.format(dot="🟢" if g.enabled else "🔴", emoji=g.emoji, title=g.title_fa),
            f"adm:game:t:{g.key}",
            ui.SUCCESS if g.enabled else ui.DANGER,
        )
        for g in games
    ]
    rows = _pairs(buttons)
    rows.append([_btn(texts.ADMIN_LIVE_BTN.format(n=fa_num(live)), "adm:live:list:0", ui.PRIMARY)])
    rows.append(_back_to_panel())
    return text, InlineKeyboardMarkup(rows)


@db
def _toggle_game(key: str) -> tuple[str, bool] | None:
    info = catalog(include_disabled=True).get(key)
    if info is None:
        return None
    game_config.sync_rows()
    setting = GameSetting.objects.filter(game_key=key).first()
    if setting is None:
        return None
    setting.is_enabled = not setting.is_enabled
    setting.save(update_fields=["is_enabled", "updated_at"])
    game_config.reload()
    return info.title_fa, setting.is_enabled


def _age(moment) -> str:
    seconds = max(0, int((timezone.now() - moment).total_seconds()))
    if seconds < 60:
        return f"{fa_num(seconds)} ثانیه پیش"
    if seconds < 3600:
        return f"{fa_num(seconds // 60)} دقیقه پیش"
    return f"{fa_num(seconds // 3600)} ساعت پیش"


def _place(match) -> str:
    return escape(match.group.title or str(match.group.chat_id)) if match.group_id else texts.ADMIN_LIVE_DUEL


@db
def _live_matches() -> list:
    return list(
        Match.objects.filter(status__in=ACTIVE_STATUSES)
        .select_related("group", "creator")
        .annotate(n_players=Count("players"))
        .order_by("-created_at")
    )


def _live_screen(matches: list, page: int):
    if not matches:
        return texts.ADMIN_LIVE_EMPTY, _markup([_btn(texts.BACK_BTN, "adm:games")], _back_to_panel())
    games = catalog(include_disabled=True)
    pages = max(1, (len(matches) + LIVE_PAGE - 1) // LIVE_PAGE)
    page = max(0, min(page, pages - 1))
    chunk = matches[page * LIVE_PAGE : (page + 1) * LIVE_PAGE]
    lines, buttons = [], []
    for m in chunk:
        info = games.get(m.game_type)
        emoji, title = (info.emoji, info.title_fa) if info else ("🎮", m.game_type)
        lines.append(
            texts.ADMIN_LIVE_LINE.format(
                id=m.pk, emoji=emoji, title=title, status=texts.ADMIN_LIVE_STATUS.get(m.status, m.status),
                players=fa_num(m.n_players), pot=fa_num(m.pot), place=_place(m), age=_age(m.created_at),
            )  # fmt: skip
        )
        buttons.append(_btn(texts.ADMIN_LIVE_ITEM_BTN.format(id=m.pk, emoji=emoji, title=title), f"adm:live:show:{m.pk}"))
    rows = _pairs(buttons)
    nav = []
    if page > 0:
        nav.append(_btn(texts.ADMIN_PREV_BTN, f"adm:live:list:{page - 1}"))
    if page < pages - 1:
        nav.append(_btn(texts.ADMIN_NEXT_BTN, f"adm:live:list:{page + 1}"))
    rows += [nav, [_btn(texts.BACK_BTN, "adm:games")], _back_to_panel()]
    text = texts.ADMIN_LIVE_LIST.format(total=fa_num(len(matches)), lines="\n\n".join(lines))
    return text, _markup(*rows)


@db
def _match_detail(match_id: int):
    match = Match.objects.filter(pk=match_id).select_related("group", "creator").first()
    if match is None:
        return None, []
    names = [e.user.display_name for e in match.players.select_related("user")]
    return match, names


def _match_screen(match, names: list[str]):
    from .. import render

    info = catalog(include_disabled=True).get(match.game_type)
    emoji, title = (info.emoji, info.title_fa) if info else ("🎮", match.game_type)
    text = texts.ADMIN_LIVE_DETAIL.format(
        emoji=emoji, title=title, variant=render.variant_suffix(info, match.options) if info else "", id=match.pk,
        place=_place(match), creator=escape(match.creator.display_name),
        status=texts.ADMIN_LIVE_STATUS.get(match.status, match.status), age=_age(match.created_at),
        fee=render.fee_label(match.entry_fee), pot=fa_num(match.pot), count=fa_num(len(names)),
        players="\n".join(f"{fa_num(i)}. {escape(n)}" for i, n in enumerate(names, 1)) or "—",
    )  # fmt: skip
    rows = []
    if match.status in ACTIVE_STATUSES:
        rows.append([_btn(texts.ADMIN_LIVE_CANCEL_BTN, f"adm:live:cx:{match.pk}", ui.DANGER)])
    rows += [[_btn(texts.BACK_BTN, "adm:live:list:0")], _back_to_panel()]
    return text, _markup(*rows)


async def _cancel_live(context, match_id: int) -> bool:
    """لغو از پنل: اگر ربات همین مسابقه را اجرا می‌کند، با همان مسیر عادی (پیام گروه به‌روز می‌شود)؛
    وگرنه (مثلاً دوئل یا بعد از ری‌استارت) در دیتابیس، و ربات در چند ثانیه بعد خودش متوجه می‌شود."""
    from games.engine import services

    manager = context.application.bot_data.get("manager")
    active = manager.get(match_id) if manager is not None else None
    if active is not None:
        return await manager.cancel(active, "admin")
    await db(services.cancel_match)(match_id, "admin")
    return True


# ------------------------------------------------------------------ تنظیمات اقتصاد
def _settings_screen(eco: EconomySettings):
    text = texts.ADMIN_SETTINGS.format(
        card=f"<code>{escape(eco.card_number)}</code>" if eco.card_number else texts.ADMIN_NOT_SET,
        holder=f"<b>{escape(eco.card_holder)}</b>" if eco.card_holder else texts.ADMIN_NOT_SET,
        price=fa_num(eco.coin_price_toman),
        fee=fa_num(eco.topup_fee_percent),
        sell_price=fa_num(eco.coin_sell_price_toman),
        min_sell=fa_num(eco.min_sell_coins),
        daily=texts.ADMIN_ON if eco.daily_enabled else texts.ADMIN_OFF,
        bonus=fa_num(eco.signup_bonus),
        ref_reward=fa_num(eco.referral_reward),
        ref_every=fa_num(eco.referral_every),
    )
    daily = texts.ADMIN_DAILY_BTN.format(state=texts.ADMIN_ON if eco.daily_enabled else texts.ADMIN_OFF)
    return text, _markup(
        [_btn(texts.ADMIN_SET_CARD_BTN, "adm:set:card", ui.PRIMARY), _btn(texts.ADMIN_SET_RATE_BTN, "adm:set:rate", ui.PRIMARY)],
        [_btn(daily, "adm:daily:toggle", ui.SUCCESS if eco.daily_enabled else ui.DANGER), _btn(texts.ADMIN_BONUS_BTN, "adm:set:bonus", ui.PRIMARY)],
        [_btn(texts.ADMIN_REFERRAL_BTN, "adm:set:ref", ui.PRIMARY)],
        _back_to_panel(),
    )


@db
def _toggle_daily() -> bool:
    eco = EconomySettings.load()
    eco.daily_enabled = not eco.daily_enabled
    eco.save(update_fields=["daily_enabled", "updated_at"])
    return eco.daily_enabled


@db
def _save_economy(**fields) -> EconomySettings:
    eco = EconomySettings.load()
    for name, value in fields.items():
        setattr(eco, name, value)
    eco.save()
    return eco


# ------------------------------------------------------------------ مدیران
@db
def _admin_rows() -> list[BotAdmin]:
    return list(BotAdmin.objects.all())


@db
def _admin_row(tg_id: int) -> BotAdmin | None:
    return BotAdmin.objects.filter(tg_id=tg_id).first()


@db
def _save_admin(tg_id: int, perms: list[str], name: str = "", added_by: int | None = None) -> BotAdmin:
    row, created = BotAdmin.objects.get_or_create(
        tg_id=tg_id, defaults={"permissions": permissions.clean(perms), "name": name[:128], "added_by": added_by}
    )
    if not created:
        row.permissions = permissions.clean(perms)
        if name:
            row.name = name[:128]
        row.save(update_fields=["permissions", "name", "updated_at"])
    return row


@db
def _delete_admin(tg_id: int) -> None:
    BotAdmin.objects.filter(tg_id=tg_id).delete()


def _admin_name(row: BotAdmin) -> str:
    return escape(row.name or str(row.tg_id))


async def _admins_screen():
    from django.conf import settings

    rows_db = await _admin_rows()
    owners = "، ".join(f"<code>{x}</code>" for x in dict.fromkeys([settings.OWNER_TG_ID, *settings.SUPERADMIN_IDS]))
    text = texts.ADMIN_ADMINS_HEADER.format(owners=owners)
    if rows_db:
        text += "\n".join(
            texts.ADMIN_ADMINS_LINE.format(n=fa_num(i), name=_admin_name(r), tg_id=r.tg_id, role=permissions.role_name(r.permissions))
            for i, r in enumerate(rows_db, 1)
        )
        text += texts.ADMIN_ADMINS_HINT
    else:
        text += texts.ADMIN_ADMINS_EMPTY
    buttons = [
        [_btn(texts.ADMIN_ADMIN_ITEM_BTN.format(name=r.name or r.tg_id, role=permissions.role_name(r.permissions)), f"adm:admin:show:{r.tg_id}")]
        for r in rows_db
    ]
    buttons.append([_btn(texts.ADMIN_ADD_ADMIN_BTN, "adm:admin:add", ui.SUCCESS)])
    buttons.append(_back_to_panel())
    return text, InlineKeyboardMarkup(buttons)


def _admin_detail_screen(row: BotAdmin):
    current = set(row.permissions or [])
    text = texts.ADMIN_ADMIN_DETAIL.format(
        name=_admin_name(row), tg_id=row.tg_id, role=permissions.role_name(row.permissions),
        date=fa_date(timezone.localtime(row.created_at)),
    )  # fmt: skip
    toggles = [
        _btn(("✅ " if key in current else "⬜️ ") + label, f"adm:admin:perm:{row.tg_id}:{key}", ui.SUCCESS if key in current else "")
        for key, label in permissions.PERMISSIONS.items()
    ]
    rows = [[t] for t in toggles]
    presets = [_btn(texts.ADMIN_PRESET_BTN.format(name=name), f"adm:admin:preset:{row.tg_id}:{key}", ui.PRIMARY) for key, (name, _) in permissions.PRESETS.items()]
    rows += _pairs(presets)
    rows.append([_btn(texts.ADMIN_DEL_ADMIN_BTN, f"adm:admin:del:{row.tg_id}", ui.DANGER)])
    rows.append([_btn(texts.BACK_BTN, "adm:admins:list")])
    return text, InlineKeyboardMarkup(rows)


def _role_picker(tg_id: int, name: str):
    presets = [
        _btn(texts.ADMIN_PRESET_BTN.format(name=label), f"adm:admin:new:{tg_id}:{key}", ui.SUCCESS if key == "full" else ui.PRIMARY)
        for key, (label, _) in permissions.PRESETS.items()
    ]
    rows = _pairs(presets)
    rows.append([_btn(texts.WALLET_CANCEL_BTN, "adm:admins:list", ui.DANGER)])
    return texts.ADMIN_PICK_ROLE.format(name=escape(name), tg_id=tg_id), InlineKeyboardMarkup(rows)


# ------------------------------------------------------------------ حسابرسی
@db
def _audit() -> dict:
    from wallet.management.commands.audit_wallets import full_audit

    return full_audit()


def _audit_text(report: dict) -> str:
    lines = [f"user {pk} ({tg_id}): coins={coins} ledger={ledger}" for pk, tg_id, coins, ledger in report["wallets"]]
    lines += report["matches"] + report["requests"]
    if not lines:
        return texts.ADMIN_AUDIT_OK.format(users=fa_num(report["users"]), transactions=fa_num(report["transactions"]))
    shown = "\n".join(escape(line) for line in lines[:12]) + ("\n…" if len(lines) > 12 else "")
    return texts.ADMIN_AUDIT_BAD.format(count=fa_num(len(lines)), lines=shown)


# ================================================================== دکمه‌های پنل
# بخش ← دسترسی لازم (بخش‌های بدون دسترسی خاص برای همه‌ی مدیران باز است)
SECTION_PERMISSION = {
    "topup": "payments",
    "sellreq": "payments",
    "usr": "users",
    "games": "games",
    "game": "games",
    "live": "games",
    "settings": "settings",
    "set": "settings",
    "daily": "settings",
    "admins": "admins",
    "admin": "admins",
    "stats": "stats",
    "audit": "stats",
    "bcast": "broadcast",
    "msg": "support",
}


@callback
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, query):
    from .wallet import show_photo_or_text

    perms = await admin_permissions(user.tg_id)
    if not perms:
        await answer(query, texts.ADMIN_ONLY, alert=True)
        return
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else "home"
    sub = parts[2] if len(parts) > 2 else ""
    arg = parts[3] if len(parts) > 3 else ""
    extra = parts[4] if len(parts) > 4 else ""
    needed = SECTION_PERMISSION.get(action)
    # کاربرها: دیدن کارت با «کاربران» یا «سکه»؛ دادن/کم کردن فقط با «سکه»
    if action == "usr" and sub in ("give", "take", "gok"):
        needed = "coins"
    elif action == "usr" and sub in ("find", "show"):
        needed = None if perms & {"users", "coins"} else "users"
    if needed and needed not in perms:
        await answer(query, texts.ADMIN_NO_ACCESS, alert=True)
        return

    async def show(text, markup):
        await show_photo_or_text(update, context, query, text, markup)

    flow = context.user_data
    if action == "home":
        flow.pop("admin_flow", None)
        await answer(query)
        await show(*await admin_panel_screen(user))
    elif action == "close":
        flow.pop("admin_flow", None)
        await answer(query, texts.ADMIN_PANEL_CLOSED)
        await show(texts.ADMIN_PANEL_CLOSED_TEXT, None)

    # ---------------------------------------------------------- مالی
    elif action in ("topup", "sellreq") and sub == "list":
        await answer(query)
        await show_request_list(update, context, user, query, "topup" if action == "topup" else "sell", parse_int(arg) or 0)

    # ---------------------------------------------------------- کاربران
    elif action == "usr" and sub == "find":
        flow["admin_flow"] = {"step": "find_user"}
        await answer(query)
        await show(texts.ADMIN_ASK_USER, _cancel_to("adm:home"))
    elif action == "usr" and sub == "show":
        flow.pop("admin_flow", None)
        await answer(query)
        await show(*await user_card_screen(user.tg_id, parse_int(arg) or 0))
    elif action == "usr" and sub in ("ban", "unban"):
        target = await _user_by_tg(parse_int(arg) or 0)
        if target is None:
            await answer(query, texts.ADMIN_TARGET_NOT_FOUND, alert=True)
            return
        if sub == "ban" and await is_superadmin(target.tg_id):
            await answer(query, texts.ADMIN_CANT_BAN_ADMIN, alert=True)
            return
        await _set_banned(target.pk, sub == "ban")
        logger.info("ban changed", extra={"admin": user.tg_id, "target": target.tg_id, "banned": sub == "ban"})
        note = texts.ADMIN_BANNED_ALERT if sub == "ban" else texts.ADMIN_UNBANNED_ALERT
        await answer(query, note.format(name=target.display_name))
        await show(*await user_card_screen(user.tg_id, target.tg_id))
    elif action == "usr" and sub in ("give", "take"):
        target = await _user_by_tg(parse_int(arg) or 0)
        if target is None:
            await answer(query, texts.ADMIN_TARGET_NOT_FOUND, alert=True)
            return
        flow["admin_flow"] = {"step": "grant_amount", "target": target.tg_id, "sign": 1 if sub == "give" else -1}
        await answer(query)
        await show(
            texts.ADMIN_ASK_AMOUNT.format(
                icon="➕" if sub == "give" else "➖", action=texts.ADMIN_GIVE_WORD if sub == "give" else texts.ADMIN_TAKE_WORD,
                name=escape(target.display_name), tg_id=target.tg_id, coins=fa_num(target.coins),
            ),  # fmt: skip
            _cancel_to(f"adm:usr:show:{target.tg_id}"),
        )
    elif action == "usr" and sub == "gok":
        pending = flow.get("admin_flow") or {}
        if pending.get("step") != "grant_confirm" or pending.get("token") != arg:
            await answer(query, texts.WALLET_EXPIRED, alert=True)
            return
        flow.pop("admin_flow", None)
        target = await _user_by_tg(pending["target"])
        if target is None:
            await answer(query, texts.ADMIN_TARGET_NOT_FOUND, alert=True)
            return
        amount = pending["amount"]
        try:
            # توکن دکمه‌ی تأیید کلید یکتا است: دوبار زدن یا تحویل دوباره دوبار سکه جابه‌جا نمی‌کند
            await db(economy.admin_grant)(target, amount, user.tg_id, f"panel:{pending['token']}")
        except InsufficientFunds as exc:
            await answer(query, texts.ADMIN_GRANT_LOW.format(balance=fa_num(exc.balance)), alert=True)
            await show(*await user_card_screen(user.tg_id, target.tg_id))
            return
        logger.info("admin grant", extra={"admin": user.tg_id, "target": target.tg_id, "amount": amount, "via": "panel"})
        await answer(query, texts.ADMIN_GRANT_DONE.format(balance=fa_num(target.coins)))
        if amount > 0 and target.started_bot:
            await tg_call(
                context.bot.send_message, target.tg_id, texts.GRANT_RECEIVED.format(amount=fa_num(amount)), parse_mode="HTML"
            )
        await show(*await user_card_screen(user.tg_id, target.tg_id))

    # ---------------------------------------------------------- بازی‌ها و مسابقه‌ها
    elif action == "games":
        await answer(query)
        await show(*_games_screen(*await _games_data()))
    elif action == "game" and sub == "t":
        toggled = await _toggle_game(arg)
        if toggled is None:
            await answer(query, texts.ERROR_GENERIC, alert=True)
            return
        title, enabled = toggled
        await answer(query, texts.ADMIN_GAME_TOGGLED.format(title=title, state=texts.ADMIN_ON if enabled else texts.ADMIN_OFF))
        await show(*_games_screen(*await _games_data()))
    elif action == "live" and sub == "list":
        await answer(query)
        await show(*_live_screen(await _live_matches(), parse_int(arg) or 0))
    elif action == "live" and sub == "show":
        match, names = await _match_detail(parse_int(arg) or 0)
        if match is None:
            await answer(query, texts.ADMIN_LIVE_GONE, alert=True)
            return
        await answer(query)
        await show(*_match_screen(match, names))
    elif action == "live" and sub == "cx":
        match, _ = await _match_detail(parse_int(arg) or 0)
        if match is None or match.status not in ACTIVE_STATUSES:
            await answer(query, texts.ADMIN_LIVE_GONE, alert=True)
            return
        info = catalog(include_disabled=True).get(match.game_type)
        await answer(query)
        await show(
            texts.ADMIN_LIVE_CANCEL_SURE.format(id=match.pk, title=info.title_fa if info else match.game_type),
            _markup(
                [_btn(texts.ADMIN_LIVE_CANCEL_SURE_BTN, f"adm:live:cxok:{match.pk}", ui.DANGER)],
                [_btn(texts.BACK_BTN, f"adm:live:show:{match.pk}")],
            ),
        )
    elif action == "live" and sub == "cxok":
        match_id = parse_int(arg) or 0
        match, _ = await _match_detail(match_id)
        if match is None or match.status not in ACTIVE_STATUSES:
            await answer(query, texts.ADMIN_LIVE_GONE, alert=True)
            return
        await _cancel_live(context, match_id)
        logger.info("match cancelled from panel", extra={"admin": user.tg_id, "match_id": match_id})
        await answer(query, texts.ADMIN_LIVE_CANCELLED.format(id=match_id))
        await show(*_live_screen(await _live_matches(), 0))

    # ---------------------------------------------------------- تنظیمات
    elif action == "settings":
        flow.pop("admin_flow", None)
        await answer(query)
        await show(*_settings_screen(await db(EconomySettings.load)()))
    elif action == "set" and sub == "card":
        eco = await db(EconomySettings.load)()
        flow["admin_flow"] = {"step": "set_card"}
        await answer(query)
        await show(texts.ADMIN_ASK_CARD.format(card=escape(eco.card_number or "—"), holder=escape(eco.card_holder or "—")), _cancel_to("adm:settings"))
    elif action == "set" and sub == "rate":
        eco = await db(EconomySettings.load)()
        flow["admin_flow"] = {"step": "set_rate"}
        await answer(query)
        await show(
            texts.ADMIN_ASK_RATE.format(
                price=fa_num(eco.coin_price_toman), fee=fa_num(eco.topup_fee_percent),
                min_sell=fa_num(eco.min_sell_coins), sell_price=fa_num(eco.coin_sell_price_toman),
            ),  # fmt: skip
            _cancel_to("adm:settings"),
        )
    elif action == "set" and sub == "bonus":
        eco = await db(EconomySettings.load)()
        flow["admin_flow"] = {"step": "set_bonus"}
        await answer(query)
        await show(texts.ADMIN_ASK_BONUS.format(bonus=fa_num(eco.signup_bonus)), _cancel_to("adm:settings"))
    elif action == "set" and sub == "ref":
        eco = await db(EconomySettings.load)()
        flow["admin_flow"] = {"step": "set_ref"}
        await answer(query)
        await show(texts.ADMIN_ASK_REFERRAL.format(reward=fa_num(eco.referral_reward), every=fa_num(eco.referral_every)), _cancel_to("adm:settings"))
    elif action == "daily" and sub == "toggle":
        enabled = await _toggle_daily()
        await answer(query, texts.ADMIN_DAILY_TOGGLED.format(state=texts.ADMIN_ON if enabled else texts.ADMIN_OFF))
        await show(*_settings_screen(await db(EconomySettings.load)()))

    # ---------------------------------------------------------- مدیران
    elif action == "admins":
        flow.pop("admin_flow", None)
        await answer(query)
        await show(*await _admins_screen())
    elif action == "admin" and sub == "add":
        flow["admin_flow"] = {"step": "add_admin"}
        await answer(query)
        await show(texts.ADMIN_ASK_NEW_ADMIN, _cancel_to("adm:admins:list"))
    elif action == "admin" and sub == "new":
        target_id = parse_int(arg) or 0
        preset = permissions.PRESETS.get(extra)
        if target_id <= 0 or preset is None or is_owner(target_id):
            await answer(query, texts.WALLET_EXPIRED, alert=True)
            return
        known = await _user_by_tg(target_id)
        name = known.display_name if known else ""
        await _save_admin(target_id, list(preset[1]), name, user.tg_id)
        await refresh_admin_ids()
        flow.pop("admin_flow", None)
        logger.info("admin added", extra={"admin": user.tg_id, "target": target_id, "role": extra})
        await answer(query, texts.ADMIN_PERMS_SAVED)
        if known is not None and known.started_bot:
            await tg_call(context.bot.send_message, target_id, texts.ADMIN_NEW_ADMIN_NOTE.format(role=preset[0]), parse_mode="HTML")
        await show(texts.ADMIN_ADDED.format(name=escape(name or str(target_id)), tg_id=target_id, role=preset[0]), _markup([_btn(texts.ADMIN_ADMINS_BTN, "adm:admins:list", ui.PRIMARY)]))
    elif action == "admin" and sub in ("show", "perm", "preset", "del", "delok"):
        row = await _admin_row(parse_int(arg) or 0)
        if row is None:
            await answer(query, texts.WALLET_EXPIRED, alert=True)
            await show(*await _admins_screen())
            return
        current = list(row.permissions or [])
        if sub == "perm":
            if extra not in permissions.PERMISSIONS:
                return
            if extra == "admins" and not is_owner(user.tg_id):
                await answer(query, texts.ADMIN_ONLY_OWNER, alert=True)
                return
            current = [p for p in current if p != extra] if extra in current else current + [extra]
            row = await _save_admin(row.tg_id, current)
            await refresh_admin_ids()
            await answer(query, texts.ADMIN_PERMS_SAVED)
        elif sub == "preset":
            preset = permissions.PRESETS.get(extra)
            if preset is None:
                return
            # نقش آماده دسترسی «مدیران» را نمی‌دهد؛ اگر مالک قبلاً داده بود فقط خودش می‌تواند بگیرد
            keep = ["admins"] if "admins" in current and not is_owner(user.tg_id) else []
            row = await _save_admin(row.tg_id, list(preset[1]) + keep)
            await refresh_admin_ids()
            await answer(query, texts.ADMIN_PERMS_SAVED)
        elif sub == "del":
            if "admins" in current and not is_owner(user.tg_id):
                await answer(query, texts.ADMIN_ONLY_OWNER, alert=True)
                return
            await answer(query)
            await show(
                texts.ADMIN_DEL_SURE.format(name=_admin_name(row), tg_id=row.tg_id),
                _markup(
                    [_btn(texts.ADMIN_DEL_SURE_BTN, f"adm:admin:delok:{row.tg_id}", ui.DANGER)],
                    [_btn(texts.BACK_BTN, f"adm:admin:show:{row.tg_id}")],
                ),
            )
            return
        elif sub == "delok":
            if "admins" in current and not is_owner(user.tg_id):
                await answer(query, texts.ADMIN_ONLY_OWNER, alert=True)
                return
            await _delete_admin(row.tg_id)
            await refresh_admin_ids()
            logger.info("admin removed", extra={"admin": user.tg_id, "target": row.tg_id})
            await answer(query, texts.ADMIN_REMOVED.format(tg_id=row.tg_id))
            await show(*await _admins_screen())
            return
        else:
            await answer(query)
        await show(*_admin_detail_screen(row))

    # ---------------------------------------------------------- آمار، حسابرسی، پیام‌ها
    elif action == "stats":
        await answer(query)
        await show(_stats_text(await _stats()), InlineKeyboardMarkup([_back_to_panel()]))
    elif action == "audit":
        await answer(query, texts.ADMIN_AUDIT_RUNNING)
        await show(_audit_text(await _audit()), _markup([_btn(texts.ADMIN_REFRESH_BTN, "adm:audit")], _back_to_panel()))
    elif action == "msg" and sub == "start":
        flow["admin_flow"] = {"step": "ask_msg_target"}
        await answer(query)
        await show(texts.ADMIN_ASK_MSG_TARGET, InlineKeyboardMarkup([_back_to_panel()]))
    elif action == "bcast" and sub == "prompt":
        flow["admin_flow"] = {"step": "broadcast"}
        await answer(query)
        await show(texts.ADMIN_ASK_BROADCAST, _cancel_to("adm:home"))
    elif action == "bcast" and sub == "go":
        pending = flow.pop("admin_flow", None) or {}
        if pending.get("step") != "broadcast_ready":
            await answer(query, texts.WALLET_EXPIRED, alert=True)
            return
        await answer(query)
        await show(texts.ADMIN_BROADCAST_QUEUED, InlineKeyboardMarkup([_back_to_panel()]))
        await _launch_broadcast(context, update.effective_chat.id, _copier(context.bot, pending["chat_id"], pending["message_id"]))


# ================================================================== پیام‌های پیوی مدیر (مرحله‌های پنل)
# مرحله ← دسترسی لازم
STEP_PERMISSION = {
    "sell_receipt": "payments",
    "set_card": "settings",
    "set_rate": "settings",
    "set_bonus": "settings",
    "set_ref": "settings",
    "add_admin": "admins",
    "broadcast": "broadcast",
    "broadcast_ready": "broadcast",
    "ask_msg_target": "support",
    "send_dm": "support",
    "find_user": None,  # با «کاربران» یا «سکه»
    "grant_amount": "coins",
    "grant_confirm": "coins",
}


async def admin_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser) -> bool:
    from .wallet import notify_sell_paid, update_all_admin_alerts

    flow = context.user_data.get("admin_flow")
    if not flow:
        return False
    perms = await admin_permissions(user.tg_id)
    step = flow.get("step")
    if step in STEP_PERMISSION:
        needed = STEP_PERMISSION[step]
        allowed = needed in perms if needed else bool(perms & {"users", "coins"})
    else:
        allowed = bool(perms)
    if not allowed:
        context.user_data.pop("admin_flow", None)
        return False
    message = update.effective_message
    text = (message.text or "").strip()
    panel = InlineKeyboardMarkup([_back_to_panel()])

    if text in texts.CANCEL_WORDS:
        context.user_data.pop("admin_flow", None)
        await reply(update, texts.ADMIN_FLOW_CANCELLED, panel)
        return True

    if step == "sell_receipt":
        file_id = message.photo[-1].file_id if message.photo else (message.document.file_id if message.document else None)
        if not file_id:
            await reply(update, texts.ADMIN_SEND_RECEIPT_PHOTO)
            return True
        context.user_data.pop("admin_flow", None)
        review = await db(services_mark_paid)(flow.get("req_id"), user.tg_id, user.display_name)
        if review is None:
            await reply(update, texts.ADMIN_REQUEST_GONE, panel)
            return True
        req = review.request
        if not review.changed:
            await reply(update, texts.ADMIN_ALREADY_REVIEWED.format(status=req.get_status_display()), panel)
            return True
        await notify_sell_paid(context, req, receipt_file_id=file_id)
        summary = texts.ADMIN_SELL_SUMMARY.format(
            id=fa_num(req.pk), name=escape(req.user.display_name), tg_id=req.user.tg_id, coins=fa_num(req.coins),
            toman=fa_num(req.amount_toman),
        )  # fmt: skip
        await update_all_admin_alerts(
            context, "sell", req.pk, summary + "\n\n" + texts.ADMIN_STATUS_PAID_RECEIPT.format(admin=escape(user.display_name))
        )
        await reply(update, texts.ADMIN_RECEIPT_SENT.format(id=fa_num(req.pk)), panel)
        return True

    settings_panel = InlineKeyboardMarkup([[_btn(texts.ADMIN_SETTINGS_BTN, "adm:settings", ui.PRIMARY)], _back_to_panel()])
    if step == "set_card":
        from wallet.services import WalletError, parse_bank_account

        try:
            number, holder = parse_bank_account(text)
        except WalletError:
            await reply(update, texts.ADMIN_BAD_CARD)
            return True
        await db(_save_card)(number, holder)
        context.user_data.pop("admin_flow", None)
        await reply(update, texts.ADMIN_CARD_SAVED.format(card=escape(number), holder=escape(holder)), settings_panel)
        return True

    if step == "set_rate":
        values = [parse_int(p) for p in text.split()]
        if len(values) < 2 or values[0] is None or values[1] is None or values[0] <= 0 or not 0 <= values[1] <= 100:
            await reply(update, texts.ADMIN_BAD_RATE)
            return True
        price, fee = values[0], values[1]
        min_sell = values[2] if len(values) > 2 and values[2] and values[2] > 0 else None
        sell_price = values[3] if len(values) > 3 and values[3] and values[3] > 0 else None
        eco = await db(_save_rates)(price, fee, min_sell, sell_price)
        context.user_data.pop("admin_flow", None)
        await reply(
            update,
            texts.ADMIN_RATE_SAVED.format(
                price=fa_num(eco.coin_price_toman), fee=fa_num(eco.topup_fee_percent),
                min_sell=fa_num(eco.min_sell_coins), sell_price=fa_num(eco.coin_sell_price_toman),
            ),  # fmt: skip
            settings_panel,
        )
        return True

    if step == "set_bonus":
        value = parse_int(text)
        if value is None or not 0 <= value <= MAX_GRANT:
            await reply(update, texts.ADMIN_BAD_NUMBERS)
            return True
        await _save_economy(signup_bonus=value)
        context.user_data.pop("admin_flow", None)
        await reply(update, texts.ADMIN_SAVED, settings_panel)
        return True

    if step == "set_ref":
        values = [parse_int(p) for p in text.split()]
        if len(values) != 2 or None in values or not 0 <= values[0] <= MAX_GRANT or not 1 <= values[1] <= 10_000:
            await reply(update, texts.ADMIN_BAD_NUMBERS)
            return True
        await _save_economy(referral_reward=values[0], referral_every=values[1])
        context.user_data.pop("admin_flow", None)
        await reply(update, texts.ADMIN_SAVED, settings_panel)
        return True

    if step == "add_admin":
        target = await find_user(text) if text else None
        new_id = target.tg_id if target else parse_int(text)
        if new_id is None or new_id <= 0:
            await reply(update, texts.ADMIN_BAD_ADMIN_ID)
            return True
        if is_owner(new_id):
            await reply(update, texts.ADMIN_ALREADY_OWNER, InlineKeyboardMarkup([[_btn(texts.ADMIN_ADMINS_BTN, "adm:admins:list", ui.PRIMARY)]]))
            context.user_data.pop("admin_flow", None)
            return True
        context.user_data["admin_flow"] = {"step": "pick_role", "target": new_id}
        await reply(update, *_role_picker(new_id, target.display_name if target else str(new_id)))
        return True

    if step == "find_user":
        target = await find_user(text) if text else None
        if target is None:
            await reply(update, texts.ADMIN_TARGET_NOT_FOUND)
            return True
        context.user_data.pop("admin_flow", None)
        await reply(update, *await user_card_screen(user.tg_id, target.tg_id))
        return True

    if step == "grant_amount":
        amount = parse_int(text)
        if amount is None or not 0 < amount <= MAX_GRANT:
            await reply(update, texts.ADMIN_BAD_AMOUNT)
            return True
        target = await _user_by_tg(flow["target"])
        if target is None:
            context.user_data.pop("admin_flow", None)
            await reply(update, texts.ADMIN_TARGET_NOT_FOUND, panel)
            return True
        signed = amount * flow["sign"]
        if target.coins + signed < 0:
            await reply(update, texts.ADMIN_GRANT_LOW.format(balance=fa_num(target.coins)))
            return True
        token = secrets.token_hex(6)
        context.user_data["admin_flow"] = {"step": "grant_confirm", "target": target.tg_id, "amount": signed, "token": token}
        give = signed > 0
        await reply(
            update,
            texts.ADMIN_GRANT_CONFIRM.format(
                icon="➕" if give else "➖", amount=fa_num(amount), name=escape(target.display_name), tg_id=target.tg_id,
                side=texts.ADMIN_GRANT_TO if give else texts.ADMIN_GRANT_FROM,
                verb=texts.ADMIN_GRANT_GIVE_VERB if give else texts.ADMIN_GRANT_TAKE_VERB, after=fa_num(target.coins + signed),
            ),  # fmt: skip
            _markup(
                [_btn(texts.ADMIN_GRANT_SURE_BTN, f"adm:usr:gok:{token}", ui.SUCCESS)],
                [_btn(texts.WALLET_CANCEL_BTN, f"adm:usr:show:{target.tg_id}", ui.DANGER)],
            ),
        )
        return True

    if step == "broadcast":
        # پیام همگانی هر نوعی می‌تواند باشد (متن، عکس، فوروارد)؛ قبل از ارسال به همه یک بار تأیید می‌شود
        context.user_data["admin_flow"] = {"step": "broadcast_ready", "chat_id": message.chat_id, "message_id": message.message_id}
        count = len(await _broadcast_targets())
        await reply(
            update,
            texts.ADMIN_BROADCAST_CONFIRM.format(count=fa_num(count)),
            InlineKeyboardMarkup(
                [[_btn(texts.ADMIN_BROADCAST_GO_BTN, "adm:bcast:go", ui.SUCCESS), _btn(texts.WALLET_CANCEL_BTN, "adm:home", ui.DANGER)]]
            ),
        )
        return True

    if step == "ask_msg_target":
        target = await find_user(text) if text else None
        if target is None:
            await reply(update, texts.ADMIN_TARGET_NOT_FOUND)
            return True
        context.user_data["admin_flow"] = {"step": "send_dm", "target_tg_id": target.tg_id, "target_name": target.display_name}
        username = f" (@{escape(target.username)})" if target.username else ""
        await reply(
            update,
            texts.ADMIN_ASK_DM_TEXT.format(name=escape(target.display_name), username=username, tg_id=target.tg_id),
            _cancel_to("adm:home"),
        )
        return True

    if step == "send_dm":
        body = message.text or message.caption or ""
        file_id = message.photo[-1].file_id if message.photo else None
        if not body and not file_id:
            await reply(update, texts.ADMIN_SEND_DM_CONTENT)
            return True
        context.user_data.pop("admin_flow", None)
        target_id = flow.get("target_tg_id")
        content = texts.SUPPORT_FROM_ADMIN.format(text=escape(body))
        keyboard = InlineKeyboardMarkup([[ui.button(texts.SUPPORT_REPLY_BTN, "pm:support", style=ui.PRIMARY)]])
        if file_id:
            sent = await tg_call(context.bot.send_photo, target_id, photo=file_id, caption=content, parse_mode="HTML", reply_markup=keyboard)
        else:
            sent = await tg_call(context.bot.send_message, target_id, content, parse_mode="HTML", reply_markup=keyboard)
        name = escape(flow.get("target_name") or str(target_id))
        done = texts.ADMIN_DM_SENT if sent is not None else texts.ADMIN_DM_FAILED
        await reply(update, done.format(name=name, tg_id=target_id), panel)
        return True
    return False


def services_mark_paid(req_id, admin_tg_id: int, admin_name: str):
    """واریز با رسید؛ اگر درخواست پیدا نشد ``None``."""
    from wallet.services import mark_sell_paid

    if not SellRequest.objects.filter(pk=req_id).exists():
        return None
    return mark_sell_paid(int(req_id), admin_tg_id, admin_name, receipt=True)


def _save_card(number: str, holder: str) -> None:
    eco = EconomySettings.load()
    eco.card_number, eco.card_holder = number[:32], holder[:128]
    eco.save(update_fields=["card_number", "card_holder", "updated_at"])


def _save_rates(price: int, fee: int, min_sell: int | None, sell_price: int | None) -> EconomySettings:
    eco = EconomySettings.load()
    eco.coin_price_toman, eco.topup_fee_percent = price, fee
    if min_sell is not None:
        eco.min_sell_coins = min_sell
    if sell_price is not None:
        eco.coin_sell_price_toman = sell_price
    eco.save()
    return eco


# ------------------------------------------------------------------ پیام مدیر به کاربر و تیکت پشتیبانی
@callback
async def admin_dm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, query):
    if not await has_permission(user.tg_id, "support"):
        await answer(query, texts.ADMIN_ONLY, alert=True)
        return
    target_id = parse_int(query.data.split(":")[2]) if query.data.count(":") >= 2 else None
    if not target_id:
        return
    target = await db(TelegramUser.objects.filter(tg_id=target_id).first)()
    name = target.display_name if target else str(target_id)
    username = f" (@{escape(target.username)})" if target and target.username else ""
    context.user_data["admin_flow"] = {"step": "send_dm", "target_tg_id": target_id, "target_name": name}
    await answer(query)
    await reply(
        update,
        texts.ADMIN_ASK_DM_TEXT.format(name=escape(name), username=username, tg_id=target_id),
        _cancel_to("adm:home"),
    )


async def user_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser) -> bool:
    if not context.user_data.get("support_flow"):
        return False
    message = update.effective_message
    body = (message.text or message.caption or "").strip()
    file_id = message.photo[-1].file_id if message.photo else (message.document.file_id if message.document else None)
    if body in texts.CANCEL_WORDS:
        context.user_data.pop("support_flow", None)
        await reply(update, texts.SUPPORT_CANCELLED)
        return True
    if not body and not file_id:
        await reply(update, texts.SUPPORT_SEND_CONTENT)
        return True
    context.user_data.pop("support_flow", None)
    username = f"@{escape(user.username)}" if user.username else texts.NO_USERNAME
    ticket = texts.SUPPORT_TICKET.format(
        mention=f'<a href="tg://user?id={user.tg_id}">{escape(user.display_name)}</a>',
        username=username,
        tg_id=user.tg_id,
        date=fa_date(timezone.localtime(timezone.now())),
        coins=fa_num(user.coins),
        text=escape(body) or "—",
    )
    keyboard = InlineKeyboardMarkup([[_btn(texts.SUPPORT_ANSWER_BTN, f"adm:dm:{user.tg_id}", ui.PRIMARY)]])
    delivered = 0
    # تیکت فقط به مدیرانی می‌رسد که دسترسی پشتیبانی دارند
    for admin_id in await get_all_admin_ids("support"):
        if file_id and message.photo:
            sent = await tg_call(context.bot.send_photo, admin_id, photo=file_id, caption=ticket, parse_mode="HTML", reply_markup=keyboard)
        elif file_id:
            sent = await tg_call(context.bot.send_document, admin_id, document=file_id, caption=ticket, parse_mode="HTML", reply_markup=keyboard)
        else:
            sent = await tg_call(context.bot.send_message, admin_id, ticket, parse_mode="HTML", reply_markup=keyboard)
        delivered += sent is not None
    await reply(update, texts.SUPPORT_SENT if delivered else texts.SUPPORT_FAILED)
    return True

