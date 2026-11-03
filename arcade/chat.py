"""گفت‌وگوی کوتاه بین بازیکن‌ها: حریف تصادفی (موقع توافق روی سکه و حین بازی) و میز بازی‌های زنده (پوکر و …).

پیام‌ها در Redis می‌مانند (۴۰ پیام آخر هر «اتاق»، سه ساعت)، پس هیچ جدول تازه‌ای لازم نیست. فقط بازیکن‌های
همان دوئل یا همان مسابقه می‌نویسند؛ پیام کوتاه است، لینک و @یوزرنیم ندارد (جلوی تبلیغ و کلاه‌برداری) و
هر نفر حداکثر یک پیام در هر ثانیه و نیم و ۱۵ پیام در دقیقه می‌فرستد. متن در کلاینت با textContent نشان داده
می‌شود، پس HTML اجرا نمی‌شود.
"""

import json
import re
import time

from core.redis import get_sync_redis

MAX_LEN = 120
KEEP = 40
TTL = 3 * 3600
QUICK = ("👋 سلام", "🍀 موفق باشی", "👍 قبول", "🤝 بازی خوبی بود", "😂", "🔥", "⏳ یک لحظه", "😎")
LINK = re.compile(r"(https?://|www\.|t\.me/|telegram\.me/|@[A-Za-z0-9_]{4,})", re.IGNORECASE)
CONTROL = re.compile(r"[\u0000-\u001f\u007f​‪-‮⁦-⁩]")


class ChatError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def duel_room(duel_id: int) -> str:
    return f"duel:{duel_id}"


def match_room(match) -> str:
    """دوئلِ روی صفحه‌ی بازی همان اتاق گفت‌وگوی مرحله‌ی توافق را ادامه می‌دهد."""
    duel_id = (match.options or {}).get("duel")
    return duel_room(duel_id) if duel_id else f"match:{match.pk}"


def clean(text) -> str:
    if not isinstance(text, str):
        raise ChatError("chat_empty")
    text = CONTROL.sub("", text)
    text = " ".join(text.split())[:MAX_LEN]
    if not text:
        raise ChatError("chat_empty")
    if LINK.search(text):
        raise ChatError("chat_no_links")
    return text


def _allowed(user_id: int) -> bool:
    redis = get_sync_redis()
    if not redis.set(f"chat:gap:{user_id}", "1", px=1200, nx=True):
        return False
    key = f"chat:min:{user_id}"
    count = redis.incr(key)
    if count == 1:
        redis.expire(key, 60)
    return count <= 15


def post(room: str, user, text) -> dict:
    """پیام را به اتاق اضافه می‌کند و همان را برمی‌گرداند؛ در خطا ``ChatError``."""
    text = clean(text)
    if not _allowed(user.pk):
        raise ChatError("chat_too_fast")
    redis = get_sync_redis()
    message = {
        "id": int(redis.incr(f"chat:seq:{room}")),
        "uid": user.pk,
        "name": (user.display_name or "")[:24],
        "text": text,
        "at": int(time.time()),
    }
    key = f"chat:log:{room}"
    pipe = redis.pipeline()
    pipe.rpush(key, json.dumps(message, ensure_ascii=False))
    pipe.ltrim(key, -KEEP, -1)
    pipe.expire(key, TTL)
    pipe.expire(f"chat:seq:{room}", TTL)
    pipe.execute()
    return message


def recent(room: str, viewer_id: int | None = None, after: int = 0) -> list[dict]:
    """پیام‌های اتاق بعد از شناسه‌ی ``after``؛ ``mine`` یعنی پیام خود بیننده است."""
    try:
        rows = get_sync_redis().lrange(f"chat:log:{room}", 0, -1)
    except Exception:
        return []
    messages = []
    for raw in rows:
        try:
            message = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if message.get("id", 0) > after:
            message["mine"] = viewer_id is not None and message.get("uid") == viewer_id
            message.pop("uid", None)
            messages.append(message)
    return messages
