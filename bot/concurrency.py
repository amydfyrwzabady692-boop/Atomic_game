"""پردازش هم‌زمان به‌روزرسانی‌ها با حفظ ترتیب در هر چت.

پیش‌فرض python-telegram-bot این است که به‌روزرسانی‌ها یکی‌یکی پردازش شوند؛ یعنی اگر تلگرام برای یک
گروه چند ثانیه مکث بخواهد (محدودیت نرخ) یا یک عکس کند آپلود شود، همه‌ی گروه‌های دیگر هم معطل
می‌مانند. این‌جا چت‌های مختلف هم‌زمان جلو می‌روند، ولی پیام‌ها و کلیک‌های یک چت دقیقاً به همان
ترتیبی که رسیده‌اند پردازش می‌شوند؛ پس «اولین جواب درست» همچنان همان اولین پیام رسیده است.
"""

import asyncio

from telegram.ext import BaseUpdateProcessor


class PerChatUpdateProcessor(BaseUpdateProcessor):
    def __init__(self, max_concurrent_updates: int = 32):
        super().__init__(max(1, max_concurrent_updates))
        self._locks: dict[int, asyncio.Lock] = {}
        self._users: dict[int, int] = {}  # چند به‌روزرسانی منتظر یا در حال پردازش برای هر چت

    async def do_process_update(self, update, coroutine) -> None:
        chat = getattr(update, "effective_chat", None)
        key = chat.id if chat is not None else 0
        lock = self._locks.setdefault(key, asyncio.Lock())
        self._users[key] = self._users.get(key, 0) + 1
        try:
            try:
                await lock.acquire()  # قفل asyncio نوبت را به ترتیب درخواست می‌دهد
            except BaseException:
                coroutine.close()
                raise
            try:
                await coroutine
            finally:
                lock.release()
        finally:
            self._users[key] -= 1
            if not self._users[key]:
                del self._users[key]
                self._locks.pop(key, None)

    async def initialize(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None
