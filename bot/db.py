"""پل بین handlerهای async و ORM همگام جنگو."""

from functools import wraps

from asgiref.sync import sync_to_async
from django.db import close_old_connections


def _call(fn, args, kwargs):
    # پروسه‌ی ربات چرخه‌ی request ندارد؛ اتصال‌های مرده/منقضی را خودمان می‌بندیم.
    close_old_connections()
    return fn(*args, **kwargs)


def db(fn):
    """تابع sync دیتابیسی را به coroutine تبدیل می‌کند: ``await db(func)(args)``"""

    @wraps(fn)
    async def wrapper(*args, **kwargs):
        return await sync_to_async(_call)(fn, args, kwargs)

    return wrapper
