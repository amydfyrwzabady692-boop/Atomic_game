"""محدودیت نرخ درخواست‌های تلگرام، تنظیم‌شده برای بازی‌های گروهی.

``AIORateLimiter`` پیش‌فرض کتابخانه دو مشکل برای این ربات داشت که بازی‌های گروه را کند می‌کرد:

۱. سقف «۲۰ پیام در دقیقه برای هر گروه» را روی *همه‌ی* درخواست‌های آن گروه می‌گذاشت؛ ویرایش شمارش معکوس لابی،
   منوی /game و حتی ``getChatMember`` (بررسی ادمین) سهمیه‌ی پیام‌های خود بازی را می‌خوردند و بعد سؤال‌ها و
   نتیجه‌ها چند ثانیه منتظر می‌ماندند. این‌جا فقط ارسال پیام سهمیه‌ی ۲۰تایی را مصرف می‌کند، ویرایش‌ها سهمیه‌ی
   جدای خودشان را دارند و درخواست‌های بی‌پیام (بررسی ادمین، حذف پیام) فقط زیر سقف کلی ربات‌اند.
۲. با یک خطای ``RetryAfter`` در *یک* گروه، همه‌ی درخواست‌های ربات در همه‌ی چت‌ها متوقف می‌شد. این‌جا فقط
   همان چت صبر می‌کند و بقیه‌ی گروه‌ها و پیوی‌ها بی‌وقفه کار می‌کنند.
"""

import asyncio
import contextlib
import logging
import time

from telegram.error import RetryAfter
from telegram.ext import AIORateLimiter

logger = logging.getLogger(__name__)

# متدهایی که پیام تازه در چت می‌سازند (همان چیزی که سقف «۲۰ پیام در دقیقه‌ی گروه» تلگرام درباره‌اش است)
SEND_METHODS = frozenset(
    {
        "sendMessage", "sendPhoto", "sendDice", "sendDocument", "sendAnimation", "sendVideo", "sendAudio",
        "sendVoice", "sendVideoNote", "sendSticker", "sendPoll", "sendMediaGroup", "sendLocation", "sendVenue",
        "sendContact", "sendInvoice", "sendGame", "copyMessage", "copyMessages", "forwardMessage", "forwardMessages",
    }
)  # fmt: skip
EDIT_METHODS = frozenset({"editMessageText", "editMessageCaption", "editMessageMedia", "editMessageReplyMarkup"})


def _seconds(value) -> float:
    return value.total_seconds() if hasattr(value, "total_seconds") else float(value)


class GroupGameRateLimiter(AIORateLimiter):
    def __init__(self, *, group_edit_max_rate: float = 40, **kwargs):
        super().__init__(**kwargs)
        self._edit_max_rate = group_edit_max_rate
        self._edit_limiters: dict = {}
        self._paused_until: dict = {}  # chat_id → زمان monotonic پایان مکث بعد از RetryAfter

    def _get_edit_limiter(self, group_id):
        from aiolimiter import AsyncLimiter

        if len(self._edit_limiters) > 512:
            # مثل خود کتابخانه: محدودکننده‌ی گروه‌هایی که الان پر نیستند دور ریخته می‌شود
            for key, limiter in list(self._edit_limiters.items()):
                if key != group_id and limiter.has_capacity(limiter.max_rate):
                    del self._edit_limiters[key]
        if group_id not in self._edit_limiters:
            self._edit_limiters[group_id] = AsyncLimiter(max_rate=self._edit_max_rate, time_period=self._group_time_period or 60)
        return self._edit_limiters[group_id]

    def _limiters(self, endpoint: str, chat_id):
        """(محدودکننده‌ی گروه، محدودکننده‌ی کلی) برای این درخواست؛ هر کدام ممکن است ``None`` باشد."""
        base = self._base_limiter if chat_id is not None else None
        is_group = (isinstance(chat_id, int) and chat_id < 0) or isinstance(chat_id, str)
        if not is_group or not self._group_max_rate:
            return None, base
        if endpoint in SEND_METHODS:
            return self._get_group_limiter(chat_id), base
        if endpoint in EDIT_METHODS and self._edit_max_rate:
            return self._get_edit_limiter(chat_id), base
        return None, base

    async def process_request(self, callback, args, kwargs, endpoint, data, rate_limit_args):
        max_retries = rate_limit_args or self._max_retries
        chat_id = data.get("chat_id")
        with contextlib.suppress(ValueError, TypeError):
            chat_id = int(chat_id)
        if data.get("allow_paid_broadcast", False):
            return await super().process_request(callback, args, kwargs, endpoint, data, rate_limit_args)
        group_limiter, base_limiter = self._limiters(endpoint, chat_id)
        for attempt in range(max_retries + 1):
            wait = self._paused_until.get(chat_id, 0) - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                async with group_limiter or contextlib.nullcontext(), base_limiter or contextlib.nullcontext():
                    return await callback(*args, **kwargs)
            except RetryAfter as exc:
                if attempt == max_retries:
                    logger.warning("telegram flood limit persisted", extra={"method": endpoint, "chat_id": chat_id})
                    raise
                pause = _seconds(exc.retry_after) + 0.1
                logger.info("telegram flood limit", extra={"method": endpoint, "chat_id": chat_id, "retry_after": pause})
                # فقط همین چت صبر می‌کند (نه کل ربات)
                self._paused_until[chat_id] = max(self._paused_until.get(chat_id, 0), time.monotonic() + pause)
                if len(self._paused_until) > 2048:
                    now = time.monotonic()
                    self._paused_until = {k: v for k, v in self._paused_until.items() if v > now}
        return None
