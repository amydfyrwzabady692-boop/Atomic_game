"""کیف پول: شارژ با رسید کارت‌به‌کارت، فروش سکه (تسویه)، انتقال سکه بین کاربران و بررسی ادمین‌ها.

همه‌ی جابه‌جایی‌های سکه از ``wallet.services`` می‌گذرد (اتمیک و با کلید یکتای ledger):

- انتقال همیشه یک مرحله‌ی تأیید با دکمه دارد. کلید یکتای انتقال همان توکن دکمه است؛ پس دوبار زدن دکمه،
  تحویل دوباره‌ی همان کلیک یا ری‌استارت ربات هرگز سکه را دوبار جابه‌جا نمی‌کند.
- فروش سکه هم قبل از کسر، شماره کارت و مبلغ را برای تأیید نشان می‌دهد؛ کسر سکه و ثبت درخواست با هم انجام می‌شوند.
- تأیید/رد رسید شارژ و واریز/رد فروش فقط یک بار اثر دارد، حتی اگر چند ادمین هم‌زمان کلیک کنند؛ پیام هشدار
  همه‌ی ادمین‌ها هم با نتیجه به‌روز می‌شود.
"""

import json
import logging
import secrets
from html import escape

from django.conf import settings
from django.utils import timezone
from telegram import InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from core import texts
from core.models import TelegramUser
from core.redis import get_redis
from core.texts import fa_num
from core.textutils import fa_date, parse_int
from wallet import services
from wallet.models import EconomySettings, SellRequest, TopUpRequest
from wallet.services import InsufficientFunds, WalletError

from .. import render, ui
from ..db import db
from ..tg import tg_call
from ..users import ensure_user, find_user
from .common import answer, callback, command, get_all_admin_ids, is_superadmin, reply

logger = logging.getLogger(__name__)

TOPUP_PACKAGES = (50, 100, 200, 500)
SELL_PACKAGES = (100, 200, 500)
TRANSFER_TTL = 120  # ثانیه؛ دکمه‌ی تأیید انتقال بعد از این مدت منقضی می‌شود
ALERTS_TTL = 7 * 86400


def _btn(text: str, data: str, style: str = ""):
    return ui.button(text, data, style=style)


