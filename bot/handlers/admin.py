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
from wallet.models import EconomySettings, SellRequest, TopUpRequest, TxType
from wallet.services import InsufficientFunds, apply_transaction

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


def _btn(text: str, data: str, style: str = ""):
    return ui.button(text, data, style=style)


async def admin_panel_screen(user: TelegramUser):
    eco = await db(EconomySettings.load)()
    topup_pending = await db(lambda: TopUpRequest.objects.filter(status=TopUpRequest.Status.PENDING).count())()
    sell_pending = await db(lambda: SellRequest.objects.filter(status=SellRequest.Status.PENDING).count())()
    admin_count = 1 + len(getattr(eco, "extra_admin_ids", []) or [])

    card_line = f"<code>{escape(eco.card_number)}</code>" if eco.card_number else "<i>ثبت نشده</i>"
    holder_line = f"<b>{escape(eco.card_holder)}</b>" if eco.card_holder else "<i>ثبت نشده</i>"

    text = (
        "👑 <b>پنل مدیریت ربات وینزون بت (Winzon Bet)</b>\n"
        "━━━━━━━━━━━━━━\n"
        f"👤 مدیر: <b>{escape(user.display_name)}</b> (<code>{user.tg_id}</code>)\n\n"
        "💳 <b>اطلاعات کارت واریز:</b>\n"
        f"شماره کارت: {card_line}\n"
        f"به نام: {holder_line}\n\n"
        "🪙 <b>نرخ و کارمزد سکه:</b>\n"
        f"قیمت هر سکه: <b>{fa_num(eco.coin_price_toman)}</b> تومان\n"
        f"کارمزد شارژ: <b>{fa_num(eco.topup_fee_percent)}٪</b>\n"
        f"حداقل فروش: <b>{fa_num(eco.min_sell_coins)}</b> سکه\n\n"
        "📊 <b>درخواست‌های در انتظار:</b>\n"
        f"🧾 رسیدهای شارژ بررسی‌نشده: <b>{fa_num(topup_pending)}</b>\n"
        f"💸 درخواست‌های فروش بررسی‌نشده: <b>{fa_num(sell_pending)}</b>\n"
        f"👥 ادمین‌های ربات: <b>{fa_num(admin_count)}</b> نفر"
    )

    rows = [
        [
            _btn(f"🧾 رسیدهای شارژ ({fa_num(topup_pending)})", "adm:topup:list:0", ui.SUCCESS if topup_pending else ui.PRIMARY),
            _btn(f"💸 تسویه و فروش ({fa_num(sell_pending)})", "adm:sellreq:list:0", ui.DANGER if sell_pending else ui.PRIMARY),
        ],
        [
            _btn("💳 تنظیم شماره کارت", "adm:set:card", ui.PRIMARY),
            _btn("🪙 تنظیم نرخ و کارمزد", "adm:set:rate", ui.PRIMARY),
        ],
        [
            _btn("👥 مدیریت ادمین‌ها", "adm:admins:list", ui.PRIMARY),
            _btn("📊 آمار کلی ربات", "adm:stats:show", ui.PRIMARY),
        ],
        [
            _btn("✉️ ارسال پیام به کاربر", "adm:msg:start", ui.PRIMARY),
            _btn("📢 ارسال پیام همگانی", "adm:bcast:prompt", ui.PRIMARY),
        ],
        [
            _btn("🔄 بروزرسانی", "adm:home"),
            _btn("❌ بستن پنل", "adm:close"),
        ],
    ]
    return text, InlineKeyboardMarkup(rows)


@command(superadmin=True, private=True)
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    context.user_data.pop("admin_flow", None)
    text, keyboard = await admin_panel_screen(user)
    await reply(update, text, keyboard)


