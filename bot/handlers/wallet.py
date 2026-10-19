"""دستورات و منوهای کیف پول: شارژ با ارسال رسید، کارمزد ۱۰٪، فروش سکه (حداقل ۱۰۰ سکه = ۱۰۰ هزار تومان)، و انتقال سکه بین کاربران."""

import json
import logging
import re
import uuid
from html import escape

logger = logging.getLogger(__name__)
from django.conf import settings
from django.utils import timezone
from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from core import texts
from core.models import TelegramUser
from core.redis import get_redis
from core.texts import fa_num
from core.textutils import fa_date, parse_int
from wallet.models import EconomySettings, SellRequest, TopUpRequest, TxType
from wallet.services import InsufficientFunds, apply_transaction, transfer_coins

from .. import ui
from ..db import db
from ..tg import tg_call
from ..users import ensure_user, find_user
from .common import answer, callback, command, get_all_admin_ids, is_superadmin, reply


def _btn(text: str, data: str, style: str = ""):
    return ui.button(text, data, style=style)


def _topup_alert_kb(req_pk: int, user_tg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _btn("✅ تایید و شارژ", f"adm:top:app:{req_pk}", ui.SUCCESS),
                _btn("❌ رد رسید", f"adm:top:rej:{req_pk}", ui.DANGER),
            ],
            [
                _btn("✉️ پیام به کاربر", f"adm:dm:{user_tg_id}", ui.PRIMARY),
            ],
        ]
    )


def _sell_alert_kb(req_pk: int, user_tg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _btn("✅ اعلام واریز (متنی)", f"adm:sell:pay:{req_pk}", ui.SUCCESS),
                _btn("📸 ارسال رسید واریز", f"adm:sell:receipt:{req_pk}", ui.PRIMARY),
            ],
            [
                _btn("❌ رد و برگشت سکه", f"adm:sell:rej:{req_pk}", ui.DANGER),
                _btn("✉️ پیام به کاربر", f"adm:dm:{user_tg_id}", ui.PRIMARY),
            ],
        ]
    )


async def record_admin_alerts(alert_type: str, req_id: int, entries: list[dict]):
    try:
        key = f"adm_alerts:{alert_type}:{req_id}"
        await get_redis().set(key, json.dumps(entries), ex=7 * 86400)
    except Exception as exc:
        logger.warning("failed to record admin alerts in redis: %s", exc)


async def update_all_admin_alerts(context, alert_type: str, req_id: int, new_text: str, is_photo: bool = False):
    try:
        key = f"adm_alerts:{alert_type}:{req_id}"
        raw = await get_redis().get(key)
        if not raw:
            return
        entries = json.loads(raw)
        for item in entries:
            chat_id = item.get("chat_id")
            msg_id = item.get("msg_id")
            if not chat_id or not msg_id:
                continue
            try:
                if is_photo:
                    await tg_call(
                        context.bot.edit_message_caption,
                        chat_id=chat_id,
                        message_id=msg_id,
                        caption=new_text,
                        parse_mode="HTML",
                        reply_markup=None,
                    )
                else:
                    await tg_call(
                        context.bot.edit_message_text,
                        chat_id=chat_id,
                        message_id=msg_id,
                        text=new_text,
                        parse_mode="HTML",
                        reply_markup=None,
                    )
            except Exception:
                pass
    except Exception as exc:
        logger.warning("failed to update all admin alerts: %s", exc)


# ------------------------------------------------------------------ صفحه‌های کیف پول

def wallet_screen(user: TelegramUser):
    rows = [
        [_btn(texts.WALLET_TOPUP_BTN, "wal:topup:menu", ui.SUCCESS)],
        [_btn(texts.WALLET_SELL_BTN, "wal:sell:menu", ui.PRIMARY)],
        [_btn(texts.WALLET_TRANSFER_BTN, "wal:trans:menu", ui.PRIMARY)],
        [_btn(texts.WALLET_HISTORY_BTN, "pm:history", ui.PRIMARY)],
        [_btn(texts.BACK_BTN, "pm:back")],
    ]
    text = texts.WALLET_HEADER.format(coins=fa_num(user.coins))
    return text, InlineKeyboardMarkup(rows)


