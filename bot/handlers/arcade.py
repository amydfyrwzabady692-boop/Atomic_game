"""/arcade — تمرین آزاد بازی‌های آرکید از پیوی (دکمه‌ی web_app، بدون سکه)."""

from django.conf import settings
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from arcade.sim import all_simulators
from core import texts
from core.models import TelegramUser
from games.catalog import arcade_enabled

from .common import command, reply


@command(private=True)
async def arcade(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    base = settings.MINIAPP_BASE_URL.rstrip("/")
    if not base.startswith("https://"):
        await reply(update, texts.ARCADE_NOT_CONFIGURED)
        return
    buttons = [
        InlineKeyboardButton(f"{sim.emoji} {sim.title_fa}", web_app=WebAppInfo(url=f"{base}/arcade/play/{key}/"))
        for key, sim in all_simulators().items()
        if arcade_enabled(key)
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    await reply(update, texts.ARCADE_PRACTICE, InlineKeyboardMarkup(rows))
