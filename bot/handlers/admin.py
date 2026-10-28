"""دستورات سوپرادمین: /grant /ban /unban /broadcast /stats"""

import asyncio
import logging
import time
from html import escape

from django.db.models import Count, Sum
from django.utils import timezone
from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core import texts
from core.models import TelegramGroup, TelegramUser
from core.texts import fa_num
from core.textutils import fa_date, parse_int
from games.catalog import catalog
from games.models import Match, MatchPlayer, MatchStatus
from leaderboard.queries import day_start
from wallet import economy
from wallet.models import EconomySettings, SellRequest, TopUpRequest
from wallet.services import InsufficientFunds

from .. import ui
from ..db import db
from ..tg import tg_call
from ..users import find_user
from .common import answer, callback, command, is_superadmin, reply

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


async def _launch_broadcast(context, chat_id: int, send) -> int:
    targets = await _broadcast_targets()
    await tg_call(context.bot.send_message, chat_id, texts.BROADCAST_STARTED.format(count=fa_num(len(targets))))
    context.application.create_task(_run_broadcast(context.bot, chat_id, targets, send))
    return len(targets)


def _copier(bot, from_chat_id: int, message_id: int):
    async def send(tg_id):
        return await tg_call(bot.copy_message, tg_id, from_chat_id, message_id, retries=1)

    return send


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
        send = _copier(bot, source.chat_id, source.message_id)
    else:

        async def send(tg_id):
            return await tg_call(bot.send_message, tg_id, text, retries=1)

    await _launch_broadcast(context, update.effective_chat.id, send)


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




# ================================================================== پنل مدیریت ربات (/admin)
def _btn(text: str, data: str, style: str = ""):
    return ui.button(text, data, style=style)


def _back_to_panel() -> list:
    return [_btn(texts.ADMIN_BACK_TO_PANEL_BTN, "adm:home")]


@db
def _panel_numbers() -> dict:
    today = day_start()
    pending_topups = TopUpRequest.objects.filter(status=TopUpRequest.Status.PENDING)
    pending_sells = SellRequest.objects.filter(status=SellRequest.Status.PENDING)
    approved = TopUpRequest.objects.filter(status=TopUpRequest.Status.APPROVED, reviewed_at__gte=today).aggregate(
        n=Count("id"), coins=Sum("coins"), toman=Sum("total_toman")
    )
    paid = SellRequest.objects.filter(status=SellRequest.Status.PAID, reviewed_at__gte=today).aggregate(
        n=Count("id"), coins=Sum("coins"), toman=Sum("amount_toman")
    )
    return {
        "eco": EconomySettings.load(),
        "topups": pending_topups.count(),
        "sells": pending_sells.count(),
        "sells_toman": pending_sells.aggregate(s=Sum("amount_toman"))["s"] or 0,
        "approved": approved,
        "paid": paid,
    }