def topup_menu_screen(user: TelegramUser, eco: EconomySettings):
    price = eco.coin_price_toman
    fee_pct = eco.topup_fee_percent

    packages = [50, 100, 200, 500]
    rows = []
    for count in packages:
        raw = count * price
        fee = (raw * fee_pct) // 100
        total = raw + fee
        label = f"{fa_num(count)} سکه — {fa_num(total)} تومان"
        rows.append([_btn(label, f"wal:topup:p:{count}", ui.PRIMARY)])

    rows.append([_btn(texts.WALLET_TOPUP_CUSTOM_BTN, "wal:topup:custom", ui.PRIMARY)])
    rows.append([_btn(texts.BACK_BTN, "wal:home")])

    text = texts.WALLET_TOPUP_MENU.format(
        price=fa_num(price),
        fee_percent=fa_num(fee_pct),
    )
    return text, InlineKeyboardMarkup(rows)


def topup_pay_screen(user: TelegramUser, coins: int, eco: EconomySettings):
    price = eco.coin_price_toman
    fee_pct = eco.topup_fee_percent
    raw = coins * price
    fee = (raw * fee_pct) // 100
    total = raw + fee

    card = eco.card_number or ""
    holder = eco.card_holder or ""

    if not card:
        text = texts.WALLET_TOPUP_NO_CARD
        keyboard = InlineKeyboardMarkup([[_btn(texts.BACK_BTN, "wal:topup:menu")]])
        return text, keyboard, None

    holder_line = f"👤 به نام: <b>{escape(holder)}</b>\n" if holder else ""
    text = texts.WALLET_TOPUP_PAY_INFO.format(
        coins=fa_num(coins),
        amount=fa_num(raw),
        fee=fa_num(fee),
        fee_percent=fa_num(fee_pct),
        total=fa_num(total),
        card=escape(card),
        holder_line=holder_line,
    )
    keyboard = InlineKeyboardMarkup([[_btn("❌ انصراف", "wal:topup:cancel")]])
    pay_data = {"coins": coins, "amount": raw, "fee": fee, "total": total}
    return text, keyboard, pay_data


def sell_menu_screen(user: TelegramUser, eco: EconomySettings):
    min_coins = eco.min_sell_coins
    price = eco.coin_sell_price_toman
    min_amount = min_coins * price

    if user.coins < min_coins:
        text = texts.WALLET_SELL_MIN_ERROR.format(
            min_coins=fa_num(min_coins),
            min_amount=fa_num(min_amount),
            coins=fa_num(user.coins),
        )
        keyboard = InlineKeyboardMarkup([[_btn(texts.BACK_BTN, "wal:home")]])
        return text, keyboard

    rows = []
    for count in [100, 200, 500]:
        if user.coins >= count:
            rows.append([_btn(f"{fa_num(count)} سکه = {fa_num(count * price)} تومان", f"wal:sell:p:{count}", ui.PRIMARY)])

    if user.coins not in [100, 200, 500]:
        rows.append([_btn(f"کل موجودی ({fa_num(user.coins)} سکه = {fa_num(user.coins * price)} تومان)", f"wal:sell:p:{user.coins}", ui.SUCCESS)])

    rows.append([_btn(texts.WALLET_TOPUP_CUSTOM_BTN, "wal:sell:custom", ui.PRIMARY)])
    rows.append([_btn(texts.BACK_BTN, "wal:home")])

    text = texts.WALLET_SELL_MENU.format(
        coins=fa_num(user.coins),
        price=fa_num(price),
        min_coins=fa_num(min_coins),
        min_amount=fa_num(min_amount),
    )
    return text, InlineKeyboardMarkup(rows)


# ------------------------------------------------------------------ دستورات و Callbackها

@command(private=True)
async def wallet_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    await reply(update, *wallet_screen(user))


