"""دعوت به بازی در گروه‌ها و پست‌های آماده‌ی کانال.

- هر ``promo_minutes`` دقیقه (پیش‌فرض ۱۲۰، یعنی هر ۲ ساعت؛ پنل /admin ← «📣 تبلیغ و کانال») در هر گروه فعال یک پیام بی‌صدا با
  دکمه‌های بازی فرستاده می‌شود؛ متن‌ها به نوبت عوض می‌شوند، پیام قبلی همان گروه پاک می‌شود و گروهی که همان
  لحظه مسابقه دارد رد می‌شود. ادمین هر گروه با /settings خاموشش می‌کند.
- پست‌های آماده‌ی کانال (معرفی ربات، آموزش، کیف پول، تقسیم جایزه، …) با دکمه‌های لینک‌دار از همین بخش پنل
  دیده و در کانال منتشر می‌شوند.
"""

import asyncio
import logging
import time
from html import escape

from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ChatType
from telegram.error import BadRequest, ChatMigrated, Forbidden, RetryAfter, TelegramError
from telegram.ext import ContextTypes

from core import texts
from core.models import TelegramGroup
from core.redis import get_redis
from core.texts import fa_num
from wallet.models import EconomySettings

from .. import render, ui
from ..db import db
from ..tg import tg_call
from .common import admin_permissions, answer, callback, reply

logger = logging.getLogger(__name__)

CHECK_SECONDS = 60  # هر دقیقه بررسی می‌شود که وقت پیام بعدی رسیده یا نه
EVERY_CHOICES = [5, 15, 30, 60, 120, 180, 240, 360]  # دکمه‌ی پنل به ترتیب می‌چرخد (پیش‌فرض ۱۲۰)
SEND_GAP = 0.06  # فاصله‌ی ارسال بین گروه‌ها (سقف کلی تلگرام حدود ۳۰ پیام در ثانیه است)
LAST_MESSAGE_SECONDS = 7 * 24 * 3600
POSTS = {key: (title, body) for key, title, body in texts.CHANNEL_POSTS}


# ================================================================== متن‌ها و دکمه‌ها
def fa_every(minutes: int) -> str:
    """۱۲۰ ← «۲ ساعت»، ۹۰ ← «۹۰ دقیقه»."""
    if minutes >= 60 and minutes % 60 == 0:
        return f"{fa_num(minutes // 60)} ساعت"
    return f"{fa_num(minutes)} دقیقه"


def next_every(minutes: int) -> int:
    """گزینه‌ی بعدی فاصله در پنل (بعد از بزرگ‌ترین، دوباره کوچک‌ترین)."""
    later = [m for m in EVERY_CHOICES if m > minutes]
    return later[0] if later else EVERY_CHOICES[0]


def _variants(daily: bool, arcade: bool) -> list[str]:
    return [text for text, need in texts.PROMO_VARIANTS if not need or (need == "daily" and daily) or (need == "arcade" and arcade)]


def _game_counts() -> tuple[int, int]:
    """(تعداد بازی‌های گروهی، تعداد بازی‌های آرکید) برای پر کردن متن‌ها."""
    from arcade.sim import all_simulators
    from games.catalog import catalog

    return sum(1 for k in catalog() if not k.startswith("arcade_")), len(all_simulators())