@callback
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, query):
    if not await is_superadmin(user.tg_id):
        await answer(query, "دسترسی غیرمجاز است.", alert=True)
        return

    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else "home"
    sub = parts[2] if len(parts) > 2 else ""

    async def show(text, markup):
        try:
            await tg_call(query.edit_message_text, text, parse_mode="HTML", reply_markup=markup)
        except Exception:
            await reply(update, text, markup)

    if action == "home":
        context.user_data.pop("admin_flow", None)
        text, markup = await admin_panel_screen(user)
        await show(text, markup)
        return

    if action == "close":
        context.user_data.pop("admin_flow", None)
        await answer(query, "پنل مدیریت بسته شد.")
        try:
            await tg_call(query.edit_message_text, "🔒 پنل مدیریت بسته شد.")
        except Exception:
            pass
        return

    if action == "msg" and sub == "start":
        context.user_data["admin_flow"] = {"step": "ask_msg_target"}
        await answer(query)
        await show(
            "✉️ <b>ارسال پیام / تیکت به کاربر</b>\n"
            "━━━━━━━━━━━━━━\n"
            "لطفاً شناسه عددی تلگرام یا آیدی کاربر را ارسال فرمایید:\n"
            "(مثال: <code>123456789</code> یا <code>@username</code>)\n\n"
            "<i>(جهت انصراف عبارت <code>لغو</code> را ارسال نمایید)</i>",
            InlineKeyboardMarkup([[_btn("🔙 بازگشت به پنل", "adm:home")]]),
        )
        return

    # تنظیم کارت
    if action == "set" and sub == "card":
        eco = await db(EconomySettings.load)()
        context.user_data["admin_flow"] = {"step": "set_card"}
        await answer(query)
        prompt = (
            "💳 <b>تنظیم شماره کارت بانکی جهت شارژ کیف پول</b>\n"
            "━━━━━━━━━━━━━━\n"
            f"شماره کارت فعلی: <code>{escape(eco.card_number or 'ثبت نشده')}</code>\n"
            f"نام صاحب کارت فعلی: <b>{escape(eco.card_holder or 'ثبت نشده')}</b>\n\n"
            "لطفاً شماره کارت ۱۶ رقمی و نام صاحب کارت را در یک پیام بفرستید:\n"
            "<i>مثال:</i>\n"
            "<code>6219861997831192 امید فیروزآبادی</code>"
        )
        kb = InlineKeyboardMarkup([[_btn("❌ انصراف", "adm:home")]])
        await show(prompt, kb)
        return

    # تنظیم نرخ و کارمزد
    if action == "set" and sub == "rate":
        eco = await db(EconomySettings.load)()
        context.user_data["admin_flow"] = {"step": "set_rate"}
        await answer(query)
        prompt = (
            "🪙 <b>تنظیم نرخ سکه و کارمزد</b>\n"
            "━━━━━━━━━━━━━━\n"
            f"نرخ خرید هر سکه: <b>{fa_num(eco.coin_price_toman)}</b> تومان\n"
            f"درصد کارمزد شارژ: <b>{fa_num(eco.topup_fee_percent)}٪</b>\n"
            f"حداقل فروش: <b>{fa_num(eco.min_sell_coins)}</b> سکه\n"
            f"نرخ فروش هر سکه: <b>{fa_num(eco.coin_sell_price_toman)}</b> تومان\n\n"
            "لطفاً مقادیر جدید را با فاصله به صورت زیر ارسال کنید:\n"
            "<code>[نرخ_خرید] [درصد_کارمزد] [حداقل_فروش] [نرخ_فروش]</code>\n"
            "<i>مثال:</i>\n"
            "<code>1000 10 100 1000</code>"
        )
        kb = InlineKeyboardMarkup([[_btn("❌ انصراف", "adm:home")]])
        await show(prompt, kb)
        return

    # مدیریت ادمین‌ها
    if action == "admins":
        eco = await db(EconomySettings.load)()
        extra = list(getattr(eco, "extra_admin_ids", []) or [])
        text = (
            "👥 <b>مدیریت ادمین‌های ربات</b>\n"
            "━━━━━━━━━━━━━━\n"
            "👑 <b>مالک اصلی:</b> <code>639344728</code>\n\n"
        )
        if extra:
            text += "<b>ادمین‌های اضافه شده:</b>\n"
            for i, aid in enumerate(extra, 1):
                text += f"{i}. <code>{aid}</code>\n"
        else:
            text += "هیچ ادمین دیگری ثبت نشده است.\n"
        rows = [
            [_btn("➕ افزودن ادمین جدید", "adm:admin:add", ui.SUCCESS)],
        ]
        if extra:
            rows.append([_btn("➖ حذف ادمین", "adm:admin:delselect", ui.DANGER)])
        rows.append([_btn("🔙 بازگشت به پنل", "adm:home")])
        await show(text, InlineKeyboardMarkup(rows))
        return

    if action == "admin" and sub == "add":
        context.user_data["admin_flow"] = {"step": "add_admin"}
        await answer(query)
        prompt = (
            "➕ <b>افزودن ادمین جدید</b>\n"
            "━━━━━━━━━━━━━━\n"
            "لطفاً آیدی عددی تلگرام کاربر مورد نظر را ارسال فرمایید:\n"
            "<i>(آیدی عددی را می‌توانید از @userinfobot دریافت کنید)</i>"
        )
        kb = InlineKeyboardMarkup([[_btn("❌ انصراف", "adm:admins")]])
        await show(prompt, kb)
        return

    if action == "admin" and sub == "delselect":
        eco = await db(EconomySettings.load)()
        extra = list(getattr(eco, "extra_admin_ids", []) or [])
        rows = []
        for aid in extra:
            rows.append([_btn(f"❌ حذف {aid}", f"adm:admin:del:{aid}", ui.DANGER)])
        rows.append([_btn("🔙 بازگشت", "adm:admins")])
        await show("روی ادمینی که می‌خواهید حذف شود کلیک کنید:", InlineKeyboardMarkup(rows))
        return

    if action == "admin" and sub == "del":
        del_id = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
        eco = await db(EconomySettings.load)()
        extra = list(getattr(eco, "extra_admin_ids", []) or [])
        if del_id in extra:
            extra.remove(del_id)
            eco.extra_admin_ids = extra
            await db(eco.save)()
            from .common import get_all_admin_ids
            await get_all_admin_ids()
            await answer(query, f"ادمین {del_id} حذف شد.")
        query.data = "adm:admins:list"
        await admin_callback(update, context, user, query)
        return

    # رسیدهای شارژ
    if action in ("topup", "top") and sub == "list":
        idx = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
        reqs = await db(lambda: list(TopUpRequest.objects.filter(status=TopUpRequest.Status.PENDING).select_related("user").order_by("created_at")))()
        if not reqs:
            await answer(query)
            await show(
                "✅ <b>هیچ رسید شارژی در انتظار بررسی وجود ندارد.</b>",
                InlineKeyboardMarkup([[_btn("🔙 بازگشت به پنل", "adm:home")]]),
            )
            return

        idx = max(0, min(idx, len(reqs) - 1))
        req = reqs[idx]

        caption = (
            f"🧾 <b>رسید شارژ کیف پول ({fa_num(idx + 1)} از {fa_num(len(reqs))})</b>\n"
            "━━━━━━━━━━━━━━\n"
            f"👤 کاربر: <b>{escape(req.user.display_name)}</b>\n"
            f"🆔 آیدی عددی: <code>{req.user.tg_id}</code>\n"
            f"🪙 تعداد سکه: <b>{fa_num(req.coins)}</b>\n"
            f"💵 مبلغ خام: <b>{fa_num(req.amount_toman)}</b> تومان\n"
            f"📊 کارمزد شارژ: <b>{fa_num(req.fee_toman)}</b> تومان\n"
            f"💰 <b>مبلغ نهایی پرداختی: {fa_num(req.total_toman)} تومان</b>\n"
            f"📅 تاریخ: {fa_date(timezone.localtime(req.created_at))}\n"
            f"شناسه پیگیری: #{fa_num(req.pk)}"
        )

        nav_row = []
        if idx > 0:
            nav_row.append(_btn("⬅️ قبلی", f"adm:topup:list:{idx - 1}"))
        if idx < len(reqs) - 1:
            nav_row.append(_btn("بعدی ➡️", f"adm:topup:list:{idx + 1}"))

        btn_rows = [
            [
                _btn("✅ تایید و شارژ", f"adm:topup:app:{req.pk}", ui.SUCCESS),
                _btn("❌ رد رسید", f"adm:topup:rej:{req.pk}", ui.DANGER),
            ]
        ]
        if nav_row:
            btn_rows.append(nav_row)
        btn_rows.append([_btn("🔙 بازگشت به پنل", "adm:home")])

        await answer(query)
        if req.receipt_photo_id:
            try:
                await tg_call(query.message.delete)
            except Exception:
                pass
            await tg_call(
                context.bot.send_photo,
                user.tg_id,
                photo=req.receipt_photo_id,
                caption=caption,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(btn_rows),
            )
        else:
            await show(caption, InlineKeyboardMarkup(btn_rows))
        return

    # تایید / رد رسید شارژ
    if action in ("topup", "top") and sub in ("app", "rej"):
        req_id = int(parts[3])
        req = await db(lambda: TopUpRequest.objects.filter(pk=req_id).select_related("user").first())()
        if not req or req.status != TopUpRequest.Status.PENDING:
            await answer(query, "این درخواست قبلاً بررسی شده است.", alert=True)
            return

        if sub == "app":
            await db(apply_transaction)(req.user, req.coins, TxType.TOPUP, f"topup:{req.pk}")
            req.status = TopUpRequest.Status.APPROVED
            req.reviewed_at = timezone.now()
            req.admin_note = f"Approved by {user.tg_id}"
            await db(req.save)(update_fields=["status", "reviewed_at", "admin_note"])
            await answer(query, f"شارژ {req.coins} سکه تایید شد ✅")
            try:
                await db(req.user.refresh_from_db)()
                await tg_call(
                    context.bot.send_message,
                    req.user.tg_id,
                    texts.WALLET_TOPUP_APPROVED_USER.format(coins=fa_num(req.coins), balance=fa_num(req.user.coins)),
                    parse_mode="HTML",
                )
            except Exception:
                pass
        else:
            req.status = TopUpRequest.Status.REJECTED
            req.reviewed_at = timezone.now()
            req.admin_note = f"Rejected by {user.tg_id}"
            await db(req.save)(update_fields=["status", "reviewed_at", "admin_note"])
            await answer(query, "رسید شارژ رد شد ❌")
            try:
                await tg_call(
                    context.bot.send_message,
                    req.user.tg_id,
                    texts.WALLET_TOPUP_REJECTED_USER.format(id=fa_num(req.pk)),
                    parse_mode="HTML",
                )
            except Exception:
                pass

        query.data = "adm:topup:list:0"
        await admin_callback(update, context, user, query)
        return

    # درخواست‌های فروش
    if action in ("sell", "sellreq") and sub == "list":
        idx = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
        reqs = await db(lambda: list(SellRequest.objects.filter(status=SellRequest.Status.PENDING).select_related("user").order_by("created_at")))()
        if not reqs:
            await answer(query)
            await show(
                "✅ <b>هیچ درخواست فروشی در انتظار واریز وجود ندارد.</b>",
                InlineKeyboardMarkup([[_btn("🔙 بازگشت به پنل", "adm:home")]]),
            )
            return

        idx = max(0, min(idx, len(reqs) - 1))
        req = reqs[idx]

        text = (
            f"💸 <b>درخواست تسویه/فروش سکه ({fa_num(idx + 1)} از {fa_num(len(reqs))})</b>\n"
            "━━━━━━━━━━━━━━\n"
            f"👤 کاربر: <b>{escape(req.user.display_name)}</b>\n"
            f"🆔 آیدی عددی: <code>{req.user.tg_id}</code>\n"
            f"🪙 سکه کسر شده: <b>{fa_num(req.coins)}</b>\n"
            f"💵 <b>مبلغ واریزی به کاربر: {fa_num(req.amount_toman)} تومان</b>\n\n"
            f"💳 شماره کارت: <code>{escape(req.card_number)}</code>\n"
            f"👤 دارنده کارت: <b>{escape(req.card_holder or '—')}</b>\n"
            f"📅 تاریخ: {fa_date(timezone.localtime(req.created_at))}\n"
            f"شناسه پیگیری: #{fa_num(req.pk)}"
        )

        nav_row = []
        if idx > 0:
            nav_row.append(_btn("⬅️ قبلی", f"adm:sellreq:list:{idx - 1}"))
        if idx < len(reqs) - 1:
            nav_row.append(_btn("بعدی ➡️", f"adm:sellreq:list:{idx + 1}"))

        btn_rows = [
            [
                _btn("✅ واریز شد", f"adm:sellreq:pay:{req.pk}", ui.SUCCESS),
                _btn("📸 ارسال رسید", f"adm:sellreq:receipt:{req.pk}", ui.PRIMARY),
                _btn("❌ رد و بازگشت سکه", f"adm:sellreq:rej:{req.pk}", ui.DANGER),
            ]
        ]
        if nav_row:
            btn_rows.append(nav_row)
        btn_rows.append([_btn("🔙 بازگشت به پنل", "adm:home")])

        await answer(query)
        await show(text, InlineKeyboardMarkup(btn_rows))
        return

    # ارسال رسید برای تسویه
    if action in ("sell", "sellreq") and sub == "receipt":
        req_id = int(parts[3])
        req = await db(lambda: SellRequest.objects.filter(pk=req_id).select_related("user").first())()
        if not req or req.status != SellRequest.Status.PENDING:
            await answer(query, "این درخواست قبلاً بررسی شده است.", alert=True)
            return
        context.user_data["admin_flow"] = {"step": "sell_receipt", "req_id": req.pk}
        await answer(query)
        await reply(
            update,
            f"📸 <b>ارسال رسید واریز برای درخواست #{fa_num(req.pk)}</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"👤 کاربر: <b>{escape(req.user.display_name)}</b> (<code>{req.user.tg_id}</code>)\n"
            f"💵 مبلغ: <b>{fa_num(req.amount_toman)} تومان</b>\n"
            f"💳 کارت: <code>{escape(req.card_number)}</code>\n\n"
            "لطفاً عکس فیش واریزی را ارسال کنید (یا برای انصراف بنویسید «لغو»):",
        )
        return

    # تایید واریز / رد فروش
    if action in ("sell", "sellreq") and sub in ("pay", "rej"):
        req_id = int(parts[3])
        req = await db(lambda: SellRequest.objects.filter(pk=req_id).select_related("user").first())()
        if not req or req.status != SellRequest.Status.PENDING:
            await answer(query, "این درخواست قبلاً بررسی شده است.", alert=True)
            return

        if sub == "pay":
            req.status = SellRequest.Status.PAID
            req.reviewed_at = timezone.now()
            req.admin_note = f"Paid by {user.tg_id}"
            await db(req.save)(update_fields=["status", "reviewed_at", "admin_note"])
            await answer(query, f"واریز {req.amount_toman:,} تومان تایید شد ✅")
            try:
                await tg_call(
                    context.bot.send_message,
                    req.user.tg_id,
                    texts.WALLET_SELL_PAID_USER.format(id=fa_num(req.pk), amount=fa_num(req.amount_toman), card=escape(req.card_number)),
                    parse_mode="HTML",
                )
            except Exception:
                pass
        else:
            await db(apply_transaction)(req.user, req.coins, TxType.REFUND, f"sell_refund:{req.pk}")
            req.status = SellRequest.Status.REJECTED
            req.reviewed_at = timezone.now()
            req.admin_note = f"Rejected by {user.tg_id}"
            await db(req.save)(update_fields=["status", "reviewed_at", "admin_note"])
            await answer(query, f"درخواست رد و {req.coins} سکه برگشت داده شد.")
            try:
                await tg_call(
                    context.bot.send_message,
                    req.user.tg_id,
                    texts.WALLET_SELL_REJECTED_USER.format(id=fa_num(req.pk), coins=fa_num(req.coins)),
                    parse_mode="HTML",
                )
            except Exception:
                pass

        query.data = "adm:sellreq:list:0"
        await admin_callback(update, context, user, query)
        return

    # آمار کلی
    if action == "stats":
        data = await _stats()
        info = catalog(include_disabled=True).get(data["top_game"]) if data["top_game"] else None
        st_text = texts.STATS.format(
            users=fa_num(data["users"]),
            dau=fa_num(data["dau"]),
            groups=fa_num(data["groups"]),
            matches=fa_num(data["matches"]),
            matches_today=fa_num(data["matches_today"]),
            top_game=f"{info.emoji} {info.title_fa}" if info else "—",
            coins=fa_num(data["coins"]),
        )
        kb = InlineKeyboardMarkup([[_btn("🔙 بازگشت به پنل", "adm:home")]])
        await show(st_text, kb)
        return

    # ارسال همگانی
    if action == "bcast" and sub == "prompt":
        context.user_data["admin_flow"] = {"step": "broadcast"}
        await answer(query)
        prompt = (
            "📢 <b>ارسال پیام همگانی به اعضای ربات</b>\n"
            "━━━━━━━━━━━━━━\n"
            "متن پیام مورد نظرتان را بفرستید یا پیامی را فوروارد کنید تا برای همه کاربران ارسال شود."
        )
        kb = InlineKeyboardMarkup([[_btn("❌ انصراف", "adm:home")]])
        await show(prompt, kb)
        return