def _keyboard(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([list(row) for row in rows])


def _cancel(data: str) -> InlineKeyboardMarkup:
    return _keyboard([_btn(texts.WALLET_CANCEL_BTN, data, ui.DANGER)])


def _mention(user: TelegramUser) -> str:
    return f'<a href="tg://user?id={user.tg_id}">{escape(user.display_name)}</a>'


def _username(user: TelegramUser) -> str:
    return f"@{escape(user.username)}" if user.username else texts.NO_USERNAME


def wallet_error_text(exc: WalletError) -> str:
    template = texts.WALLET_ERRORS.get(exc.code, texts.ERROR_GENERIC)
    return template.format(**{k: fa_num(v) for k, v in exc.context.items()})


# ------------------------------------------------------------------ صفحه‌ها
def wallet_screen(user: TelegramUser):
    rows = [
        [_btn(texts.WALLET_TOPUP_BTN, "wal:topup:menu", ui.SUCCESS), _btn(texts.WALLET_SELL_BTN, "wal:sell:menu", ui.PRIMARY)],
        [_btn(texts.WALLET_TRANSFER_BTN, "wal:trans:menu", ui.PRIMARY), _btn(texts.WALLET_HISTORY_BTN, "pm:history", ui.PRIMARY)],
        [_btn(texts.BACK_BTN, "pm:back")],
    ]
    return texts.WALLET_HEADER.format(coins=fa_num(user.coins)), InlineKeyboardMarkup(rows)


def topup_menu_screen(eco: EconomySettings):
    rows = []
    for count in TOPUP_PACKAGES:
        quote = services.topup_quote(count, eco)
        label = texts.WALLET_PACKAGE_BTN.format(coins=fa_num(count), toman=fa_num(quote.total))
        rows.append([_btn(label, f"wal:topup:p:{count}", ui.PRIMARY)])
    rows.append([_btn(texts.WALLET_CUSTOM_BTN, "wal:topup:custom", ui.SUCCESS)])
    rows.append([_btn(texts.BACK_BTN, "wal:home")])
    text = texts.WALLET_TOPUP_MENU.format(price=fa_num(eco.coin_price_toman), fee_percent=fa_num(eco.topup_fee_percent))
    return text, InlineKeyboardMarkup(rows)


def topup_pay_screen(coins: int, eco: EconomySettings):
    """اطلاعات واریز. خروجی ``(متن، کیبورد، داده‌ی مرحله‌ی بعد یا None)``."""
    if not eco.card_number:
        return texts.WALLET_TOPUP_NO_CARD, _keyboard([_btn(texts.BACK_BTN, "wal:topup:menu")]), None
    quote = services.topup_quote(coins, eco)
    holder = texts.WALLET_HOLDER_LINE.format(holder=escape(eco.card_holder)) if eco.card_holder else ""
    text = texts.WALLET_TOPUP_PAY_INFO.format(
        coins=fa_num(coins),
        amount=fa_num(quote.amount),
        fee=fa_num(quote.fee),
        fee_percent=fa_num(eco.topup_fee_percent),
        total=fa_num(quote.total),
        card=escape(eco.card_number),
        holder_line=holder,
    )
    return text, _cancel("wal:topup:cancel"), {"step": "awaiting_receipt", "coins": coins}


def sell_menu_screen(user: TelegramUser, eco: EconomySettings):
    minimum, price = max(1, eco.min_sell_coins), eco.coin_sell_price_toman
    if user.coins < minimum:
        text = texts.WALLET_SELL_MIN_ERROR.format(
            min_coins=fa_num(minimum), min_amount=fa_num(minimum * price), coins=fa_num(user.coins)
        )
        return text, _keyboard([_btn(texts.BACK_BTN, "wal:home")])
    rows = []
    for count in SELL_PACKAGES:
        if minimum <= count <= user.coins:
            label = texts.WALLET_PACKAGE_BTN.format(coins=fa_num(count), toman=fa_num(count * price))
            rows.append([_btn(label, f"wal:sell:p:{count}", ui.PRIMARY)])
    everything = min(user.coins, services.MAX_REQUEST_COINS)
    if everything not in SELL_PACKAGES:
        label = texts.WALLET_SELL_ALL_BTN.format(coins=fa_num(everything), toman=fa_num(everything * price))
        rows.append([_btn(label, f"wal:sell:p:{everything}", ui.SUCCESS)])
    rows.append([_btn(texts.WALLET_CUSTOM_BTN, "wal:sell:custom", ui.PRIMARY)])
    rows.append([_btn(texts.BACK_BTN, "wal:home")])
    text = texts.WALLET_SELL_MENU.format(
        coins=fa_num(user.coins), price=fa_num(price), min_coins=fa_num(minimum), min_amount=fa_num(minimum * price)
    )
    return text, InlineKeyboardMarkup(rows)


def _sell_amount_error(user: TelegramUser, eco: EconomySettings, coins) -> str | None:
    minimum = max(1, eco.min_sell_coins)
    if coins is None or coins < minimum or coins > min(user.coins, services.MAX_REQUEST_COINS):
        return texts.WALLET_SELL_BAD_AMOUNT.format(
            min_coins=fa_num(minimum), max_coins=fa_num(max(minimum, min(user.coins, services.MAX_REQUEST_COINS)))
        )
    return None


# ------------------------------------------------------------------ دستورات و دکمه‌ها
SECTIONS = ("wallet", "topup", "sell", "transfer")


async def open_section(update: Update, context, user: TelegramUser, section: str) -> None:
    """یک بخش کیف پول را با پیام تازه باز می‌کند (دکمه‌های کیف پول مینی‌اپ: /start topup و …)."""
    context.user_data.pop("wallet_flow", None)
    context.user_data.pop("support_flow", None)
    if section == "transfer":
        context.user_data["wallet_flow"] = {"step": "transfer_target"}
        await reply(update, texts.WALLET_TRANSFER_ASK_TARGET, _cancel("wal:home"))
        return
    if section in ("topup", "sell"):
        eco = await db(EconomySettings.load)()
        await reply(update, *(topup_menu_screen(eco) if section == "topup" else sell_menu_screen(user, eco)))
        return
    await reply(update, *wallet_screen(user))


@command(private=True)
async def wallet_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    await open_section(update, context, user, "wallet")


async def _edit(query, text: str, keyboard=None) -> None:
    await tg_call(query.edit_message_text, text, parse_mode="HTML", reply_markup=keyboard, disable_web_page_preview=True)


@callback
async def wallet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, query):
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    sub = parts[2] if len(parts) > 2 else ""
    value = parse_int(parts[3]) if len(parts) > 3 else None

    if action in ("tc", "tx"):
        await _transfer_button(update, context, user, query, sub, confirm=action == "tc")
        return
    if update.effective_chat.type != ChatType.PRIVATE:
        return
    # مرحله‌ی نیمه‌کاره‌ی پشتیبانی نباید پیام‌های کیف پول (عدد، کارت، آیدی) را به‌عنوان تیکت بفرستد
    context.user_data.pop("support_flow", None)
    if action == "home":
        context.user_data.pop("wallet_flow", None)
        await _edit(query, *wallet_screen(user))
        return

    if action == "topup":
        eco = await db(EconomySettings.load)()
        if sub == "menu":
            context.user_data.pop("wallet_flow", None)
            await _edit(query, *topup_menu_screen(eco))
        elif sub == "cancel":
            context.user_data.pop("wallet_flow", None)
            await answer(query, texts.WALLET_TOPUP_CANCELLED)
            await _edit(query, *wallet_screen(user))
        elif sub == "custom":
            context.user_data["wallet_flow"] = {"step": "topup_custom"}
            await _edit(query, texts.WALLET_TOPUP_ASK_CUSTOM.format(max=fa_num(services.MAX_REQUEST_COINS)), _cancel("wal:topup:cancel"))
        elif sub == "p" and value in TOPUP_PACKAGES:
            text, keyboard, flow = topup_pay_screen(value, eco)
            if flow:
                context.user_data["wallet_flow"] = flow
            await _edit(query, text, keyboard)
        return

    if action == "sell":
        eco = await db(EconomySettings.load)()
        if sub == "menu":
            context.user_data.pop("wallet_flow", None)
            await _edit(query, *sell_menu_screen(user, eco))
        elif sub == "cancel":
            context.user_data.pop("wallet_flow", None)
            await answer(query, texts.WALLET_SELL_CANCELLED)
            await _edit(query, *wallet_screen(user))
        elif sub == "custom":
            context.user_data["wallet_flow"] = {"step": "sell_custom"}
            await _edit(query, texts.WALLET_SELL_ASK_CUSTOM.format(min_coins=fa_num(max(1, eco.min_sell_coins))), _cancel("wal:sell:cancel"))
        elif sub == "p":
            error = _sell_amount_error(user, eco, value)
            if error:
                await answer(query, error, alert=True)
                return
            context.user_data["wallet_flow"] = {"step": "awaiting_sell_card", "coins": value}
            await _edit(query, _ask_card_text(value, eco), _cancel("wal:sell:cancel"))
        elif sub == "ok":
            await _confirm_sell(update, context, user, query)
        return

    if action == "trans" and sub == "menu":
        context.user_data["wallet_flow"] = {"step": "transfer_target"}
        await _edit(query, texts.WALLET_TRANSFER_ASK_TARGET, _cancel("wal:home"))