async def admin_panel_screen(user: TelegramUser):
    from .common import get_all_admin_ids

    data = await _panel_numbers()
    eco = data["eco"]
    text = texts.ADMIN_PANEL.format(
        name=escape(user.display_name),
        tg_id=user.tg_id,
        card=f"<code>{escape(eco.card_number)}</code>" if eco.card_number else texts.ADMIN_NOT_SET,
        holder=f"<b>{escape(eco.card_holder)}</b>" if eco.card_holder else texts.ADMIN_NOT_SET,
        price=fa_num(eco.coin_price_toman),
        fee=fa_num(eco.topup_fee_percent),
        sell_price=fa_num(eco.coin_sell_price_toman),
        min_sell=fa_num(eco.min_sell_coins),
        daily=texts.ADMIN_ON if eco.daily_enabled else texts.ADMIN_OFF,
        topups=fa_num(data["topups"]),
        sells=fa_num(data["sells"]),
        sells_toman=fa_num(data["sells_toman"]),
        approved=fa_num(data["approved"]["n"] or 0),
        approved_toman=fa_num(data["approved"]["toman"] or 0),
        paid=fa_num(data["paid"]["n"] or 0),
        paid_toman=fa_num(data["paid"]["toman"] or 0),
        admins=fa_num(len(await get_all_admin_ids())),
    )
    rows = [
        [
            _btn(texts.ADMIN_TOPUPS_BTN.format(n=fa_num(data["topups"])), "adm:topup:list:0", ui.SUCCESS if data["topups"] else ui.PRIMARY),
            _btn(texts.ADMIN_SELLS_BTN.format(n=fa_num(data["sells"])), "adm:sellreq:list:0", ui.DANGER if data["sells"] else ui.PRIMARY),
        ],
        [_btn(texts.ADMIN_SET_CARD_BTN, "adm:set:card", ui.PRIMARY), _btn(texts.ADMIN_SET_RATE_BTN, "adm:set:rate", ui.PRIMARY)],
        [
            _btn(texts.ADMIN_DAILY_BTN.format(state=texts.ADMIN_ON if eco.daily_enabled else texts.ADMIN_OFF), "adm:daily:toggle", ui.SUCCESS if eco.daily_enabled else ui.DANGER),
            _btn(texts.ADMIN_ADMINS_BTN, "adm:admins:list", ui.PRIMARY),
        ],
        [_btn(texts.ADMIN_STATS_BTN, "adm:stats:show", ui.PRIMARY), _btn(texts.ADMIN_MSG_BTN, "adm:msg:start", ui.PRIMARY)],
        [_btn(texts.ADMIN_BROADCAST_BTN, "adm:bcast:prompt", ui.PRIMARY)],
        [_btn(texts.ADMIN_REFRESH_BTN, "adm:home"), _btn(texts.ADMIN_CLOSE_BTN, "adm:close", ui.DANGER)],
    ]
    return text, InlineKeyboardMarkup(rows)


@command(superadmin=True, private=True)
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    context.user_data.pop("admin_flow", None)
    await reply(update, *await admin_panel_screen(user))


# ------------------------------------------------------------------ فهرست رسیدهای شارژ و درخواست‌های فروش
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


# ------------------------------------------------------------------ دکمه‌های پنل
@db
def _toggle_daily() -> bool:
    eco = EconomySettings.load()
    eco.daily_enabled = not eco.daily_enabled
    eco.save(update_fields=["daily_enabled", "updated_at"])
    return eco.daily_enabled


@db
def _set_extra_admins(add: int | None = None, remove: int | None = None) -> list[int]:
    from django.db import transaction

    with transaction.atomic():
        eco = EconomySettings.objects.select_for_update().get(pk=EconomySettings.load().pk)
        ids = [int(x) for x in eco.extra_admin_ids or [] if str(x).lstrip("-").isdigit()]
        if add is not None and add not in ids:
            ids.append(add)
        if remove is not None and remove in ids:
            ids.remove(remove)
        eco.extra_admin_ids = ids
        eco.save(update_fields=["extra_admin_ids", "updated_at"])
    return ids


def _admins_screen(extra: list[int]):
    from django.conf import settings

    text = texts.ADMIN_ADMINS_HEADER.format(owner=settings.OWNER_TG_ID)
    if extra:
        text += "\n".join(texts.ADMIN_ADMINS_LINE.format(n=fa_num(i), tg_id=aid) for i, aid in enumerate(extra, 1))
    else:
        text += texts.ADMIN_ADMINS_EMPTY
    rows = [[_btn(texts.ADMIN_ADD_ADMIN_BTN, "adm:admin:add", ui.SUCCESS)]]
    if extra:
        rows.append([_btn(texts.ADMIN_DEL_ADMIN_BTN, "adm:admin:delselect", ui.DANGER)])
    rows.append(_back_to_panel())
    return text, InlineKeyboardMarkup(rows)


@db
def _extra_admin_list() -> list[int]:
    return [int(x) for x in EconomySettings.load().extra_admin_ids or [] if str(x).lstrip("-").isdigit()]