async def admin_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser) -> bool:
    flow = context.user_data.get("admin_flow")
    if not flow or not await is_superadmin(user.tg_id):
        return False

    step = flow.get("step")
    message = update.effective_message
    text = (message.text or "").strip()

    if text in ("/cancel", "لغو"):
        context.user_data.pop("admin_flow", None)
        await reply(update, "عملیات لغو شد.")
        return True

    if step == "sell_receipt":
        req_id = flow.get("req_id")
        if not message.photo and not message.document:
            await reply(update, "❌ لطفاً عکس فیش/رسید واریز را ارسال کنید (یا عبارت «لغو» برای انصراف).")
            return True
        photo_id = message.photo[-1].file_id if message.photo else message.document.file_id
        req = await db(lambda: SellRequest.objects.filter(pk=req_id).select_related("user").first())()
        if not req:
            context.user_data.pop("admin_flow", None)
            await reply(update, "❌ درخواست یافت نشد.")
            return True
        if req.status != SellRequest.Status.PENDING:
            context.user_data.pop("admin_flow", None)
            await reply(update, f"این درخواست قبلاً {req.get_status_display()} شده است.")
            return True

        req.status = SellRequest.Status.PAID
        req.reviewed_at = timezone.now()
        req.admin_note = f"Paid with receipt by {user.tg_id}"
        await db(req.save)(update_fields=["status", "reviewed_at", "admin_note"])
        context.user_data.pop("admin_flow", None)

        user_caption = (
            f"🎉 <b>مبلغ فروش سکه واریز شد!</b>\n{texts.DIVIDER}\n"
            f"شناسه درخواست: #{fa_num(req.pk)}\n"
            f"💵 مبلغ واریزی: <b>{fa_num(req.amount_toman)}</b> تومان\n"
            f"💳 شماره کارت: <code>{escape(req.card_number)}</code>\n\n"
            f"📸 <b>رسید واریز بانکی توسط مدیریت ضمیمه گردید.</b> از همراهی‌تان سپاسگزاریم!"
        )
        try:
            await tg_call(
                context.bot.send_photo,
                req.user.tg_id,
                photo=photo_id,
                caption=user_caption,
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.warning("failed to send receipt photo to user %s: %s", req.user.tg_id, exc)

        try:
            from .wallet import update_all_admin_alerts

            sync_text = (
                f"💸 <b>درخواست فروش سکه #{fa_num(req.pk)}</b>\n"
                f"👤 کاربر: <b>{escape(req.user.display_name)}</b>\n"
                f"💵 مبلغ: <b>{fa_num(req.amount_toman)} تومان</b>\n\n"
                f"✅ <b>واریز شد و فیش ارسال گردید</b> توسط {escape(user.display_name)}"
            )
            await update_all_admin_alerts(context, "sell", req.pk, sync_text, is_photo=False)
        except Exception as exc:
            logger.warning("failed to sync sell alert: %s", exc)

        await reply(
            update,
            f"✅ رسید واریزی با موفقیت برای کاربر ارسال شد و وضعیت درخواست #{fa_num(req.pk)} به «واریز شد» ثبت گردید.",
            InlineKeyboardMarkup([[_btn("🔙 بازگشت به پنل", "adm:home")]]),
        )
        return True

    if step == "set_card":
        parts = text.split(None, 1)
        raw_card = parts[0].replace("-", "").replace(" ", "")
        holder = parts[1].strip() if len(parts) > 1 else ""
        if len(raw_card) < 16 or not raw_card[:16].isdigit():
            await reply(update, "❌ شماره کارت باید حداقل ۱۶ رقم عددی باشد.\nمثال:\n<code>6219861997831192 امید فیروزآبادی</code>")
            return True
        eco = await db(EconomySettings.load)()
        eco.card_number = raw_card[:16]
        eco.card_holder = holder[:128]
        await db(eco.save)()
        context.user_data.pop("admin_flow", None)
        await reply(
            update,
            f"✅ <b>کارت واریز با موفقیت ذخیره شد:</b>\n"
            f"شماره کارت: <code>{eco.card_number}</code>\n"
            f"به نام: <b>{escape(eco.card_holder or '—')}</b>",
            InlineKeyboardMarkup([[_btn("🔙 بازگشت به پنل ادمین", "adm:home")]]),
        )
        return True

    if step == "set_rate":
        parts = [parse_int(p) for p in text.split()]
        if len(parts) < 2 or parts[0] is None or parts[1] is None:
            await reply(update, "❌ لطفاً حداقل دو عدد برای [نرخ هر سکه] و [درصد کارمزد] ارسال کنید.\nمثال:\n<code>1000 10 100 1000</code>")
            return True
        coin_price = max(1, parts[0])
        fee_pct = max(0, min(100, parts[1]))
        min_sell = parts[2] if len(parts) > 2 and parts[2] is not None and parts[2] > 0 else 100
        sell_price = parts[3] if len(parts) > 3 and parts[3] is not None and parts[3] > 0 else coin_price

        eco = await db(EconomySettings.load)()
        eco.coin_price_toman = coin_price
        eco.topup_fee_percent = fee_pct
        eco.min_sell_coins = min_sell
        eco.coin_sell_price_toman = sell_price
        await db(eco.save)()
        context.user_data.pop("admin_flow", None)
        await reply(
            update,
            f"✅ <b>تنظیمات اقتصادی به‌روزرسانی شد:</b>\n"
            f"نرخ خرید هر سکه: <b>{fa_num(coin_price)}</b> تومان\n"
            f"کارمزد شارژ: <b>{fa_num(fee_pct)}٪</b>\n"
            f"حداقل فروش: <b>{fa_num(min_sell)}</b> سکه\n"
            f"نرخ فروش هر سکه: <b>{fa_num(sell_price)}</b> تومان",
            InlineKeyboardMarkup([[_btn("🔙 بازگشت به پنل ادمین", "adm:home")]]),
        )
        return True

    if step == "add_admin":
        aid = parse_int(text)
        if aid is None or aid <= 0:
            await reply(update, "❌ لطفاً یک شناسه عددی تلگرام معتبر ارسال کنید.")
            return True
        eco = await db(EconomySettings.load)()
        extra = list(getattr(eco, "extra_admin_ids", []) or [])
        if aid not in extra:
            extra.append(aid)
            eco.extra_admin_ids = extra
            await db(eco.save)()
            from .common import get_all_admin_ids
            await get_all_admin_ids()
            msg = f"✅ کاربر با شناسه <code>{aid}</code> به ادمین‌های ربات اضافه شد."
        else:
            msg = "این کاربر قبلاً ادمین بوده است."
        context.user_data.pop("admin_flow", None)
        await reply(update, msg, InlineKeyboardMarkup([[_btn("🔙 مدیریت ادمین‌ها", "adm:admins")]]))
        return True

    if step == "broadcast":
        context.user_data.pop("admin_flow", None)
        await broadcast(update, context, user)
        return True

    if step == "ask_msg_target":
        from ..users import find_user

        target = await find_user(text)
        if not target:
            target_tg_id = parse_int(text)
            if target_tg_id:
                target = await db(TelegramUser.objects.filter(tg_id=target_tg_id).first)()
        if not target:
            await reply(update, "❌ کاربر یافت نشد. لطفاً شناسه عددی تلگرام یا آیدی کاربر را صحیح وارد کنید:")
            return True

        context.user_data["admin_flow"] = {
            "step": "send_dm",
            "target_tg_id": target.tg_id,
            "target_name": target.display_name,
        }
        uname = f" (@{target.username})" if target.username else ""
        await reply(
            update,
            f"👤 کاربر انتخاب شد: <b>{escape(target.display_name)}</b>{uname} (<code>{target.tg_id}</code>)\n\n"
            f"📝 اکنون متن پیام (یا عکس همراه با متن) را ارسال فرمایید تا برای کاربر فرستاده شود:\n"
            f"<i>(جهت انصراف عبارت <code>لغو</code> را ارسال نمایید)</i>",
            InlineKeyboardMarkup([[_btn("❌ انصراف", "adm:home")]]),
        )
        return True

    if step == "send_dm":
        target_tg_id = flow.get("target_tg_id")
        target_name = flow.get("target_name", str(target_tg_id))
        msg_text = message.text or message.caption or ""
        photo_id = message.photo[-1].file_id if message.photo else (message.document.file_id if message.document else None)

        if not msg_text and not photo_id:
            await reply(update, "❌ لطفاً متن پیام یا عکس را ارسال کنید (یا عبارت «لغو» برای انصراف).")
            return True

        user_content = (
            f"📩 <b>پیام از طرف پشتیبانی و مدیریت ربات:</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"{escape(msg_text)}\n"
            f"━━━━━━━━━━━━━━\n"
            f"✍️ <i>جهت پاسخ دادن به مدیریت، روی دکمه زیر کلیک کنید:</i>"
        )
        reply_kb = InlineKeyboardMarkup([[ui.button("✍️ پاسخ به پشتیبانی", "pm:support", style=ui.PRIMARY)]])

        delivered = False
        try:
            if photo_id:
                await tg_call(
                    context.bot.send_photo,
                    chat_id=target_tg_id,
                    photo=photo_id,
                    caption=user_content,
                    parse_mode="HTML",
                    reply_markup=reply_kb,
                )
            else:
                await tg_call(
                    context.bot.send_message,
                    chat_id=target_tg_id,
                    text=user_content,
                    parse_mode="HTML",
                    reply_markup=reply_kb,
                )
            delivered = True
        except Exception as exc:
            logger.warning("failed to send dm to %s: %s", target_tg_id, exc)

        context.user_data.pop("admin_flow", None)
        if delivered:
            await reply(
                update,
                f"✅ پیام شما با موفقیت برای <b>{escape(target_name)}</b> (<code>{target_tg_id}</code>) ارسال گردید.",
                InlineKeyboardMarkup([[_btn("🔙 بازگشت به پنل", "adm:home")]]),
            )
        else:
            await reply(
                update,
                f"❌ ارسال پیام به کاربر (<code>{target_tg_id}</code>) ناموفق بود. ممکن است کاربر ربات را بلاک کرده باشد.",
                InlineKeyboardMarkup([[_btn("🔙 بازگشت به پنل", "adm:home")]]),
            )
        return True

    return False


@callback
async def admin_dm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, query):
    if not await is_superadmin(user.tg_id):
        await answer(query, "دسترسی غیرمجاز است.", alert=True)
        return

    parts = query.data.split(":")
    target_tg_id = int(parts[2])
    target = await db(TelegramUser.objects.filter(tg_id=target_tg_id).first)()
    target_name = target.display_name if target else str(target_tg_id)
    target_uname = f" (@{target.username})" if (target and target.username) else ""

    context.user_data["admin_flow"] = {
        "step": "send_dm",
        "target_tg_id": target_tg_id,
        "target_name": target_name,
    }
    await answer(query)
    await reply(
        update,
        f"✉️ <b>ارسال پیام به کاربر:</b>\n"
        f"👤 <b>{escape(target_name)}</b>{target_uname} (<code>{target_tg_id}</code>)\n"
        f"━━━━━━━━━━━━━━\n"
        f"لطفاً متن پیام (یا عکس همراه با متن) را ارسال فرمایید تا بلافاصله برای کاربر ارسال شود:\n\n"
        f"<i>(جهت انصراف عبارت <code>لغو</code> را ارسال نمایید)</i>",
        InlineKeyboardMarkup([[_btn("❌ انصراف", "adm:home")]]),
    )


