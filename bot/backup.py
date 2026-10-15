"""پشتیبان‌گیری خودکار از دیتابیس و فرستادنش در پیوی مدیرها.

خروجی با ``dumpdata`` جنگو ساخته و gzip می‌شود (به ابزار pg_dump داخل کانتینر ربات نیازی نیست) و با
``python manage.py loaddata backup-....json.gz`` روی یک دیتابیس خالیِ migrate‌شده برمی‌گردد.
فایل اطلاعات کاربران را دارد؛ فقط برای شناسه‌های ``BACKUP_CHAT_IDS`` (پیش‌فرض: سوپرادمین‌ها) فرستاده می‌شود.
"""

import gzip
import logging
import os
import tempfile
import time

from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from core import texts

from .tg import tg_call

logger = logging.getLogger(__name__)

TELEGRAM_FILE_LIMIT = 49 * 1024 * 1024  # سقف فایل ارسالی ربات ۵۰ مگابایت است
EXCLUDED = ["contenttypes", "auth.permission", "sessions", "admin.logentry"]


def recipients() -> list[int]:
    return list(getattr(settings, "BACKUP_CHAT_IDS", None) or settings.SUPERADMIN_IDS)


def make_backup() -> tuple[str, str]:
    """فایل پشتیبان فشرده را در پوشه‌ی موقت می‌سازد. ``(مسیر، نام فایل)`` برمی‌گرداند."""
    stamp = timezone.localtime().strftime("%Y-%m-%d_%H-%M")
    name = f"backup-{stamp}.json.gz"
    handle, path = tempfile.mkstemp(suffix=".json.gz")
    os.close(handle)
    with gzip.open(path, "wt", encoding="utf-8") as output:
        call_command(
            "dumpdata",
            natural_foreign=True,
            natural_primary=True,
            exclude=EXCLUDED,
            stdout=output,
            verbosity=0,
        )
    return path, name


def _make_backup_in_thread() -> tuple[str, str]:
    """در thread جدا اجرا می‌شود تا ساختن پشتیبان بقیه‌ی کارهای دیتابیس ربات را معطل نکند."""
    from django.db import connection

    try:
        return make_backup()
    finally:
        connection.close()


async def send_backup(bot, chat_ids: list[int] | None = None) -> int:
    """پشتیبان می‌سازد و برای مدیرها می‌فرستد. تعداد ارسال‌های موفق را برمی‌گرداند."""
    import asyncio

    chat_ids = chat_ids if chat_ids is not None else recipients()
    if not chat_ids:
        return 0
    started = time.monotonic()
    path, name = await asyncio.to_thread(_make_backup_in_thread)
    try:
        size = os.path.getsize(path)
        caption = texts.BACKUP_CAPTION.format(
            date=texts.fa_digits(timezone.localtime().strftime("%Y/%m/%d %H:%M")),
            size=texts.fa_digits(f"{size / 1024:.0f}"),
        )
        sent = 0
        for chat_id in chat_ids:
            if size > TELEGRAM_FILE_LIMIT:
                await tg_call(bot.send_message, chat_id, texts.BACKUP_TOO_BIG, parse_mode="HTML")
                continue
            with open(path, "rb") as file:
                data = await asyncio.to_thread(file.read)
            if await tg_call(bot.send_document, chat_id, data, filename=name, caption=caption, parse_mode="HTML"):
                sent += 1
        logger.info("backup sent", extra={"bytes": size, "sent": sent, "seconds": round(time.monotonic() - started, 1)})
        return sent
    finally:
        os.remove(path)


async def backup_job(context) -> None:
    try:
        await send_backup(context.bot)
    except Exception:
        logger.exception("backup failed")