@callback
async def wallet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, query):
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    sub = parts[2] if len(parts) > 2 else ""

    async def show(screen):
        await tg_call(query.edit_message_text, screen[0], parse_mode="HTML", reply_markup=screen[1])

    if action == "home":
        context.user_data.pop("wallet_flow", None)
        await show(wallet_screen(user))
        return

    # --- شارژ کیف پول
    if action == "topup":
        eco = await db(EconomySettings.load)()
        if sub == "menu":
            context.user_data.pop("wallet_flow", None)
            await show(topup_menu_screen(user, eco))
            return
        if sub == "cancel":
            context.user_data.pop("wallet_flow", None)
            await answer(query, "شارژ لغو شد.")
            await show(wallet_screen(user))
            return
        if sub == "custom":
            context.user_data["wallet_flow"] = {"step": "topup_custom"}
            await answer(query)
            await tg_call(
                query.edit_message_text,
                texts.WALLET_TOPUP_ASK_CUSTOM,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[_btn("❌ انصراف", "wal:topup:cancel")]]),
            )
            return
        if sub == "p" and len(parts) > 3 and parts[3].isdigit():
            coins = int(parts[3])
            text, keyboard, pay_data = topup_pay_screen(user, coins, eco)
            if pay_data:
                context.user_data["wallet_flow"] = {"step": "awaiting_receipt", **pay_data}
            await tg_call(query.edit_message_text, text, parse_mode="HTML", reply_markup=keyboard)
            return

    # --- فروش سکه
    if action == "sell":
        eco = await db(EconomySettings.load)()
        if sub == "menu":
            context.user_data.pop("wallet_flow", None)
            await show(sell_menu_screen(user, eco))
            return
        if sub == "cancel":
            context.user_data.pop("wallet_flow", None)
            await answer(query, "فروش لغو شد.")
            await show(wallet_screen(user))
            return
        if sub == "custom":
            context.user_data["wallet_flow"] = {"step": "sell_custom"}
            await answer(query)
            await tg_call(
                query.edit_message_text,
                f"لطفاً تعداد سکه برای فروش را بفرست (حداقل {fa_num(eco.min_sell_coins)} سکه):",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[_btn("❌ انصراف", "wal:sell:cancel")]]),
            )
            return
        if sub == "p" and len(parts) > 3 and parts[3].isdigit():
            coins = int(parts[3])
            min_coins = eco.min_sell_coins
            if coins < min_coins or user.coins < coins:
                await answer(query, "موجودی یا تعداد سکه نامعتبر است.", alert=True)
                return
            amount = coins * eco.coin_sell_price_toman
            context.user_data["wallet_flow"] = {"step": "awaiting_sell_card", "coins": coins, "amount": amount}
            await tg_call(
                query.edit_message_text,
                texts.WALLET_SELL_ASK_CARD.format(coins=fa_num(coins), amount=fa_num(amount)),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[_btn("❌ انصراف", "wal:sell:cancel")]]),
            )
            return

    # --- انتقال سکه
    if action == "trans":
        if sub == "menu":
            context.user_data["wallet_flow"] = {"step": "transfer_target"}
            await tg_call(
                query.edit_message_text,
                texts.WALLET_TRANSFER_ASK_TARGET,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[_btn("❌ انصراف", "wal:home")]]),
            )
            return


