"""اتصال Redis (وضعیت زنده، قفل‌ها، rate limit).

اگر ``REDIS_URL`` خالی باشد از fakeredis درون‌حافظه‌ای استفاده می‌شود که فقط برای
توسعه و تست مناسب است (بین پروسه‌ها مشترک نیست).
"""

import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

_async_client = None
_sync_client = None
_fake_server = None


def _fake(async_: bool):
    global _fake_server
    try:
        import fakeredis
    except ImportError as exc:  # pragma: no cover
        raise ImproperlyConfigured("REDIS_URL تنظیم نشده و fakeredis هم نصب نیست.") from exc
    if _fake_server is None:
        _fake_server = fakeredis.FakeServer()
        logger.warning("REDIS_URL is empty; using in-memory fakeredis (development only)")
    cls = fakeredis.FakeAsyncRedis if async_ else fakeredis.FakeRedis
    return cls(server=_fake_server, decode_responses=True)


def get_redis():
    """کلاینت async برای پروسه‌ی ربات."""
    global _async_client
    if _async_client is None:
        if settings.REDIS_URL:
            import redis.asyncio as aioredis

            _async_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        else:
            _async_client = _fake(async_=True)
    return _async_client


def get_sync_redis():
    """کلاینت sync برای viewهای جنگو."""
    global _sync_client
    if _sync_client is None:
        if settings.REDIS_URL:
            import redis

            _sync_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        else:
            _sync_client = _fake(async_=False)
    return _sync_client


def reset_clients() -> None:
    """فقط برای تست."""
    global _async_client, _sync_client, _fake_server
    _async_client = _sync_client = _fake_server = None
