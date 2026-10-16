"""پل بین handlerهای async و ORM همگام جنگو.

پیش‌فرض ``sync_to_async`` (``thread_sensitive=True``) همه‌ی کوئری‌ها را در یک thread واحد صف
می‌کند؛ یعنی با وجود پردازش هم‌زمان چت‌ها، کوئری یک گروه پشت کوئری گروه‌های دیگر معطل می‌ماند.
این‌جا کوئری‌ها در یک thread pool با اندازه‌ی ``BOT_DB_THREADS`` اجرا می‌شوند (هر thread اتصال
دیتابیس خودش را دارد). درستی موجودی‌ها با تراکنش و ``select_for_update`` تضمین می‌شود، نه با
یک‌thread بودن. با ``BOT_DB_THREADS=0`` رفتار قبلی برمی‌گردد.
"""

import asyncio
import contextvars
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import partial, wraps

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import close_old_connections

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _call(fn, args, kwargs):
    # پروسه‌ی ربات چرخه‌ی request ندارد؛ اتصال‌های مرده/منقضی را خودمان می‌بندیم.
    close_old_connections()
    return fn(*args, **kwargs)


def _pool_size() -> int:
    # SQLite (فقط توسعه) با چند نویسنده‌ی هم‌زمان «database is locked» می‌دهد
    if "sqlite" in settings.DATABASES["default"]["ENGINE"]:
        return 0
    return getattr(settings, "BOT_DB_THREADS", 0)


def _get_executor() -> ThreadPoolExecutor | None:
    global _executor
    size = _pool_size()
    if size <= 1:
        return None
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(max_workers=size, thread_name_prefix="bot-db")
    return _executor


def db(fn):
    """تابع sync دیتابیسی را به coroutine تبدیل می‌کند: ``await db(func)(args)``"""

    @wraps(fn)
    async def wrapper(*args, **kwargs):
        executor = _get_executor()
        if executor is None:
            return await sync_to_async(_call)(fn, args, kwargs)
        ctx = contextvars.copy_context()
        return await asyncio.get_running_loop().run_in_executor(executor, partial(ctx.run, _call, fn, args, kwargs))

    return wrapper