def promo_message(index: int, username: str, daily: bool) -> tuple[str, InlineKeyboardMarkup]:
    arcade = render.arcade_ready()
    variants = _variants(daily, arcade)
    games, arcade_games = _game_counts()
    text = variants[index % len(variants)].format(games=fa_num(games), arcade=fa_num(arcade_games))
    start = lambda payload: render.start_link(username, payload)  # noqa: E731
    rows = [[ui.button(texts.PROMO_GAME_BTN, "promo:game", style=ui.SUCCESS), ui.button(texts.PROMO_HELP_BTN, "promo:help", style=ui.PRIMARY)]]
    if arcade:
        rows.append(
            [
                ui.button(texts.PROMO_MINIAPP_BTN, url=render.miniapp_home_link(username), style=ui.PRIMARY),
                ui.button(texts.PROMO_DUEL_BTN, url=start("duel"), style=ui.PRIMARY),
            ]
        )
    last = [ui.button(texts.PROMO_WALLET_BTN, url=start("wallet"), style=ui.PRIMARY)]
    if daily:
        last.insert(0, ui.button(texts.PROMO_DAILY_BTN, url=start("daily"), style=ui.SUCCESS))
    rows.append(last)
    return text, InlineKeyboardMarkup(rows)


def channel_post(key: str, username: str, eco: EconomySettings) -> tuple[str, InlineKeyboardMarkup]:
    """متن و دکمه‌های یک پست آماده؛ عددها از تنظیمات فعلی."""
    _, body = POSTS[key]
    games, arcade_games = _game_counts()
    text = body.format(
        bot=username,
        coin=texts.COIN,
        games=fa_num(games),
        arcade=fa_num(arcade_games),
        price=fa_num(eco.coin_price_toman),
        fee=fa_num(eco.topup_fee_percent),
        sell_price=fa_num(eco.coin_sell_price_toman),
        min_sell=fa_num(eco.min_sell_coins),
    )
    start = lambda payload: render.start_link(username, payload)  # noqa: E731
    rows = [[ui.button(texts.POST_START_BTN, url=start("channel"), style=ui.SUCCESS), ui.button(texts.POST_ADD_BTN, url=f"https://t.me/{username}?startgroup=true", style=ui.PRIMARY)]]
    if render.arcade_ready():
        rows.append([ui.button(texts.POST_MINIAPP_BTN, url=render.miniapp_home_link(username), style=ui.PRIMARY)])
    if key == "wallet":
        rows.append([ui.button(texts.POST_WALLET_BTN, url=start("wallet"), style=ui.PRIMARY)])
    if key == "faq":
        rows.append([ui.button(texts.POST_SUPPORT_BTN, url=start("support"), style=ui.PRIMARY)])
    return text, InlineKeyboardMarkup(rows)


# ================================================================== دکمه‌های پیام دعوت در گروه
@callback
async def promo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user, query):
    from . import flow
    from .forcejoin import gate_in_group

    action = query.data.split(":", 1)[1]
    if action == "help":
        await answer(query, texts.PROMO_HELP_ALERT, alert=True)
        return
    if update.effective_chat.type == ChatType.PRIVATE:
        await answer(query, texts.PROMO_ONLY_GROUP, alert=True)
        return
    await answer(query)
    if await gate_in_group(update, context, user):
        await flow.open_menu(update, context, user)


# ================================================================== ارسال دوره‌ای
@db
def _promo_groups() -> list[int]:
    return list(TelegramGroup.objects.filter(is_active=True, promo_enabled=True).values_list("chat_id", flat=True))


@db
def _deactivate(chat_id: int) -> None:
    TelegramGroup.objects.filter(chat_id=chat_id).update(is_active=False)


@db
def _migrate(old: int, new: int) -> None:
    if not TelegramGroup.objects.filter(chat_id=new).exists():
        TelegramGroup.objects.filter(chat_id=old).update(chat_id=new)


