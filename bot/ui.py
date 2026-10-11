"""دکمه‌های اینلاین رنگی.

تلگرام از Bot API 9.4 فیلد ``style`` را برای دکمه‌ها دارد: ``primary`` (آبی)، ``success`` (سبز) و
``danger`` (قرمز). کتابخانه‌ی python-telegram-bot نسخه‌ی ۲۱ این فیلد را نمی‌شناسد، برای همین از راه
``api_kwargs`` فرستاده می‌شود. کلاینت‌های قدیمی تلگرام فیلد را نادیده می‌گیرند و دکمه را ساده نشان
می‌دهند. با ``BUTTON_STYLES=False`` در ``.env`` رنگ‌ها کاملاً خاموش می‌شوند.
"""

from django.conf import settings
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from games.engine.base import DANGER, PRIMARY, SUCCESS

STYLES = (PRIMARY, SUCCESS, DANGER)


def button(text: str, data: str | None = None, *, url: str | None = None, web_app=None, style: str = ""):
    """یک دکمه‌ی اینلاین؛ ``style`` یکی از ``primary``، ``success`` یا ``danger`` است (یا خالی)."""
    extra = {"style": style} if style in STYLES and getattr(settings, "BUTTON_STYLES", True) else None
    return InlineKeyboardButton(text, callback_data=data, url=url, web_app=web_app, api_kwargs=extra)


def style_of(telegram_button) -> str:
    """رنگ یک دکمه‌ی ساخته‌شده (برای تست‌ها و بررسی)."""
    return (telegram_button.api_kwargs or {}).get("style", "")


def rows(buttons: list, per_row: int) -> list[list]:
    return [buttons[i : i + per_row] for i in range(0, len(buttons), per_row)]


def markup(button_rows: list[list]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(button_rows)


__all__ = ["DANGER", "PRIMARY", "STYLES", "SUCCESS", "button", "markup", "rows", "style_of"]