def _ask_card_text(coins: int, eco: EconomySettings) -> str:
    return texts.WALLET_SELL_ASK_CARD.format(coins=fa_num(coins), amount=fa_num(services.sell_quote(coins, eco)))


# ------------------------------------------------------------------ پیام‌های پیوی (رسید، عدد، کارت، مقصد)
async def private_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    tg_user = update.effective_user
    if message is None or tg_user is None or tg_user.is_bot:
        return
    user = await ensure_user(tg_user)
    if user.is_banned:
        return

    if context.user_data.get("admin_flow"):
        from . import admin

        if await admin.admin_private_message(update, context, user):
            return
    if context.user_data.get("support_flow"):
        from . import admin

        if await admin.user_support_message(update, context, user):
            return

    flow = context.user_data.get("wallet_flow")
    if not flow:
        return
    text = (message.text or "").strip()
    if text in texts.CANCEL_WORDS:
        context.user_data.pop("wallet_flow", None)
        await reply(update, texts.WALLET_FLOW_CANCELLED, _keyboard([_btn(texts.MENU_WALLET_BTN, "pm:wallet", ui.PRIMARY)]))
        return
    step = flow.get("step")
    if step == "awaiting_receipt":
        await _receive_receipt(update, context, user, flow)
    elif step == "topup_custom":
        coins = parse_int(text)
        if coins is None or not 0 < coins <= services.MAX_REQUEST_COINS:
            await reply(update, texts.WALLET_TOPUP_INVALID_AMOUNT.format(max=fa_num(services.MAX_REQUEST_COINS)))
            return
        eco = await db(EconomySettings.load)()
        screen, keyboard, next_flow = topup_pay_screen(coins, eco)
        if next_flow:
            context.user_data["wallet_flow"] = next_flow
        await reply(update, screen, keyboard)
    elif step == "sell_custom":
        eco = await db(EconomySettings.load)()
        coins = parse_int(text)
        error = _sell_amount_error(user, eco, coins)
        if error:
            await reply(update, error)
            return
        context.user_data["wallet_flow"] = {"step": "awaiting_sell_card", "coins": coins}
        await reply(update, _ask_card_text(coins, eco), _cancel("wal:sell:cancel"))
    elif step == "awaiting_sell_card":
        await _receive_card(update, context, user, flow, text)
    elif step == "transfer_target":
        target = await find_user(text) if text else None
        if target is None:
            await reply(update, texts.WALLET_TARGET_NOT_FOUND, _cancel("wal:home"))
            return
        if target.pk == user.pk:
            await reply(update, texts.WALLET_TRANSFER_SELF)
            return
        context.user_data["wallet_flow"] = {"step": "transfer_amount", "target_id": target.pk}
        await reply(
            update,
            texts.WALLET_TRANSFER_ASK_AMOUNT.format(
                name=escape(target.display_name), coins=fa_num(user.coins), min=fa_num(settings.TRANSFER_MIN_COINS)
            ),
            _cancel("wal:home"),
        )
    elif step == "transfer_amount":
        target = await db(TelegramUser.objects.filter(pk=flow.get("target_id")).first)()
        if target is None:
            context.user_data.pop("wallet_flow", None)
            await reply(update, texts.WALLET_TARGET_NOT_FOUND)
            return
        if await ask_transfer(update, user, target, parse_int(text)):
            context.user_data.pop("wallet_flow", None)