# ------------------------------------------------------------------ پیام‌های خصوصی (رسید و متن)

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

        handled = await admin.admin_private_message(update, context, user)
        if handled:
            return

    if context.user_data.get("support_flow"):
        from . import admin

        handled = await admin.user_support_message(update, context, user)
        if handled:
            return

    flow = context.user_data.get("wallet_flow")
    if not flow:
        return

    step = flow.get("step")

    # ۱. دریافت عکس رسید برای شارژ
    if step == "awaiting_receipt":
        if not message.photo and not message.document:
            await reply(update, "لطفاً عکس فیش/رسید واریز را ارسال فرمایید.")
            return

        photo_id = message.photo[-1].file_id if message.photo else message.document.file_id
        coins = flow["coins"]
        amount = flow["amount"]
        fee = flow["fee"]
        total = flow["total"]

        req = await db(TopUpRequest.objects.create)(
            user=user,
            coins=coins,
            amount_toman=amount,
            fee_toman=fee,
            total_toman=total,
            receipt_photo_id=photo_id,
        )
        context.user_data.pop("wallet_flow", None)

        await reply(
            update,
            texts.WALLET_RECEIPT_RECEIVED.format(
                id=fa_num(req.pk),
                coins=fa_num(coins),
                total=fa_num(total),
            ),
        )

        # ارسال به سوپرادمین‌ها
        uname = f"@{escape(user.username)}" if user.username else "<i>ندارد</i>"
        user_mention = f"<a href=\"tg://user?id={user.tg_id}\">{escape(user.display_name)}</a>"
        admin_caption = texts.ADMIN_TOPUP_ALERT.format(
            user=user_mention,
            username=uname,
            tg_id=user.tg_id,
            coins=fa_num(coins),
            amount=fa_num(amount),
            fee=fa_num(fee),
            total=fa_num(total),
            date=fa_date(timezone.localtime(req.created_at)),
            id=fa_num(req.pk),
        )
        admin_kb = _topup_alert_kb(req.pk, user.tg_id)
        sent_entries = []
        for admin_id in await get_all_admin_ids():
            try:
                sent = await tg_call(
                    context.bot.send_photo,
                    admin_id,
                    photo=photo_id,
                    caption=admin_caption,
                    parse_mode="HTML",
                    reply_markup=admin_kb,
                )
                if sent:
                    sent_entries.append({"chat_id": admin_id, "msg_id": sent.message_id})
            except Exception as exc:
                logger.warning("failed to send topup alert to admin %s: %s", admin_id, exc)
        if sent_entries:
            await record_admin_alerts("topup", req.pk, sent_entries)
        return

    # ۲. دریافت تعداد دلخواه شارژ
    if step == "topup_custom":
        val = parse_int(message.text or "")
        if val is None or val <= 0:
            await reply(update, texts.WALLET_TOPUP_INVALID_AMOUNT)
            return
        eco = await db(EconomySettings.load)()
        text, keyboard, pay_data = topup_pay_screen(user, val, eco)
        if pay_data:
            context.user_data["wallet_flow"] = {"step": "awaiting_receipt", **pay_data}
        await reply(update, text, keyboard)
        return

    # ۳. دریافت تعداد دلخواه فروش
    if step == "sell_custom":
        val = parse_int(message.text or "")
        eco = await db(EconomySettings.load)()
        min_coins = eco.min_sell_coins
        if val is None or val < min_coins or user.coins < val:
            await reply(
                update,
                f"تعداد سکه نامعتبر است. حداقل {fa_num(min_coins)} سکه و حداکثر {fa_num(user.coins)} سکه مجاز است.",
            )
            return
        amount = val * eco.coin_sell_price_toman
        context.user_data["wallet_flow"] = {"step": "awaiting_sell_card", "coins": val, "amount": amount}
        await reply(
            update,
            texts.WALLET_SELL_ASK_CARD.format(coins=fa_num(val), amount=fa_num(amount)),
            InlineKeyboardMarkup([[_btn("❌ انصراف", "wal:sell:cancel")]]),
        )
        return

    # ۴. دریافت اطلاعات کارت برای فروش
    if step == "awaiting_sell_card":
        card_text = (message.text or "").strip()
        if len(card_text) < 10:
            await reply(update, "لطفاً شماره کارت ۱۶ رقمی و نام صاحب کارت را وارد کنید:")
            return

        coins = flow["coins"]
        amount = flow["amount"]

        # کسر سکه‌ها از موجودی
        try:
            tx_key = f"sell:{uuid.uuid4().hex[:12]}"
            await db(apply_transaction)(user, -coins, TxType.SELL, tx_key)
        except InsufficientFunds:
            context.user_data.pop("wallet_flow", None)
            await reply(update, "موجودی سکه شما کافی نیست!")
            return

        req = await db(SellRequest.objects.create)(
            user=user,
            coins=coins,
            amount_toman=amount,
            card_number=card_text[:32],
            card_holder=card_text[32:128] if len(card_text) > 32 else "",
        )
        context.user_data.pop("wallet_flow", None)

        await reply(
            update,
            texts.WALLET_SELL_SUBMITTED.format(
                id=fa_num(req.pk),
                coins=fa_num(coins),
                amount=fa_num(amount),
                card=escape(card_text),
            ),
        )

        # ارسال به سوپرادمین‌ها
        uname = f"@{escape(user.username)}" if user.username else "<i>ندارد</i>"
        user_mention = f"<a href=\"tg://user?id={user.tg_id}\">{escape(user.display_name)}</a>"
        admin_msg = texts.ADMIN_SELL_ALERT.format(
            user=user_mention,
            username=uname,
            tg_id=user.tg_id,
            coins=fa_num(coins),
            amount=fa_num(amount),
            card=escape(card_text),
            date=fa_date(timezone.localtime(req.created_at)),
            id=fa_num(req.pk),
        )
        admin_kb = _sell_alert_kb(req.pk, user.tg_id)
        sent_entries = []
        for admin_id in await get_all_admin_ids():
            try:
                sent = await tg_call(
                    context.bot.send_message,
                    admin_id,
                    admin_msg,
                    parse_mode="HTML",
                    reply_markup=admin_kb,
                )
                if sent:
                    sent_entries.append({"chat_id": admin_id, "msg_id": sent.message_id})
            except Exception as exc:
                logger.warning("failed to send sell alert to admin %s: %s", admin_id, exc)
        if sent_entries:
            await record_admin_alerts("sell", req.pk, sent_entries)
        return

    # ۵. دریافت مقصد انتقال در پیوی
    if step == "transfer_target":
        target = await find_user((message.text or "").strip())
        if target is None:
            await reply(update, texts.USER_NOT_FOUND)
            return
        if target.pk == user.pk:
            await reply(update, texts.WALLET_TRANSFER_SELF)
            return
        context.user_data["wallet_flow"] = {"step": "transfer_amount", "target_id": target.pk, "target_name": target.display_name}
        await reply(
            update,
            texts.WALLET_TRANSFER_ASK_AMOUNT.format(
                name=escape(target.display_name),
                coins=fa_num(user.coins),
            ),
            InlineKeyboardMarkup([[_btn("❌ انصراف", "wal:home")]]),
        )
        return

    # ۶. دریافت مقدار انتقال در پیوی
    if step == "transfer_amount":
        amount = parse_int(message.text or "")
        if amount is None or amount <= 0:
            await reply(update, "تعداد سکه باید یک عدد صحیح بزرگ‌تر از صفر باشد.")
            return
        if user.coins < amount:
            await reply(update, texts.WALLET_TRANSFER_NO_COINS.format(balance=fa_num(user.coins)))
            return

        target_id = flow["target_id"]
        target = await db(TelegramUser.objects.filter(pk=target_id).first)()
        if target is None:
            context.user_data.pop("wallet_flow", None)
            await reply(update, texts.USER_NOT_FOUND)
            return

        try:
            await db(transfer_coins)(user, target, amount)
        except InsufficientFunds:
            await reply(update, texts.WALLET_TRANSFER_NO_COINS.format(balance=fa_num(user.coins)))
            return
        except Exception:
            await reply(update, "خطا در انجام انتقال.")
            return

        context.user_data.pop("wallet_flow", None)
        await reply(
            update,
            texts.WALLET_TRANSFER_SUCCESS.format(
                amount=fa_num(amount),
                receiver=escape(target.display_name),
                balance=fa_num(user.coins),
            ),
        )
        # اطلاع‌رسانی به گیرنده
        if target.started_bot:
            try:
                await tg_call(
                    context.bot.send_message,
                    target.tg_id,
                    texts.WALLET_TRANSFER_RECEIVED.format(
                        amount=fa_num(amount),
                        sender=escape(user.display_name),
                        balance=fa_num(target.coins),
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass
        return


# ------------------------------------------------------------------ دستور انتقال (/transfer یا /pay)

@command()
async def transfer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    """انتقال مستقیم سکه: در گروه با ریپلای یا آیدی، در پیوی تعاملی یا با آیدی."""
    message = update.effective_message
    args = context.args or []

    # حالت ۱: ریپلای در گروه
    if message.reply_to_message and message.reply_to_message.from_user:
        target_tg_user = message.reply_to_message.from_user
        if target_tg_user.is_bot:
            await reply(update, "نمی‌توانید به ربات سکه انتقال دهید.")
            return
        amount = parse_int(args[0]) if args else None
        if amount is None or amount <= 0:
            await reply(update, "استفاده: روی پیام کاربر ریپلای کن و بنویس:\n<code>/transfer 50</code>")
            return
        target = await ensure_user(target_tg_user)
        if target.pk == user.pk:
            await reply(update, texts.WALLET_TRANSFER_SELF)
            return
        try:
            await db(transfer_coins)(user, target, amount)
        except InsufficientFunds:
            await reply(update, texts.WALLET_TRANSFER_NO_COINS.format(balance=fa_num(user.coins)))
            return
        await reply(
            update,
            texts.WALLET_TRANSFER_SUCCESS.format(
                amount=fa_num(amount),
                receiver=escape(target.display_name),
                balance=fa_num(user.coins),
            ),
        )
        if target.started_bot:
            try:
                await tg_call(
                    context.bot.send_message,
                    target.tg_id,
                    texts.WALLET_TRANSFER_RECEIVED.format(
                        amount=fa_num(amount),
                        sender=escape(user.display_name),
                        balance=fa_num(target.coins),
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass
        return

    # حالت ۲: با آرگومان: /transfer @user 50 یا /transfer 1234567 50
    if len(args) == 2:
        amount = parse_int(args[1])
        if amount is None or amount <= 0:
            await reply(update, "تعداد سکه نامعتبر است.")
            return
        target = await find_user(args[0])
        if target is None:
            await reply(update, texts.USER_NOT_FOUND)
            return
        if target.pk == user.pk:
            await reply(update, texts.WALLET_TRANSFER_SELF)
            return
        try:
            await db(transfer_coins)(user, target, amount)
        except InsufficientFunds:
            await reply(update, texts.WALLET_TRANSFER_NO_COINS.format(balance=fa_num(user.coins)))
            return
        await reply(
            update,
            texts.WALLET_TRANSFER_SUCCESS.format(
                amount=fa_num(amount),
                receiver=escape(target.display_name),
                balance=fa_num(user.coins),
            ),
        )
        if target.started_bot:
            try:
                await tg_call(
                    context.bot.send_message,
                    target.tg_id,
                    texts.WALLET_TRANSFER_RECEIVED.format(
                        amount=fa_num(amount),
                        sender=escape(user.display_name),
                        balance=fa_num(target.coins),
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass
        return

    # حالت ۳: در پیوی بدون آرگومان
    if update.effective_chat.type == ChatType.PRIVATE:
        context.user_data["wallet_flow"] = {"step": "transfer_target"}
        await reply(
            update,
            texts.WALLET_TRANSFER_ASK_TARGET,
            InlineKeyboardMarkup([[_btn("❌ انصراف", "wal:home")]]),
        )
        return

    await reply(update, texts.WALLET_TRANSFER_USAGE.format(coins=fa_num(user.coins)))


# ------------------------------------------------------------------ Callbackهای ادمین برای شارژ و تسویه

@callback
async def admin_topup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, query):
    if not await is_superadmin(user.tg_id):
        await answer(query, "دسترسی مجاز نیست.", alert=True)
        return

    parts = query.data.split(":")
    action = parts[2]
    req_id = int(parts[3])

    req = await db(lambda: TopUpRequest.objects.filter(pk=req_id).select_related("user").first())()
    if req is None:
        await answer(query, "درخواست یافت نشد.", alert=True)
        return
    if req.status != TopUpRequest.Status.PENDING:
        await answer(query, f"این درخواست قبلاً {req.get_status_display()} شده است.", alert=True)
        return

    if action == "app":
        confirm_kb = InlineKeyboardMarkup(
            [
                [
                    _btn("✅ بله، تایید نهایی و شارژ حساب", f"adm:top:capp:{req.pk}", ui.SUCCESS),
                ],
                [
                    _btn("🔙 انصراف و بازگشت", f"adm:top:reset:{req.pk}", ui.PRIMARY),
                ],
            ]
        )
        await answer(query, "⚠️ جهت تایید نهایی و واریز سکه‌ها، دکمه تایید نهایی را بزنید.")
        await tg_call(query.edit_message_reply_markup, reply_markup=confirm_kb)
        return

    if action == "rej":
        confirm_kb = InlineKeyboardMarkup(
            [
                [
                    _btn("❌ بله، رد قطعی رسید", f"adm:top:crej:{req.pk}", ui.DANGER),
                ],
                [
                    _btn("🔙 انصراف و بازگشت", f"adm:top:reset:{req.pk}", ui.PRIMARY),
                ],
            ]
        )
        await answer(query, "⚠️ جهت رد رسید، دکمه رد قطعی را بزنید.")
        await tg_call(query.edit_message_reply_markup, reply_markup=confirm_kb)
        return

    if action == "reset":
        await answer(query, "عملیات لغو شد.")
        await tg_call(query.edit_message_reply_markup, reply_markup=_topup_alert_kb(req.pk, req.user.tg_id))
        return

    if action == "capp":
        await db(apply_transaction)(req.user, req.coins, TxType.TOPUP, f"topup:{req.pk}")
        req.status = TopUpRequest.Status.APPROVED
        req.reviewed_at = timezone.now()
        req.admin_note = f"Approved by {user.tg_id} ({user.display_name})"
        await db(req.save)(update_fields=["status", "reviewed_at", "admin_note"])
        await answer(query, f"شارژ {req.coins} سکه تایید شد ✅")

        base_caption = query.message.caption_html or ""
        new_caption = f"{base_caption}\n\n✅ <b>تایید و شارژ شد</b> توسط {escape(user.display_name)}"
        await update_all_admin_alerts(context, "topup", req.pk, new_caption, is_photo=True)
        try:
            await tg_call(query.edit_message_caption, caption=new_caption, parse_mode="HTML", reply_markup=None)
        except Exception:
            pass

        # اطلاع‌رسانی به کاربر
        try:
            await db(req.user.refresh_from_db)()
            await tg_call(
                context.bot.send_message,
                req.user.tg_id,
                texts.WALLET_TOPUP_APPROVED_USER.format(
                    coins=fa_num(req.coins),
                    balance=fa_num(req.user.coins),
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    if action == "crej":
        req.status = TopUpRequest.Status.REJECTED
        req.reviewed_at = timezone.now()
        req.admin_note = f"Rejected by {user.tg_id} ({user.display_name})"
        await db(req.save)(update_fields=["status", "reviewed_at", "admin_note"])
        await answer(query, "رسید رد شد ❌")

        base_caption = query.message.caption_html or ""
        new_caption = f"{base_caption}\n\n❌ <b>رد شد</b> توسط {escape(user.display_name)}"
        await update_all_admin_alerts(context, "topup", req.pk, new_caption, is_photo=True)
        try:
            await tg_call(query.edit_message_caption, caption=new_caption, parse_mode="HTML", reply_markup=None)
        except Exception:
            pass

        try:
            await tg_call(
                context.bot.send_message,
                req.user.tg_id,
                texts.WALLET_TOPUP_REJECTED_USER.format(id=fa_num(req.pk)),
                parse_mode="HTML",
            )
        except Exception:
            pass
        return


@callback
async def admin_sell_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, query):
    if not await is_superadmin(user.tg_id):
        await answer(query, "دسترسی مجاز نیست.", alert=True)
        return

    parts = query.data.split(":")
    action = parts[2]
    req_id = int(parts[3])

    req = await db(lambda: SellRequest.objects.filter(pk=req_id).select_related("user").first())()
    if req is None:
        await answer(query, "درخواست یافت نشد.", alert=True)
        return
    if req.status != SellRequest.Status.PENDING:
        await answer(query, f"این درخواست قبلاً {req.get_status_display()} شده است.", alert=True)
        return

    if action == "receipt":
        context.user_data["admin_flow"] = {"step": "sell_receipt", "req_id": req.pk}
        await answer(query)
        await reply(
            update,
            f"📸 <b>ارسال رسید واریز به کاربر (درخواست #{fa_num(req.pk)})</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"👤 کاربر: <b>{escape(req.user.display_name)}</b> (<code>{req.user.tg_id}</code>)\n"
            f"💵 مبلغ واریزی: <b>{fa_num(req.amount_toman)} تومان</b>\n"
            f"💳 شماره کارت: <code>{escape(req.card_number)}</code>\n"
            f"👤 صاحب کارت: <b>{escape(req.card_holder or '—')}</b>\n\n"
            "لطفاً عکس فیش/رسید واریز بانک را ارسال فرمایید تا بلافاصله برای کاربر فرستاده و درخواست تایید شود.\n"
            "(جهت انصراف عبارت <code>لغو</code> را ارسال کنید)",
        )
        return

    if action == "pay":
        confirm_kb = InlineKeyboardMarkup(
            [
                [
                    _btn("✅ بله، تایید نهایی واریز وجه", f"adm:sell:cpay:{req.pk}", ui.SUCCESS),
                ],
                [
                    _btn("🔙 انصراف و بازگشت", f"adm:sell:reset:{req.pk}", ui.PRIMARY),
                ],
            ]
        )
        await answer(query, "⚠️ جهت اعلام واریز، تایید نهایی را بزنید.")
        await tg_call(query.edit_message_reply_markup, reply_markup=confirm_kb)
        return

    if action == "rej":
        confirm_kb = InlineKeyboardMarkup(
            [
                [
                    _btn("❌ بله، رد قطعی و برگشت سکه‌ها", f"adm:sell:crej:{req.pk}", ui.DANGER),
                ],
                [
                    _btn("🔙 انصراف و بازگشت", f"adm:sell:reset:{req.pk}", ui.PRIMARY),
                ],
            ]
        )
        await answer(query, "⚠️ جهت رد درخواست تسویه، تایید نهایی را بزنید.")
        await tg_call(query.edit_message_reply_markup, reply_markup=confirm_kb)
        return

    if action == "reset":
        await answer(query, "عملیات لغو شد.")
        await tg_call(query.edit_message_reply_markup, reply_markup=_sell_alert_kb(req.pk, req.user.tg_id))
        return

    if action == "cpay":
        req.status = SellRequest.Status.PAID
        req.reviewed_at = timezone.now()
        req.admin_note = f"Paid by {user.tg_id} ({user.display_name})"
        await db(req.save)(update_fields=["status", "reviewed_at", "admin_note"])
        await answer(query, f"واریز {req.amount_toman:,} تومان تایید شد ✅")

        base_text = query.message.text_html or ""
        new_text = f"{base_text}\n\n✅ <b>واریز شد</b> توسط {escape(user.display_name)}"
        await update_all_admin_alerts(context, "sell", req.pk, new_text, is_photo=False)
        try:
            await tg_call(query.edit_message_text, text=new_text, parse_mode="HTML", reply_markup=None)
        except Exception:
            pass

        try:
            await tg_call(
                context.bot.send_message,
                req.user.tg_id,
                texts.WALLET_SELL_PAID_USER.format(
                    id=fa_num(req.pk),
                    amount=fa_num(req.amount_toman),
                    card=escape(req.card_number),
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    if action == "crej":
        await db(apply_transaction)(req.user, req.coins, TxType.REFUND, f"sell_refund:{req.pk}")
        req.status = SellRequest.Status.REJECTED
        req.reviewed_at = timezone.now()
        req.admin_note = f"Rejected by {user.tg_id} ({user.display_name})"
        await db(req.save)(update_fields=["status", "reviewed_at", "admin_note"])
        await answer(query, f"رد شد و {req.coins} سکه برگشت داده شد.")

        base_text = query.message.text_html or ""
        new_text = f"{base_text}\n\n❌ <b>رد شد و سکه‌ها برگشت داده شد</b> توسط {escape(user.display_name)}"
        await update_all_admin_alerts(context, "sell", req.pk, new_text, is_photo=False)
        try:
            await tg_call(query.edit_message_text, text=new_text, parse_mode="HTML", reply_markup=None)
        except Exception:
            pass

        try:
            await tg_call(
                context.bot.send_message,
                req.user.tg_id,
                texts.WALLET_SELL_REJECTED_USER.format(
                    id=fa_num(req.pk),
                    coins=fa_num(req.coins),
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass
        return
