"""وب‌هوک ربات‌های دیگر: رویدادهای استارت، بلاک/آنبلاک و عضویت/خروج کانال همان لحظه برای هر کلید API که
آدرس وب‌هوک دارد فرستاده می‌شود.

بدنه JSON است و هدر ``X-Signature`` برابر HMAC-SHA256 همان بدنه با کلید API (hex) است تا گیرنده مطمئن شود
پیام از همین ربات آمده. ارسال پشت handler انجام می‌شود (ربات معطل نمی‌ماند)، تا دو بار دوباره تلاش می‌شود و
نتیجه‌ی آخرین ارسال هر کلید برای پنل مدیریت در Redis می‌ماند.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time

from django.conf import settings

from core.redis import get_redis

from .db import db

logger = logging.getLogger(__name__)

TIMEOUT = 6
RETRY_DELAYS = (2, 8)
TARGETS_TTL = 30.0
MAX_PARALLEL = 20

_targets: dict = {"rows": [], "at": float("-inf")}
_client = None
_slots: asyncio.Semaphore | None = None


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def body_of(event: str, bot_username: str, **fields) -> bytes:
    data = {"event": event, "bot": bot_username, "date": int(time.time()), **fields}
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()


@db
def _load_targets() -> list[tuple[int, str, str]]:
    from membership.models import PartnerKey

    return list(
        PartnerKey.objects.filter(is_active=True).exclude(webhook_url="").values_list("pk", "key", "webhook_url")
    )


async def targets() -> list[tuple[int, str, str]]:
    if time.monotonic() - _targets["at"] > TARGETS_TTL:
        try:
            _targets["rows"] = await _load_targets()
            _targets["at"] = time.monotonic()
        except Exception:
            logger.warning("failed to load partner webhooks", exc_info=True)
    return _targets["rows"]


def forget_targets() -> None:
    """پنل کلیدی را عوض کرد: بار بعد از دیتابیس خوانده می‌شود."""
    _targets["at"] = float("-inf")


def _http():
    global _client
    if _client is None:
        import httpx

        _client = httpx.AsyncClient(timeout=TIMEOUT, proxy=settings.PARTNER_HTTP_PROXY or None, follow_redirects=False)
    return _client


async def _remember(pk: int, event: str, status: str) -> None:
    try:
        await get_redis().set(f"hook:last:{pk}", json.dumps({"at": int(time.time()), "event": event, "status": status}))
    except Exception:
        pass


async def last_result(pk: int) -> dict | None:
    try:
        raw = await get_redis().get(f"hook:last:{pk}")
    except Exception:
        return None
    return json.loads(raw) if raw else None


async def deliver(pk: int, secret: str, url: str, event: str, body: bytes, retries: bool = True) -> str:
    """یک رویداد برای یک گیرنده؛ وضعیت نهایی را برمی‌گرداند («200» یا شرح خطا)."""
    global _slots
    if _slots is None:
        _slots = asyncio.Semaphore(MAX_PARALLEL)
    headers = {"Content-Type": "application/json", "X-Event": event, "X-Signature": sign(secret, body)}
    delays = RETRY_DELAYS if retries else ()
    status = "error"
    for attempt in range(len(delays) + 1):
        try:
            async with _slots:
                response = await _http().post(url, content=body, headers=headers)
            status = str(response.status_code)
            if response.status_code < 500:
                break  # ۲xx موفق؛ ۴xx یعنی گیرنده نمی‌خواهد و تکرار فایده ندارد
        except Exception as exc:
            status = type(exc).__name__
        if attempt < len(delays):
            await asyncio.sleep(delays[attempt])
    if not status.startswith("2"):
        logger.info("partner webhook failed", extra={"key": pk, "event": event, "status": status})
    await _remember(pk, event, status)
    return status


async def _emit(event: str, bot_username: str, fields: dict) -> None:
    rows = await targets()
    if not rows:
        return
    body = body_of(event, bot_username, **fields)
    await asyncio.gather(*(deliver(pk, secret, url, event, body) for pk, secret, url in rows))


def emit(application, event: str, **fields) -> None:
    """رویداد را بدون معطل کردن handler برای همه‌ی وب‌هوک‌ها می‌فرستد."""
    username = application.bot_data.get("username") or settings.BOT_USERNAME
    application.create_task(_emit(event, username, fields))