# ------------------------------------------------------------------ شارژ: دریافت رسید
async def _receive_receipt(update: Update, context, user: TelegramUser, flow: dict) -> None:
    message = update.effective_message
    file_id = message.photo[-1].file_id if message.photo else (message.document.file_id if message.document else None)
    if not file_id:
        await reply(update, texts.WALLET_SEND_RECEIPT, _cancel("wal:topup:cancel"))
        return
    try:
        req = await db(services.create_topup_request)(user, int(flow.get("coins") or 0), file_id)
    except WalletError as exc:
        context.user_data.pop("wallet_flow", None)
        await reply(update, wallet_error_text(exc))
        return
    context.user_data.pop("wallet_flow", None)
    await reply(
        update,
        texts.WALLET_RECEIPT_RECEIVED.format(id=fa_num(req.pk), coins=fa_num(req.coins), total=fa_num(req.total_toman)),
    )
    eco = await db(EconomySettings.load)()
    caption = texts.ADMIN_TOPUP_ALERT.format(
        user=_mention(user),
        username=_username(user),
        tg_id=user.tg_id,
        coins=fa_num(req.coins),
        amount=fa_num(req.amount_toman),
        fee=fa_num(req.fee_toman),
        fee_percent=fa_num(eco.topup_fee_percent),
        total=fa_num(req.total_toman),
        date=fa_date(timezone.localtime(req.created_at)),
        id=fa_num(req.pk),
    )
    keyboard = topup_alert_keyboard(req.pk, user.tg_id)
    sent = []
    for admin_id in await get_all_admin_ids():
        message = await tg_call(
            context.bot.send_photo, admin_id, photo=file_id, caption=caption, parse_mode="HTML", reply_markup=keyboard
        )
        if message is None and message_is_document(update):
            # رسیدی که فایل (نه عکس) فرستاده شده با sendPhoto نمی‌رود
            message = await tg_call(
                context.bot.send_document, admin_id, document=file_id, caption=caption, parse_mode="HTML", reply_markup=keyboard
            )
        if message is not None:
            sent.append({"chat_id": admin_id, "msg_id": message.message_id, "photo": True})
    if sent:
        await record_admin_alerts("topup", req.pk, sent)
    else:
        logger.warning("topup alert reached no admin", extra={"request": req.pk})


def message_is_document(update: Update) -> bool:
    message = update.effective_message
    return bool(message is not None and message.document and not message.photo)


# ------------------------------------------------------------------ فروش: کارت و تأیید
async def _receive_card(update: Update, context, user: TelegramUser, flow: dict, text: str) -> None:
    try:
        number, holder = services.parse_bank_account(text)
    except WalletError as exc:
        await reply(update, wallet_error_text(exc), _cancel("wal:sell:cancel"))
        return
    eco = await db(EconomySettings.load)()
    coins = int(flow.get("coins") or 0)
    context.user_data["wallet_flow"] = {"step": "confirm_sell", "coins": coins, "card": number, "holder": holder}
    await reply(
        update,
        texts.WALLET_SELL_CONFIRM.format(
            coins=fa_num(coins),
            amount=fa_num(services.sell_quote(coins, eco)),
            card=escape(_spaced(number)),
            holder=escape(holder),
        ),
        _keyboard([_btn(texts.WALLET_SELL_OK_BTN, "wal:sell:ok", ui.SUCCESS), _btn(texts.WALLET_CANCEL_BTN, "wal:sell:cancel", ui.DANGER)]),
    )


def _spaced(number: str) -> str:
    """۶۰۳۷۹۹۱۲۳۴۵۶۷۸۹۰ → 6037 9912 3456 7890 تا خواندن و مقایسه‌اش راحت باشد."""
    if number.startswith("IR"):
        return number
    return " ".join(number[i : i + 4] for i in range(0, len(number), 4))


async def _confirm_sell(update: Update, context, user: TelegramUser, query) -> None:
    flow = context.user_data.get("wallet_flow") or {}
    if flow.get("step") != "confirm_sell":
        await answer(query, texts.WALLET_EXPIRED, alert=True)
        await tg_call(query.edit_message_reply_markup, None)
        return
    context.user_data.pop("wallet_flow", None)
    try:
        req = await db(services.create_sell_request)(user, int(flow["coins"]), flow["card"], flow["holder"])
    except InsufficientFunds as exc:
        await answer(query, texts.WALLET_NOT_ENOUGH.format(balance=fa_num(exc.balance)), alert=True)
        await _edit(query, *wallet_screen(user))
        return
    except WalletError as exc:
        await answer(query, wallet_error_text(exc), alert=True)
        return
    await _edit(
        query,
        texts.WALLET_SELL_SUBMITTED.format(
            id=fa_num(req.pk),
            coins=fa_num(req.coins),
            amount=fa_num(req.amount_toman),
            card=escape(_spaced(req.card_number)),
            holder=escape(req.card_holder),
            balance=fa_num(user.coins),
        ),
    )
    text = texts.ADMIN_SELL_ALERT.format(
        user=_mention(user),
        username=_username(user),
        tg_id=user.tg_id,
        coins=fa_num(req.coins),
        amount=fa_num(req.amount_toman),
        card=escape(req.card_number),
        holder=escape(req.card_holder or "—"),
        date=fa_date(timezone.localtime(req.created_at)),
        id=fa_num(req.pk),
    )
    keyboard = sell_alert_keyboard(req.pk, user.tg_id)
    sent = []
    for admin_id in await get_all_admin_ids():
        message = await tg_call(context.bot.send_message, admin_id, text, parse_mode="HTML", reply_markup=keyboard)
        if message is not None:
            sent.append({"chat_id": admin_id, "msg_id": message.message_id, "photo": False})
    if sent:
        await record_admin_alerts("sell", req.pk, sent)
    else:
        logger.warning("sell alert reached no admin", extra={"request": req.pk})


