"""ساخت Application تلگرام، ثبت handlerها و jobهای زمان‌بندی‌شده."""

import datetime
import logging
from html import escape
from zoneinfo import ZoneInfo

from django.conf import settings
from telegram import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats, Update
from telegram.ext import (
    AIORateLimiter,
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from core import texts
from core.texts import fa_num
from games import config as game_config
from leaderboard.queries import announce_weekly_champions

from .concurrency import PerChatUpdateProcessor
from .db import db
from .handlers import admin, arcade, flow, group, group_settings, private, shop
from .runner import MatchManager
from .tg import tg_call

logger = logging.getLogger(__name__)

ALLOWED_UPDATES = ["message", "callback_query", "my_chat_member"]
TEHRAN = ZoneInfo("Asia/Tehran")
GAME_SETTINGS_REFRESH_SECONDS = 15

PRIVATE_COMMANDS = [
    ("start", "شروع"),
    ("me", "پروفایل من"),
    ("daily", "جایزه‌ی روزانه"),
    ("invite", "دعوت دوستان"),
    ("shop", "فروشگاه"),
    ("arcade", "تمرین آزاد آرکید"),
    ("history", "تراکنش‌های سکه"),
    ("gtop", "برترین‌های کل ربات"),
    ("help", "راهنما"),
]
GROUP_COMMANDS = [
    ("game", "ساخت مسابقه"),
    ("top", "رتبه‌بندی گروه"),
    ("me", "پروفایل من"),
    ("rules", "قوانین"),
    ("cancel", "لغو مسابقه"),
    ("settings", "تنظیمات گروه (ادمین)"),
]


async def weekly_champions_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """شنبه‌ها: اعلام قهرمان هفته‌ی گذشته در هر گروه. جدول هفته خودبه‌خود از نو شروع می‌شود."""
    for chat_group, champion in await db(announce_weekly_champions)():
        await tg_call(
            context.bot.send_message,
            chat_group.chat_id,
            texts.WEEKLY_CHAMPION.format(
                name=escape(champion.user.display_name), coins=fa_num(champion.coins), wins=fa_num(champion.wins)
            ),
            parse_mode="HTML",
        )


async def game_settings_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """تغییرهای پنل ادمین (تعداد شرکت‌کننده، فعال/غیرفعال) را به حافظه‌ی ربات می‌آورد."""
    await db(game_config.reload)()


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(
        "unhandled error",
        exc_info=context.error,
        extra={"update_id": getattr(update, "update_id", None)},
    )


async def post_init(application: Application) -> None:
    me = await application.bot.get_me()
    application.bot_data["username"] = me.username
    application.bot_data["bot_id"] = me.id
    # اگر Privacy Mode روشن باشد ربات فقط در گروه‌هایی که ادمین است پیام‌ها را می‌بیند
    application.bot_data["reads_all"] = bool(getattr(me, "can_read_all_group_messages", False))
    manager = MatchManager(application)
    application.bot_data["manager"] = manager
    await tg_call(
        application.bot.set_my_commands,
        [BotCommand(c, d) for c, d in PRIVATE_COMMANDS],
        scope=BotCommandScopeAllPrivateChats(),
    )
    await tg_call(
        application.bot.set_my_commands,
        [BotCommand(c, d) for c, d in GROUP_COMMANDS],
        scope=BotCommandScopeAllGroupChats(),
    )
    await db(game_config.reload)()
    application.job_queue.run_repeating(
        game_settings_job, interval=GAME_SETTINGS_REFRESH_SECONDS, name="game_settings"
    )
    await manager.recover()
    # شنبه ساعت ۰۰:۰۵ تهران (در PTB روز ۶ = شنبه)، و یک بار هم موقع بالا آمدن برای جبران خاموشی
    application.job_queue.run_daily(
        weekly_champions_job, time=datetime.time(0, 5, tzinfo=TEHRAN), days=(6,), name="weekly_champions"
    )
    application.job_queue.run_once(weekly_champions_job, when=30, name="weekly_champions_catchup")
    logger.info("bot ready", extra={"username": me.username})


async def post_shutdown(application: Application) -> None:
    manager = application.bot_data.get("manager")
    if manager is not None:
        await manager.shutdown()


def register_handlers(application: Application) -> None:
    add = application.add_handler
    add(CommandHandler("start", private.start))
    add(CommandHandler("help", private.help_cmd))
    add(CommandHandler("me", private.me))
    add(CommandHandler("daily", private.daily))
    add(CommandHandler("invite", private.invite))
    add(CommandHandler("history", private.history))
    add(CommandHandler("shop", shop.shop))
    add(CommandHandler("arcade", arcade.arcade))

    add(CommandHandler("game", flow.game))
    add(CommandHandler("cancel", group.cancel))
    add(CommandHandler("top", group.top))
    add(CommandHandler("gtop", group.gtop))
    add(CommandHandler("rules", group.rules))
    add(CommandHandler("settings", group_settings.settings_cmd))

    add(CommandHandler("grant", admin.grant))
    add(CommandHandler("ban", admin.ban))
    add(CommandHandler("unban", admin.unban))
    add(CommandHandler("broadcast", admin.broadcast))
    add(CommandHandler("stats", admin.stats))

    add(CallbackQueryHandler(group.game_callback, pattern=r"^g:\d+:"))
    add(CallbackQueryHandler(group.join_callback, pattern=r"^j:\d+$"))
    add(CallbackQueryHandler(group.cancel_callback, pattern=r"^x:\d+$"))
    add(CallbackQueryHandler(flow.new_game_callback, pattern=r"^n:"))
    add(CallbackQueryHandler(group.top_callback, pattern=r"^top:"))
    add(CallbackQueryHandler(group_settings.settings_callback, pattern=r"^set:"))
    add(CallbackQueryHandler(shop.shop_callback, pattern=r"^shop:"))
    add(CallbackQueryHandler(group.rules_callback, pattern=r"^rules:"))
    add(CallbackQueryHandler(group.rules_alert_callback, pattern=r"^rl:"))
    add(CallbackQueryHandler(private.menu_callback, pattern=r"^pm:"))

    add(ChatMemberHandler(group.my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    add(MessageHandler(filters.StatusUpdate.MIGRATE, group.migrated))
    # فقط پیام‌های تازه (نه ادیت‌شده)، متنی، غیر دستور، داخل گروه
    add(
        MessageHandler(
            filters.UpdateType.MESSAGE & filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, group.group_text
        )
    )
    application.add_error_handler(on_error)


def build_application() -> Application:
    if not settings.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN تنظیم نشده است (فایل .env را ببینید).")
    application = (
        ApplicationBuilder()
        .token(settings.BOT_TOKEN)
        .rate_limiter(AIORateLimiter(max_retries=2))
        # چت‌های مختلف هم‌زمان پردازش می‌شوند تا کندی یک گروه بقیه را معطل نکند
        .concurrent_updates(PerChatUpdateProcessor(settings.BOT_CONCURRENT_UPDATES))
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    register_handlers(application)
    return application


def run() -> None:
    application = build_application()
    if settings.WEBHOOK_URL:
        path = f"tg/{settings.WEBHOOK_SECRET or 'hook'}"
        application.run_webhook(
            listen=settings.WEBHOOK_LISTEN,
            port=settings.WEBHOOK_PORT,
            url_path=path,
            webhook_url=f"{settings.WEBHOOK_URL.rstrip('/')}/{path}",
            secret_token=settings.WEBHOOK_SECRET or None,
            allowed_updates=ALLOWED_UPDATES,
        )
    else:
        application.run_polling(allowed_updates=ALLOWED_UPDATES, drop_pending_updates=False)


__all__ = ["Update", "build_application", "run"]