async def user_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser) -> bool:
    flow = context.user_data.get("support_flow")
    if not flow:
        return False

    message = update.effective_message
    text = (message.text or message.caption or "").strip()
    photo_id = message.photo[-1].file_id if message.photo else (message.document.file_id if message.document else None)

    if text in ("/cancel", "لغو"):
        context.user_data.pop("support_flow", None)
        await reply(update, "عملیات ارسال پیام به پشتیبانی لغو شد.")
        return True

    if not text and not photo_id:
        await reply(update, "لطفاً پیام متنی یا تصویر خود را ارسال فرمایید (یا عبارت «لغو» را ارسال کنید).")
        return True

    context.user_data.pop("support_flow", None)

    uname = f"@{escape(user.username)}" if user.username else "<i>ندارد</i>"
    admin_caption = (
        "📨 <b>تیکت / پیام جدید از کاربر</b>\n"
        "━━━━━━━━━━━━━━\n"
        f"👤 کاربر: <a href=\"tg://user?id={user.tg_id}\">{escape(user.display_name)}</a>\n"
        f"🔗 آیدی تلگرام: {uname}\n"
        f"🆔 شناسه عددی: <code>{user.tg_id}</code>\n"
        f"📅 تاریخ: {fa_date(timezone.localtime(timezone.now()))}\n"
        "━━━━━━━━━━━━━━\n"
        f"📝 <b>متن پیام:</b>\n"
        f"{escape(text)}"
    )

    admin_kb = InlineKeyboardMarkup(
        [
            [
                _btn("✍️ پاسخ به کاربر", f"adm:dm:{user.tg_id}", ui.PRIMARY),
            ]
        ]
    )

    from .common import get_all_admin_ids

    for admin_id in await get_all_admin_ids():
        try:
            if photo_id:
                await tg_call(
                    context.bot.send_photo,
                    chat_id=admin_id,
                    photo=photo_id,
                    caption=admin_caption,
                    parse_mode="HTML",
                    reply_markup=admin_kb,
                )
            else:
                await tg_call(
                    context.bot.send_message,
                    chat_id=admin_id,
                    text=admin_caption,
                    parse_mode="HTML",
                    reply_markup=admin_kb,
                )
        except Exception as exc:
            logger.warning("failed to send support ticket to admin %s: %s", admin_id, exc)

    await reply(
        update,
        "✅ <b>پیام شما به پشتیبانی ارسال شد.</b>\n"
        "پیام شما برای تیم مدیریت ارسال گردید؛ به محض بررسی پاسخ آن در همین پیوی برای شما ارسال خواهد شد.",
    )
    return True