def _stats_text(data: dict) -> str:
    info = catalog(include_disabled=True).get(data["top_game"]) if data["top_game"] else None
    return texts.STATS.format(
        users=fa_num(data["users"]),
        dau=fa_num(data["dau"]),
        groups=fa_num(data["groups"]),
        matches=fa_num(data["matches"]),
        matches_today=fa_num(data["matches_today"]),
        top_game=f"{info.emoji} {info.title_fa}" if info else "—",
        coins=fa_num(data["coins"]),
    )


@callback
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, query):
    from .common import refresh_admin_ids
    from .wallet import show_photo_or_text

    if not await is_superadmin(user.tg_id):
        await answer(query, texts.ADMIN_ONLY, alert=True)
        return
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else "home"
    sub = parts[2] if len(parts) > 2 else ""
    arg = parts[3] if len(parts) > 3 else ""

    async def show(text, markup):
        await show_photo_or_text(update, context, query, text, markup)

    if action == "home":
        context.user_data.pop("admin_flow", None)
        await answer(query)
        await show(*await admin_panel_screen(user))
    elif action == "close":
        context.user_data.pop("admin_flow", None)
        await answer(query, texts.ADMIN_PANEL_CLOSED)
        await show(texts.ADMIN_PANEL_CLOSED_TEXT, None)
    elif action == "msg" and sub == "start":
        context.user_data["admin_flow"] = {"step": "ask_msg_target"}
        await answer(query)
        await show(texts.ADMIN_ASK_MSG_TARGET, InlineKeyboardMarkup([_back_to_panel()]))
    elif action == "set" and sub == "card":
        eco = await db(EconomySettings.load)()
        context.user_data["admin_flow"] = {"step": "set_card"}
        await answer(query)
        await show(
            texts.ADMIN_ASK_CARD.format(card=escape(eco.card_number or "—"), holder=escape(eco.card_holder or "—")),
            InlineKeyboardMarkup([[_btn(texts.WALLET_CANCEL_BTN, "adm:home", ui.DANGER)]]),
        )
    elif action == "set" and sub == "rate":
        eco = await db(EconomySettings.load)()
        context.user_data["admin_flow"] = {"step": "set_rate"}
        await answer(query)
        await show(
            texts.ADMIN_ASK_RATE.format(
                price=fa_num(eco.coin_price_toman), fee=fa_num(eco.topup_fee_percent),
                min_sell=fa_num(eco.min_sell_coins), sell_price=fa_num(eco.coin_sell_price_toman),
            ),  # fmt: skip
            InlineKeyboardMarkup([[_btn(texts.WALLET_CANCEL_BTN, "adm:home", ui.DANGER)]]),
        )
    elif action == "daily" and sub == "toggle":
        enabled = await _toggle_daily()
        await answer(query, texts.ADMIN_DAILY_TOGGLED.format(state=texts.ADMIN_ON if enabled else texts.ADMIN_OFF))
        await show(*await admin_panel_screen(user))
    elif action == "admins":
        await answer(query)
        await show(*_admins_screen(await _extra_admin_list()))
    elif action == "admin" and sub == "add":
        context.user_data["admin_flow"] = {"step": "add_admin"}
        await answer(query)
        await show(texts.ADMIN_ASK_NEW_ADMIN, InlineKeyboardMarkup([[_btn(texts.WALLET_CANCEL_BTN, "adm:admins:list", ui.DANGER)]]))
    elif action == "admin" and sub == "delselect":
        extra = await _extra_admin_list()
        rows = [[_btn(texts.ADMIN_DEL_ONE_BTN.format(tg_id=aid), f"adm:admin:del:{aid}", ui.DANGER)] for aid in extra]
        rows.append([_btn(texts.BACK_BTN, "adm:admins:list")])
        await answer(query)
        await show(texts.ADMIN_PICK_TO_DELETE, InlineKeyboardMarkup(rows))
    elif action == "admin" and sub == "del":
        target = parse_int(arg)
        extra = await _set_extra_admins(remove=target) if target else await _extra_admin_list()
        await refresh_admin_ids()
        await answer(query, texts.ADMIN_REMOVED.format(tg_id=target or "—"))
        await show(*_admins_screen(extra))
    elif action in ("topup", "sellreq") and sub == "list":
        await answer(query)
        await show_request_list(update, context, user, query, "topup" if action == "topup" else "sell", parse_int(arg) or 0)
    elif action == "stats":
        await answer(query)
        await show(_stats_text(await _stats()), InlineKeyboardMarkup([_back_to_panel()]))
    elif action == "bcast" and sub == "prompt":
        context.user_data["admin_flow"] = {"step": "broadcast"}
        await answer(query)
        await show(texts.ADMIN_ASK_BROADCAST, InlineKeyboardMarkup([[_btn(texts.WALLET_CANCEL_BTN, "adm:home", ui.DANGER)]]))
    elif action == "bcast" and sub == "go":
        flow = context.user_data.pop("admin_flow", None) or {}
        if flow.get("step") != "broadcast_ready":
            await answer(query, texts.WALLET_EXPIRED, alert=True)
            return
        await answer(query)
        await show(texts.ADMIN_BROADCAST_QUEUED, InlineKeyboardMarkup([_back_to_panel()]))
        await _launch_broadcast(context, update.effective_chat.id, _copier(context.bot, flow["chat_id"], flow["message_id"]))