# ------------------------------------------------------------------ انتقال سکه با تأیید
def _transfer_key(token: str) -> str:
    return f"wallet:transfer:{token}"


async def ask_transfer(update: Update, sender: TelegramUser, target: TelegramUser, amount: int | None) -> bool:
    """پیام تأیید انتقال را می‌فرستد. اگر ورودی‌ها معتبر بود و پیام رفت ``True``."""
    minimum = max(1, settings.TRANSFER_MIN_COINS)
    if amount is None or amount < minimum:
        await reply(update, texts.WALLET_TRANSFER_MIN.format(min=fa_num(minimum)))
        return False
    if target.pk == sender.pk:
        await reply(update, texts.WALLET_TRANSFER_SELF)
        return False
    if target.is_banned:
        await reply(update, texts.WALLET_ERRORS["banned"])
        return False
    if sender.coins < amount:
        await reply(update, texts.WALLET_NOT_ENOUGH.format(balance=fa_num(sender.coins)))
        return False
    token = secrets.token_urlsafe(8)
    pending = {"from": sender.pk, "to": target.pk, "amount": amount}
    await get_redis().set(_transfer_key(token), json.dumps(pending), ex=TRANSFER_TTL)
    # موجودی فقط در پیوی نشان داده می‌شود، نه جلوی همه‌ی اعضای گروه
    private = update.effective_chat.type == ChatType.PRIVATE
    template = texts.WALLET_TRANSFER_CONFIRM if private else texts.WALLET_TRANSFER_CONFIRM_GROUP
    text = template.format(
        sender=render.short_mention(sender),
        name=escape(target.display_name),
        username=f" ({_username(target)})" if target.username else "",
        amount=fa_num(amount),
        after=fa_num(sender.coins - amount),
        seconds=fa_num(TRANSFER_TTL),
    )
    keyboard = _keyboard(
        [_btn(texts.WALLET_TRANSFER_OK_BTN, f"wal:tc:{token}", ui.SUCCESS), _btn(texts.WALLET_CANCEL_BTN, f"wal:tx:{token}", ui.DANGER)]
    )
    return await reply(update, text, keyboard) is not None


async def _transfer_button(update: Update, context, user: TelegramUser, query, token: str, confirm: bool) -> None:
    raw = await get_redis().get(_transfer_key(token)) if token else None
    pending = json.loads(raw) if raw else None
    if pending is None:
        await answer(query, texts.WALLET_EXPIRED, alert=True)
        await tg_call(query.edit_message_reply_markup, None)
        return
    if pending["from"] != user.pk:
        await answer(query, texts.WALLET_NOT_YOUR_TRANSFER, alert=True)
        return
    if not confirm:
        await get_redis().delete(_transfer_key(token))
        await answer(query, texts.WALLET_TRANSFER_CANCELLED)
        await _edit(query, texts.WALLET_TRANSFER_CANCELLED_TEXT)
        return
    target = await db(TelegramUser.objects.filter(pk=pending["to"]).first)()
    if target is None:
        await answer(query, texts.WALLET_TARGET_NOT_FOUND, alert=True)
        return
    amount = int(pending["amount"])
    try:
        tx_out, _ = await db(services.transfer_coins)(user, target, amount, idempotency_key=f"transfer:{token}")
    except InsufficientFunds as exc:
        await answer(query, texts.WALLET_NOT_ENOUGH.format(balance=fa_num(exc.balance)), alert=True)
        return
    except WalletError as exc:
        await answer(query, wallet_error_text(exc), alert=True)
        return
    await get_redis().delete(_transfer_key(token))
    if tx_out.duplicate:
        await answer(query, texts.WALLET_TRANSFER_ALREADY)
        return
    logger.info("coin transfer", extra={"from": user.tg_id, "to": target.tg_id, "amount": amount})
    await answer(query, texts.WALLET_TRANSFER_DONE_ALERT)
    if update.effective_chat.type == ChatType.PRIVATE:
        done = texts.WALLET_TRANSFER_SUCCESS.format(
            amount=fa_num(amount), receiver=escape(target.display_name), balance=fa_num(user.coins)
        )
    else:
        done = texts.WALLET_TRANSFER_SUCCESS_GROUP.format(
            amount=fa_num(amount), sender=render.short_mention(user), receiver=render.short_mention(target)
        )
    await _edit(query, done)
    if target.started_bot:
        await tg_call(
            context.bot.send_message,
            target.tg_id,
            texts.WALLET_TRANSFER_RECEIVED.format(
                amount=fa_num(amount), sender=escape(user.display_name), balance=fa_num(target.coins)
            ),
            parse_mode="HTML",
            retries=1,
        )


