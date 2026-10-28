"""محدودیت نرخ تلگرام: سهمیه‌ی جدا برای ارسال و ویرایش در گروه و مکث فقط برای همان چت."""

import asyncio
import time

from telegram.error import RetryAfter

from bot.ratelimiter import GroupGameRateLimiter


async def _ok(*args, **kwargs):
    return True


async def test_edits_and_admin_checks_do_not_use_the_group_message_budget():
    limiter = GroupGameRateLimiter(group_max_rate=1, group_time_period=60, group_edit_max_rate=100)
    await limiter.process_request(_ok, (), {}, "sendMessage", {"chat_id": -100}, None)
    assert not limiter._get_group_limiter(-100).has_capacity()  # سهمیه‌ی پیام این گروه پر شد
    # ویرایش لابی، بررسی ادمین و ارسال در گروه دیگر منتظر نمی‌مانند
    for _ in range(5):
        await asyncio.wait_for(limiter.process_request(_ok, (), {}, "editMessageText", {"chat_id": -100}, None), 1)
    await asyncio.wait_for(limiter.process_request(_ok, (), {}, "getChatMember", {"chat_id": -100}, None), 1)
    await asyncio.wait_for(limiter.process_request(_ok, (), {}, "sendMessage", {"chat_id": -200}, None), 1)
    await asyncio.wait_for(limiter.process_request(_ok, (), {}, "sendMessage", {"chat_id": 12345}, None), 1)


async def test_flood_wait_pauses_only_that_chat():
    limiter = GroupGameRateLimiter(max_retries=1)
    attempts = []

    async def flood(*args, **kwargs):
        attempts.append(time.monotonic())
        if len(attempts) == 1:
            raise RetryAfter(1)
        return "sent"

    async def other(*args, **kwargs):
        return "fast"

    slow = asyncio.create_task(limiter.process_request(flood, (), {}, "sendMessage", {"chat_id": -1}, None))
    await asyncio.sleep(0.05)
    started = time.monotonic()
    assert await limiter.process_request(other, (), {}, "sendMessage", {"chat_id": -2}, None) == "fast"
    assert time.monotonic() - started < 0.5  # گروه دیگر معطل مکث گروه اول نشد
    assert await slow == "sent" and attempts[1] - attempts[0] >= 1