# ------------------------------------------------------------------ پیام‌های پیوی مدیر (مرحله‌های پنل)
async def admin_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser) -> bool:
    from .common import refresh_admin_ids
    from .wallet import notify_sell_paid, update_all_admin_alerts

    flow = context.user_data.get("admin_flow")
    if not flow or not await is_superadmin(user.tg_id):
        return False
    step = flow.get("step")
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

    if step == "set_card":
        from wallet.services import WalletError, parse_bank_account

        try:
            number, holder = parse_bank_account(text)
        except WalletError:
            await reply(update, texts.ADMIN_BAD_CARD)
            return True
        await db(_save_card)(number, holder)
        context.user_data.pop("admin_flow", None)
        await reply(update, texts.ADMIN_CARD_SAVED.format(card=escape(number), holder=escape(holder)), panel)
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
            panel,
        )
        return True

    if step == "add_admin":
        new_id = parse_int(text)
        if new_id is None or new_id <= 0:
            await reply(update, texts.ADMIN_BAD_ADMIN_ID)
            return True
        await db(_set_extra_admins)(add=new_id)
        await refresh_admin_ids()
        context.user_data.pop("admin_flow", None)
        await reply(
            update,
            texts.ADMIN_ADDED.format(tg_id=new_id),
            InlineKeyboardMarkup([[_btn(texts.ADMIN_ADMINS_BTN, "adm:admins:list", ui.PRIMARY)]]),
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
            InlineKeyboardMarkup([[_btn(texts.WALLET_CANCEL_BTN, "adm:home", ui.DANGER)]]),
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
    if not await is_superadmin(user.tg_id):
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
        InlineKeyboardMarkup([[_btn(texts.WALLET_CANCEL_BTN, "adm:home", ui.DANGER)]]),
    )


async def user_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser) -> bool:
    from .common import get_all_admin_ids

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
    for admin_id in await get_all_admin_ids():
        if file_id and message.photo:
            sent = await tg_call(context.bot.send_photo, admin_id, photo=file_id, caption=ticket, parse_mode="HTML", reply_markup=keyboard)
        elif file_id:
            sent = await tg_call(context.bot.send_document, admin_id, document=file_id, caption=ticket, parse_mode="HTML", reply_markup=keyboard)
        else:
            sent = await tg_call(context.bot.send_message, admin_id, ticket, parse_mode="HTML", reply_markup=keyboard)
        delivered += sent is not None
    await reply(update, texts.SUPPORT_SENT if delivered else texts.SUPPORT_FAILED)
    return True