@command()
async def transfer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    """/transfer یا /pay — در گروه با ریپلای (/transfer 50) یا آیدی (/transfer @user 50)، در پیوی مرحله‌به‌مرحله."""
    message = update.effective_message
    args = context.args or []
    replied = message.reply_to_message.from_user if message.reply_to_message else None
    if replied is not None and len(args) == 1:
        if replied.is_bot:
            await reply(update, texts.WALLET_TRANSFER_BOT)
            return
        target = await ensure_user(replied)
        await ask_transfer(update, user, target, parse_int(args[0]))
        return
    if len(args) == 2:
        target = await find_user(args[0])
        if target is None:
            await reply(update, texts.WALLET_TARGET_NOT_FOUND)
            return
        await ask_transfer(update, user, target, parse_int(args[1]))
        return
    if update.effective_chat.type == ChatType.PRIVATE:
        context.user_data.pop("support_flow", None)
        context.user_data["wallet_flow"] = {"step": "transfer_target"}
        await reply(update, texts.WALLET_TRANSFER_ASK_TARGET, _cancel("wal:home"))
        return
    await reply(
        update, texts.WALLET_TRANSFER_USAGE.format(coins=fa_num(user.coins), min=fa_num(settings.TRANSFER_MIN_COINS))
    )


# ------------------------------------------------------------------ پیام‌های هشدار ادمین‌ها
def topup_alert_keyboard(req_pk: int, user_tg_id: int, suffix: str = "") -> InlineKeyboardMarkup:
    return _keyboard(
        [_btn(texts.ADMIN_APPROVE_BTN, f"adm:top:app:{req_pk}{suffix}", ui.SUCCESS), _btn(texts.ADMIN_REJECT_BTN, f"adm:top:rej:{req_pk}{suffix}", ui.DANGER)],
        [_btn(texts.ADMIN_DM_BTN, f"adm:dm:{user_tg_id}", ui.PRIMARY)],
    )


def sell_alert_keyboard(req_pk: int, user_tg_id: int, suffix: str = "") -> InlineKeyboardMarkup:
    return _keyboard(
        [_btn(texts.ADMIN_PAID_BTN, f"adm:sell:pay:{req_pk}{suffix}", ui.SUCCESS), _btn(texts.ADMIN_RECEIPT_BTN, f"adm:sell:receipt:{req_pk}{suffix}", ui.PRIMARY)],
        [_btn(texts.ADMIN_REFUND_BTN, f"adm:sell:rej:{req_pk}{suffix}", ui.DANGER), _btn(texts.ADMIN_DM_BTN, f"adm:dm:{user_tg_id}", ui.PRIMARY)],
    )


def _confirm_keyboard(label: str, data: str, back: str, style: str) -> InlineKeyboardMarkup:
    return _keyboard([_btn(label, data, style)], [_btn(texts.ADMIN_BACK_BTN, back, ui.PRIMARY)])


async def record_admin_alerts(kind: str, req_id: int, entries: list[dict]) -> None:
    try:
        await get_redis().set(f"adm_alerts:{kind}:{req_id}", json.dumps(entries), ex=ALERTS_TTL)
    except Exception as exc:
        logger.warning("failed to record admin alerts: %s", exc)


async def update_all_admin_alerts(context, kind: str, req_id: int, status_line: str, is_photo: bool = False) -> None:
    """پیام هشدار همین درخواست را در پیوی همه‌ی ادمین‌ها به‌روز و دکمه‌هایش را حذف می‌کند تا کسی دوباره رسیدگی نکند."""
    try:
        raw = await get_redis().get(f"adm_alerts:{kind}:{req_id}")
    except Exception as exc:
        logger.warning("failed to read admin alerts: %s", exc)
        return
    for item in json.loads(raw) if raw else []:
        chat_id, message_id = item.get("chat_id"), item.get("msg_id")
        if not chat_id or not message_id:
            continue
        if item.get("photo", is_photo):
            await tg_call(
                context.bot.edit_message_caption,
                chat_id=chat_id,
                message_id=message_id,
                caption=status_line,
                parse_mode="HTML",
                reply_markup=None,
            )
        else:
            await tg_call(
                context.bot.edit_message_text,
                chat_id=chat_id,
                message_id=message_id,
                text=status_line,
                parse_mode="HTML",
                reply_markup=None,
            )


def _request_summary(kind: str, req) -> str:
    template = texts.ADMIN_TOPUP_SUMMARY if kind == "topup" else texts.ADMIN_SELL_SUMMARY
    amount = req.total_toman if kind == "topup" else req.amount_toman
    return template.format(
        id=fa_num(req.pk),
        name=escape(req.user.display_name),
        tg_id=req.user.tg_id,
        coins=fa_num(req.coins),
        toman=fa_num(amount),
    )