async def send_promo(bot, chat_id: int, text: str, markup) -> bool:
    """پیام دعوت را در یک گروه می‌گذارد و پیام قبلی همان گروه را پاک می‌کند. ``True`` اگر فرستاده شد."""
    redis = get_redis()
    key = f"promo:msg:{chat_id}"
    try:
        sent = await bot.send_message(
            chat_id, text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True, disable_notification=True
        )
    except RetryAfter as exc:
        wait = exc.retry_after.total_seconds() if hasattr(exc.retry_after, "total_seconds") else float(exc.retry_after)
        await asyncio.sleep(min(30.0, wait) + 0.5)
        return False
    except ChatMigrated as exc:
        await _migrate(chat_id, exc.new_chat_id)
        return False
    except Forbidden:
        await _deactivate(chat_id)  # ربات از گروه بیرون شده
        return False
    except BadRequest as exc:
        if "chat not found" in str(exc).lower():
            await _deactivate(chat_id)
        return False  # مثلاً اجازه‌ی ارسال پیام ندارد
    except (TelegramError, OSError) as exc:
        logger.info("promo send failed", extra={"chat": chat_id, "error": str(exc)})
        return False
    previous = await redis.get(key)
    await redis.set(key, sent.message_id, ex=LAST_MESSAGE_SECONDS)
    if previous:
        await tg_call(bot.delete_message, chat_id, int(previous), retries=0)
    return True


async def remove_last_promo(bot, chat_id: int) -> None:
    """آخرین پیام دعوت این گروه را پاک می‌کند (وقتی ادمین گروه پیام دعوت را خاموش می‌کند)."""
    previous = await get_redis().getdel(f"promo:msg:{chat_id}")
    if previous:
        await tg_call(bot.delete_message, chat_id, int(previous), retries=0)


async def run_promo(application) -> tuple[int, int]:
    """یک دور پیام دعوت در همه‌ی گروه‌ها: (فرستاده‌شده، ردشده)."""
    redis = get_redis()
    eco = await db(EconomySettings.load)()
    username = render.bot_username(application)
    index = int(await redis.incr("promo:variant"))
    text, markup = promo_message(index, username, eco.daily_enabled)
    manager = application.bot_data.get("manager")
    sent = skipped = 0
    for chat_id in await _promo_groups():
        if manager is not None and manager.in_chat(chat_id):
            skipped += 1  # همین حالا بازی دارند؛ لازم نیست دعوت کنیم
            continue
        if await send_promo(application.bot, chat_id, text, markup):
            sent += 1
        else:
            skipped += 1
        await asyncio.sleep(SEND_GAP)
    await redis.set("promo:last_run", int(time.time()))
    logger.info("group promo sent", extra={"sent": sent, "skipped": skipped})
    return sent, skipped


async def run_promo_once(application) -> tuple[int, int] | None:
    """یک دور پیام دعوت، فقط اگر دور دیگری (زمان‌بندی یا «ارسال همین حالا»، در هر پروسه‌ای) در جریان نباشد.
    وگرنه ``None``؛ تا هیچ گروهی دو پیام دعوت هم‌زمان نگیرد."""
    redis = get_redis()
    if not await redis.set("promo:running", "1", ex=900, nx=True):
        return None
    try:
        return await run_promo(application)
    finally:
        await redis.delete("promo:running")


async def promo_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """هر دقیقه: اگر روشن است و وقتش رسیده، یک دور پیام دعوت (فقط یک پروسه در هر لحظه)."""
    redis = get_redis()
    eco = await db(EconomySettings.load)()
    if not eco.promo_enabled:
        return
    last = float(await redis.get("promo:last_run") or 0)
    if time.time() - last < max(5, eco.promo_minutes) * 60 - 5:
        return
    await run_promo_once(context.application)


# ================================================================== پنل: تبلیغ و کانال
def _btn(text: str, data: str, style: str = ""):
    return ui.button(text, data, style=style)


@db
def _promo_numbers() -> dict:
    groups = TelegramGroup.objects.filter(is_active=True)
    return {"eco": EconomySettings.load(), "on": groups.filter(promo_enabled=True).count(), "off": groups.filter(promo_enabled=False).count()}


