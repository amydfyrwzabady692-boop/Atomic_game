"""فراخوانی امن API تلگرام و صف ویرایش پیام‌ها (برای جلوگیری از flood)."""

import asyncio
import logging
import time

from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TimedOut

logger = logging.getLogger(__name__)


def _seconds(value) -> float:
    return value.total_seconds() if hasattr(value, "total_seconds") else float(value)


async def tg_call(func, *args, retries: int = 2, **kwargs):
    """متد bot را صدا می‌زند و خطاهای رایج را مدیریت می‌کند. در شکست ``None`` برمی‌گرداند.

    - ``RetryAfter``: صبر و تلاش دوباره
    - ``BadRequest: message is not modified``: نادیده گرفته می‌شود
    - خطای شبکه: یک بار تلاش دوباره
    """
    for attempt in range(retries + 1):
        try:
            return await func(*args, **kwargs)
        except RetryAfter as exc:
            delay = _seconds(exc.retry_after) + 0.5
            if attempt >= retries or delay > 30:
                logger.warning("telegram flood limit", extra={"method": func.__name__, "retry_after": delay})
                return None
            await asyncio.sleep(delay)
        except BadRequest as exc:
            if "not modified" not in str(exc).lower():
                logger.warning("telegram bad request", extra={"method": func.__name__, "error": str(exc)})
            return None
        except Forbidden as exc:
            logger.info("telegram forbidden", extra={"method": func.__name__, "error": str(exc)})
            return None
        except (TimedOut, NetworkError) as exc:
            if attempt >= retries:
                logger.warning("telegram network error", extra={"method": func.__name__, "error": str(exc)})
                return None
            await asyncio.sleep(1)
    return None


class EditQueue:
    """ویرایش‌های پشت‌سرهم یک پیام را ادغام می‌کند تا از حد نرخ تلگرام رد نشویم.

    برای هر پیام حداکثر هر ``interval`` ثانیه یک ویرایش فرستاده می‌شود و همیشه
    آخرین محتوا اعمال می‌شود.
    """

    def __init__(self, bot, interval: float = 3.0):
        self.bot = bot
        self.interval = interval
        self._last: dict[tuple[int, int], float] = {}
        self._pending: dict[tuple[int, int], dict] = {}
        self._tasks: dict[tuple[int, int], asyncio.Task] = {}

    def edit(self, chat_id: int, message_id: int, text: str, reply_markup=None, *, urgent: bool = False) -> None:
        key = (chat_id, message_id)
        self._pending[key] = {"text": text, "reply_markup": reply_markup}
        if key in self._tasks and not self._tasks[key].done():
            return
        wait = 0.0 if urgent else max(0.0, self._last.get(key, 0.0) + self.interval - time.monotonic())
        self._tasks[key] = asyncio.create_task(self._flush(key, wait))

    async def _flush(self, key, wait: float) -> None:
        try:
            if wait:
                await asyncio.sleep(wait)
            payload = self._pending.pop(key, None)
            if payload is None:
                return
            self._last[key] = time.monotonic()
            await tg_call(
                self.bot.edit_message_text,
                chat_id=key[0],
                message_id=key[1],
                parse_mode="HTML",
                disable_web_page_preview=True,
                **payload,
            )
        finally:
            self._tasks.pop(key, None)
            if key in self._pending:  # در حین ارسال، محتوای تازه‌تری رسیده
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:  # حلقه‌ی رویداد در حال بسته شدن است
                    self._pending.pop(key, None)
                else:
                    self._tasks[key] = loop.create_task(self._flush(key, self.interval))

    async def flush_now(self, chat_id: int, message_id: int) -> None:
        """منتظر می‌ماند تا ویرایش‌های معوق این پیام تمام شود."""
        key = (chat_id, message_id)
        task = self._tasks.get(key)
        if task and not task.done():
            task.cancel()
        self._tasks.pop(key, None)
        payload = self._pending.pop(key, None)
        if payload is not None:
            self._last[key] = time.monotonic()
            await tg_call(
                self.bot.edit_message_text,
                chat_id=chat_id,
                message_id=message_id,
                parse_mode="HTML",
                disable_web_page_preview=True,
                **payload,
            )

    async def close(self) -> None:
        """هنگام خاموش شدن ربات: ویرایش‌های معوق دور ریخته و taskهای در انتظار لغو می‌شوند."""
        self._pending.clear()
        tasks = [task for task in self._tasks.values() if not task.done()]
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def forget(self, chat_id: int, message_id: int) -> None:
        key = (chat_id, message_id)
        self._pending.pop(key, None)
        self._last.pop(key, None)
        task = self._tasks.pop(key, None)
        if task and not task.done():
            task.cancel()