async def _finish_review(update, context, user: TelegramUser, query, kind: str, review, status: str, panel: bool) -> None:
    """بعد از تأیید/رد: هشدار همه‌ی ادمین‌ها به‌روز می‌شود و اگر از پنل بود، درخواست بعدی نشان داده می‌شود."""
    if not review.changed:
        await answer(query, texts.ADMIN_ALREADY_REVIEWED.format(status=review.request.get_status_display()), alert=True)
    summary = _request_summary(kind, review.request) + "\n\n" + status.format(admin=escape(user.display_name))
    if review.changed:
        await update_all_admin_alerts(context, kind, review.request.pk, summary)
    if panel:
        from . import admin

        await admin.show_request_list(update, context, user, query, kind, 0)
        return
    # همین پیام هم (حتی اگر در فهرست هشدارها نبود) نتیجه را نشان می‌دهد و دکمه‌هایش برداشته می‌شود
    message = query.message
    if getattr(message, "photo", None) or getattr(message, "document", None):
        await tg_call(query.edit_message_caption, caption=summary, parse_mode="HTML", reply_markup=None)
    else:
        await tg_call(query.edit_message_text, summary, parse_mode="HTML", reply_markup=None)


@callback
async def admin_topup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, query):
    """adm:top:<app|rej|capp|crej|reset>:<id>[:p] — دو مرحله‌ای (اول انتخاب، بعد تأیید نهایی). «:p» یعنی از پنل /admin."""
    if not await is_superadmin(user.tg_id):
        await answer(query, texts.ADMIN_ONLY, alert=True)
        return
    parts = query.data.split(":")
    if len(parts) < 4 or not parts[3].isdigit():
        return
    action, req_id, panel = parts[2], int(parts[3]), len(parts) > 4 and parts[4] == "p"
    suffix = ":p" if panel else ""
    req = await db(lambda: TopUpRequest.objects.filter(pk=req_id).select_related("user").first())()
    if req is None:
        await answer(query, texts.ADMIN_REQUEST_GONE, alert=True)
        return
    if req.status != TopUpRequest.Status.PENDING and action in ("app", "rej", "capp", "crej"):
        await answer(query, texts.ADMIN_ALREADY_REVIEWED.format(status=req.get_status_display()), alert=True)
        await tg_call(query.edit_message_reply_markup, None)
        return
    back = f"adm:top:reset:{req.pk}{suffix}"
    if action == "app":
        await answer(query, texts.ADMIN_CONFIRM_HINT)
        await tg_call(query.edit_message_reply_markup, _confirm_keyboard(texts.ADMIN_APPROVE_SURE_BTN, f"adm:top:capp:{req.pk}{suffix}", back, ui.SUCCESS))
    elif action == "rej":
        await answer(query, texts.ADMIN_CONFIRM_HINT)
        await tg_call(query.edit_message_reply_markup, _confirm_keyboard(texts.ADMIN_REJECT_SURE_BTN, f"adm:top:crej:{req.pk}{suffix}", back, ui.DANGER))
    elif action == "reset":
        await answer(query)
        await tg_call(query.edit_message_reply_markup, topup_alert_keyboard(req.pk, req.user.tg_id, suffix))
    elif action == "capp":
        review = await db(services.approve_topup)(req.pk, user.tg_id, user.display_name)
        if review.changed:
            await answer(query, texts.ADMIN_TOPUP_APPROVED_ALERT.format(coins=fa_num(req.coins)))
            await tg_call(
                context.bot.send_message,
                req.user.tg_id,
                texts.WALLET_TOPUP_APPROVED_USER.format(id=fa_num(req.pk), coins=fa_num(req.coins), balance=fa_num(review.balance)),
                parse_mode="HTML",
            )
        await _finish_review(update, context, user, query, "topup", review, texts.ADMIN_STATUS_APPROVED, panel)
    elif action == "crej":
        review = await db(services.reject_topup)(req.pk, user.tg_id, user.display_name)
        if review.changed:
            await answer(query, texts.ADMIN_TOPUP_REJECTED_ALERT)
            await tg_call(
                context.bot.send_message, req.user.tg_id, texts.WALLET_TOPUP_REJECTED_USER.format(id=fa_num(req.pk)), parse_mode="HTML"
            )
        await _finish_review(update, context, user, query, "topup", review, texts.ADMIN_STATUS_REJECTED, panel)