async def _promo_screen():
    data = await _promo_numbers()
    eco = data["eco"]
    last = await get_redis().get("promo:last_run")
    if last:
        minutes = max(0, int(time.time() - float(last)) // 60)
        last_text = f"{fa_num(minutes)} دقیقه پیش"
    else:
        last_text = texts.ADMIN_PROMO_NEVER
    text = texts.ADMIN_PROMO.format(
        state=texts.ADMIN_ON if eco.promo_enabled else texts.ADMIN_OFF,
        every=fa_every(eco.promo_minutes),
        groups=fa_num(data["on"]),
        off=fa_num(data["off"]),
        last=last_text,
    )
    toggle = (texts.ADMIN_PROMO_OFF_BTN, ui.DANGER) if eco.promo_enabled else (texts.ADMIN_PROMO_ON_BTN, ui.SUCCESS)
    rows = [
        [_btn(toggle[0], "adm:promo:toggle", toggle[1]), _btn(texts.ADMIN_PROMO_EVERY_BTN.format(every=fa_every(eco.promo_minutes)), "adm:promo:every", ui.PRIMARY)],
        [_btn(texts.ADMIN_PROMO_PREVIEW_BTN, "adm:promo:preview"), _btn(texts.ADMIN_PROMO_NOW_BTN, "adm:promo:now", ui.PRIMARY)],
        [_btn(texts.ADMIN_POSTS_BTN, "adm:post:list", ui.PRIMARY)],
        [_btn(texts.ADMIN_BACK_TO_PANEL_BTN, "adm:home")],
    ]
    return text, InlineKeyboardMarkup(rows), data["on"]


@db
def _save_promo(**fields) -> EconomySettings:
    eco = EconomySettings.load()
    for name, value in fields.items():
        setattr(eco, name, value)
    eco.save(update_fields=[*fields, "updated_at"])
    return eco


def _posts_screen():
    rows = [[_btn(title, f"adm:post:show:{key}", ui.PRIMARY)] for key, (title, _) in POSTS.items()]
    rows.append([_btn(texts.BACK_BTN, "adm:promo:home")])
    return texts.ADMIN_POSTS, InlineKeyboardMarkup(rows)


@db
def _channels():
    from membership.models import ForcedChannel

    return list(ForcedChannel.objects.all())


async def publish(context, key: str, chat) -> tuple[bool, str]:
    """پست را در کانال می‌گذارد: (موفق؟، نام کانال برای پیام)."""
    eco = await db(EconomySettings.load)()
    text, markup = channel_post(key, render.bot_username(context), eco)
    sent = await tg_call(context.bot.send_message, chat, text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True, retries=1)
    return sent is not None, str(chat)


@callback
async def panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user, query):
    from .wallet import show_photo_or_text

    if "broadcast" not in await admin_permissions(user.tg_id):
        await answer(query, texts.ADMIN_NO_ACCESS, alert=True)
        return
    parts = query.data.split(":")
    section, action = parts[1], parts[2] if len(parts) > 2 else "home"
    arg = parts[3] if len(parts) > 3 else ""
    extra = parts[4] if len(parts) > 4 else ""

    async def show(text, markup):
        await show_photo_or_text(update, context, query, text, markup)

    context.user_data.pop("admin_flow", None)
    if section == "promo":
        if action == "toggle":
            eco = await db(EconomySettings.load)()
            eco = await _save_promo(promo_enabled=not eco.promo_enabled)
            await answer(query, texts.ADMIN_ON if eco.promo_enabled else texts.ADMIN_OFF)
        elif action == "every":
            eco = await db(EconomySettings.load)()
            eco = await _save_promo(promo_minutes=next_every(eco.promo_minutes))
            await answer(query, texts.ADMIN_PROMO_EVERY_BTN.format(every=fa_every(eco.promo_minutes)))
        elif action == "preview":
            eco = await db(EconomySettings.load)()
            index = int(await get_redis().get("promo:variant") or 0) + 1
            text, markup = promo_message(index, render.bot_username(context), eco.daily_enabled)
            await answer(query)
            await tg_call(context.bot.send_message, update.effective_chat.id, text, parse_mode="HTML", reply_markup=markup)
            return
        elif action == "now":
            _, _, groups = await _promo_screen()
            await answer(query)
            await show(
                texts.ADMIN_PROMO_NOW_SURE.format(groups=fa_num(groups)),
                InlineKeyboardMarkup([[_btn(texts.ADMIN_PROMO_NOW_SURE_BTN, "adm:promo:nowok", ui.SUCCESS)], [_btn(texts.BACK_BTN, "adm:promo:home")]]),
            )
            return
        elif action == "nowok":
            result = await run_promo_once(context.application)
            if result is None:  # همین حالا یک دور در حال ارسال است
                await answer(query, texts.ADMIN_PROMO_BUSY, alert=True)
            else:
                await answer(query, texts.ADMIN_PROMO_NOW_BTN)
                sent, skipped = result
                await tg_call(context.bot.send_message, update.effective_chat.id, texts.ADMIN_PROMO_SENT.format(sent=fa_num(sent), skipped=fa_num(skipped)))
        else:
            await answer(query)
        text, markup, _ = await _promo_screen()
        await show(text, markup)
        return

    # ---------------------------------------------------------- پست‌های کانال
    if action == "list" or arg not in POSTS:
        await answer(query)
        await show(*_posts_screen())
        return
    title = POSTS[arg][0]
    if action == "show":
        eco = await db(EconomySettings.load)()
        text, markup = channel_post(arg, render.bot_username(context), eco)
        rows = [list(row) for row in markup.inline_keyboard]
        rows += [[_btn(texts.ADMIN_POST_SEND_BTN, f"adm:post:pick:{arg}", ui.SUCCESS)], [_btn(texts.BACK_BTN, "adm:post:list")]]
        await answer(query)
        await show(text, InlineKeyboardMarkup(rows))
    elif action == "pick":
        rows = [[_btn(f"📢 {row.title or row.handle}"[:48], f"adm:post:to:{arg}:{row.pk}", ui.PRIMARY)] for row in await _channels()]
        rows += [[_btn(texts.ADMIN_POST_OTHER_BTN, f"adm:post:other:{arg}")], [_btn(texts.BACK_BTN, f"adm:post:show:{arg}")]]
        await answer(query)
        await show(texts.ADMIN_POST_PICK.format(title=escape(title)), InlineKeyboardMarkup(rows))
    elif action == "to":
        row = next((r for r in await _channels() if str(r.pk) == extra), None)
        if row is None:
            await answer(query)
            return
        ok, _ = await publish(context, arg, row.chat_id)
        name = row.title or row.handle
        await answer(query, (texts.ADMIN_POST_SENT if ok else texts.ADMIN_POST_FAILED).format(channel=name), alert=True)
    elif action == "other":
        context.user_data["admin_flow"] = {"step": "post_channel", "post": arg}
        await answer(query)
        await show(texts.ADMIN_POST_ASK_CHANNEL, InlineKeyboardMarkup([[_btn(texts.BACK_BTN, f"adm:post:pick:{arg}")]]))


async def flow_message(update: Update, context, user, flow: dict) -> bool:
    """مرحله‌ی «کانال دیگر» برای ارسال پست."""
    from .membership_admin import chat_ref

    if flow.get("step") != "post_channel" or flow.get("post") not in POSTS:
        return False
    ref = chat_ref(update.effective_message)
    if ref is None:
        await reply(update, texts.ADMIN_POST_BAD_CHANNEL)
        return True
    context.user_data.pop("admin_flow", None)
    ok, name = await publish(context, flow["post"], ref)
    back = InlineKeyboardMarkup([[_btn(texts.ADMIN_POSTS_BTN, "adm:post:list", ui.PRIMARY)]])
    await reply(update, (texts.ADMIN_POST_SENT if ok else texts.ADMIN_POST_FAILED).format(channel=escape(name)), back)
    return True

