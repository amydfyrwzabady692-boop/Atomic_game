"""پردازش هم‌زمان به‌روزرسانی‌ها با حفظ ترتیب در هر چت.

پیش‌فرض python-telegram-bot این است که به‌روزرسانی‌ها یکی‌یکی پردازش شوند؛ یعنی اگر تلگرام برای یک
گروه چند ثانیه مکث بخواهد (محدودیت نرخ) یا یک عکس کند آپلود شود، همه‌ی گروه‌های دیگر هم معطل
می‌مانند. این‌جا چت‌های مختلف هم‌زمان جلو می‌روند، ولی پیام‌های یک چت دقیقاً به همان ترتیبی که
رسیده‌اند پردازش می‌شوند؛ پس «اولین جواب درست» همچنان همان اولین پیام رسیده است.

- کلیک دکمه‌ها در گروه به ترتیبِ *همان پیام* پردازش می‌شوند (نه کل گروه): وقتی ده بازی هم‌زمان در یک گروه
  جریان دارد، کلیک‌های لابی یا صفحه‌ی یک بازی پشت ارسال پیام بازی دیگری (که شاید زیر سقف ۲۰ پیام در دقیقه‌ی
  تلگرام منتظر مانده) صف نمی‌کشند. وضعیت هر بازی جدا با قفل خودش (``ActiveMatch.lock``) محافظت می‌شود و
  پول با قفل ردیف دیتابیس؛ در پیوی همه‌چیز مثل قبل به ترتیب چت است.
- نوبتِ چت قبل از گرفتن سهمیه‌ی پردازش هم‌زمان گرفته می‌شود؛ پس یک گروه شلوغ که ده‌ها پیام پشت هم دارد
  حداکثر یک جای پردازش را اشغال می‌کند و بقیه‌ی چت‌ها و پیوی‌ها هرگز به‌خاطرش معطل نمی‌مانند.
"""

import asyncio

from telegram.constants import ChatType
from telegram.ext import BaseUpdateProcessor

GROUP_TYPES = (ChatType.GROUP, ChatType.SUPERGROUP)


def update_key(update) -> object:
    """کلید ترتیب: شناسه‌ی چت، یا (چت، پیام) برای کلیک دکمه در گروه."""
    chat = getattr(update, "effective_chat", None)
    if chat is None:
        return 0
    query = getattr(update, "callback_query", None)
    message = getattr(query, "message", None) if query is not None else None
    if message is not None and getattr(chat, "type", None) in GROUP_TYPES:
        return (chat.id, message.message_id)
    return chat.id


class PerChatUpdateProcessor(BaseUpdateProcessor):
    def __init__(self, max_concurrent_updates: int = 32):
        super().__init__(max(1, max_concurrent_updates))
        self._locks: dict[object, asyncio.Lock] = {}
        self._users: dict[object, int] = {}  # چند به‌روزرسانی منتظر یا در حال پردازش برای هر کلید

    async def process_update(self, update, coroutine) -> None:
        key = update_key(update)
        lock = self._locks.setdefault(key, asyncio.Lock())
        self._users[key] = self._users.get(key, 0) + 1
        try:
            try:
                await lock.acquire()  # قفل asyncio نوبت را به ترتیب درخواست می‌دهد
            except BaseException:
                coroutine.close()
                raise
            try:
                # سهمیه‌ی هم‌زمانی (semaphore کتابخانه) فقط وقتی نوبت این چت رسید گرفته می‌شود
                await super().process_update(update, coroutine)
            except BaseException:
                coroutine.close()  # اگر وسط انتظار سهمیه لغو شد، هشدار «never awaited» نمی‌دهد
                raise
            finally:
                lock.release()
        finally:
            self._users[key] -= 1
            if not self._users[key]:
                del self._users[key]
                self._locks.pop(key, None)

    async def do_process_update(self, update, coroutine) -> None:
        await coroutine

    async def initialize(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None