@callback
async def admin_sell_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, query):
    """adm:sell:<pay|receipt|rej|cpay|crej|reset>:<id>[:p]"""
    if not await is_superadmin(user.tg_id):
        await answer(query, texts.ADMIN_ONLY, alert=True)
        return
    parts = query.data.split(":")
    if len(parts) < 4 or not parts[3].isdigit():
        return
    action, req_id, panel = parts[2], int(parts[3]), len(parts) > 4 and parts[4] == "p"
    suffix = ":p" if panel else ""
    req = await db(lambda: SellRequest.objects.filter(pk=req_id).select_related("user").first())()
    if req is None:
        await answer(query, texts.ADMIN_REQUEST_GONE, alert=True)
        return
    if req.status != SellRequest.Status.PENDING and action != "reset":
        await answer(query, texts.ADMIN_ALREADY_REVIEWED.format(status=req.get_status_display()), alert=True)
        await tg_call(query.edit_message_reply_markup, None)
        return
    back = f"adm:sell:reset:{req.pk}{suffix}"
    if action == "receipt":
        context.user_data["admin_flow"] = {"step": "sell_receipt", "req_id": req.pk}
        await answer(query)
        await reply(
            update,
            texts.ADMIN_SEND_PAYOUT_RECEIPT.format(
                id=fa_num(req.pk),
                name=escape(req.user.display_name),
                tg_id=req.user.tg_id,
                amount=fa_num(req.amount_toman),
                card=escape(req.card_number),
                holder=escape(req.card_holder or "—"),
            ),
        )
    elif action == "pay":
        await answer(query, texts.ADMIN_CONFIRM_HINT)
        await tg_call(query.edit_message_reply_markup, _confirm_keyboard(texts.ADMIN_PAID_SURE_BTN, f"adm:sell:cpay:{req.pk}{suffix}", back, ui.SUCCESS))
    elif action == "rej":
        await answer(query, texts.ADMIN_CONFIRM_HINT)
        await tg_call(query.edit_message_reply_markup, _confirm_keyboard(texts.ADMIN_REFUND_SURE_BTN, f"adm:sell:crej:{req.pk}{suffix}", back, ui.DANGER))
    elif action == "reset":
        await answer(query)
        if req.status == SellRequest.Status.PENDING:
            await tg_call(query.edit_message_reply_markup, sell_alert_keyboard(req.pk, req.user.tg_id, suffix))
    elif action == "cpay":
        review = await db(services.mark_sell_paid)(req.pk, user.tg_id, user.display_name)
        if review.changed:
            await answer(query, texts.ADMIN_SELL_PAID_ALERT.format(amount=fa_num(req.amount_toman)))
            await notify_sell_paid(context, review.request)
        await _finish_review(update, context, user, query, "sell", review, texts.ADMIN_STATUS_PAID, panel)
    elif action == "crej":
        review = await db(services.reject_sell)(req.pk, user.tg_id, user.display_name)
        if review.changed:
            await answer(query, texts.ADMIN_SELL_REFUNDED_ALERT.format(coins=fa_num(req.coins)))
            await tg_call(
                context.bot.send_message,
                req.user.tg_id,
                texts.WALLET_SELL_REJECTED_USER.format(id=fa_num(req.pk), coins=fa_num(req.coins), balance=fa_num(review.balance)),
                parse_mode="HTML",
            )
        await _finish_review(update, context, user, query, "sell", review, texts.ADMIN_STATUS_REFUNDED, panel)


async def notify_sell_paid(context, req: SellRequest, receipt_file_id: str | None = None) -> None:
    text = texts.WALLET_SELL_PAID_USER.format(
        id=fa_num(req.pk), amount=fa_num(req.amount_toman), card=escape(_spaced(req.card_number))
    )
    if receipt_file_id:
        sent = await tg_call(
            context.bot.send_photo, req.user.tg_id, photo=receipt_file_id, caption=text + texts.WALLET_SELL_RECEIPT_NOTE, parse_mode="HTML"
        )
        if sent is not None:
            return
    await tg_call(context.bot.send_message, req.user.tg_id, text, parse_mode="HTML")


async def show_photo_or_text(update, context, query, text: str, keyboard, photo: str | None = None) -> None:
    """پیام فعلی را به متن/عکس تازه تبدیل می‌کند. ویرایش متنِ پیامِ عکس‌دار ممکن نیست (و برعکس)؛
    آن‌وقت پیام قبلی پاک و پیام تازه فرستاده می‌شود، وگرنه دکمه‌ها ظاهراً «کار نمی‌کردند»."""
    message = query.message
    has_photo = bool(getattr(message, "photo", None) or getattr(message, "document", None))
    bot = context.bot
    chat_id = update.effective_chat.id
    if photo and has_photo:
        done = await tg_call(
            bot.edit_message_media,
            chat_id=chat_id,
            message_id=message.message_id,
            media=InputMediaPhoto(photo, caption=text, parse_mode="HTML"),
            reply_markup=keyboard,
        )
        if done is not None:
            return
    if not photo and not has_photo:
        if await tg_call(query.edit_message_text, text, parse_mode="HTML", reply_markup=keyboard) is not None:
            return
    await tg_call(message.delete)
    if photo:
        sent = await tg_call(bot.send_photo, chat_id, photo=photo, caption=text, parse_mode="HTML", reply_markup=keyboard)
        if sent is not None:
            return
        sent = await tg_call(bot.send_document, chat_id, document=photo, caption=text, parse_mode="HTML", reply_markup=keyboard)
        if sent is not None:
            return
    await tg_call(bot.send_message, chat_id, text, parse_mode="HTML", reply_markup=keyboard)
