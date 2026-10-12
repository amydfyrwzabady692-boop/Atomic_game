"""/arcade — تمرین آزاد بازی‌های آرکید از پیوی (دکمه‌ی web_app، بدون سکه)."""

from django.conf import settings
from telegram import InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from arcade.sim import all_simulators
from core import texts
from core.models import TelegramUser
from games.catalog import arcade_enabled

from .. import render, ui
from .common import command, is_superadmin, reply


@command(private=True)
async def arcade(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    base = settings.MINIAPP_BASE_URL.rstrip("/")
    if not render.arcade_ready():
        text = texts.ARCADE_NOT_CONFIGURED
        if is_superadmin(user.tg_id):
            text += texts.ARCADE_SETUP_HINT.format(short=settings.MINIAPP_SHORT_NAME)
        await reply(update, text)
        return
    buttons = [
        ui.button(f"{sim.emoji} {sim.title_fa}", web_app=WebAppInfo(url=f"{base}/arcade/play/{key}/"), style=ui.PRIMARY)
        for key, sim in all_simulators().items()
        if arcade_enabled(key)
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    await reply(update, texts.ARCADE_PRACTICE, InlineKeyboardMarkup(rows))
