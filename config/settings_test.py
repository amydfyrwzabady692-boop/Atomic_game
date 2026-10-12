"""تنظیمات تست.

اگر `DATABASE_URL` تنظیم شده باشد همان استفاده می‌شود (مثلاً در CI با سرویس Postgres).
وگرنه اگر بسته‌ی `pgserver` نصب باشد یک PostgreSQL موقت بالا می‌آید تا تست‌های
همزمانی (`select_for_update`) واقعی باشند؛ در غیر این صورت SQLite استفاده می‌شود و
تست‌های مخصوص Postgres رد (skip) می‌شوند.
"""

import atexit
import os
import tempfile

from .settings import *  # noqa: F403
from .settings import env

if not os.environ.get("DATABASE_URL"):
    try:
        import importlib.resources
        import pathlib
        import shutil

        import pgserver

        # بیلد ویندوزی pgserver پوشه‌ی timezone ندارد؛ از بسته‌ی tzdata پرش می‌کنیم (همان قالب TZif).
        _tz_dir = pathlib.Path(pgserver.__file__).parent / "pginstall" / "share" / "postgresql" / "timezone"
        if _tz_dir.parent.is_dir() and not _tz_dir.exists():
            shutil.copytree(
                str(importlib.resources.files("tzdata") / "zoneinfo"),
                _tz_dir,
                ignore=shutil.ignore_patterns("*.py", "__pycache__"),
            )

        _pg_dir = tempfile.mkdtemp(prefix="gamebot-pg-")
        _pg = pgserver.get_server(_pg_dir)
        atexit.register(_pg.cleanup)
        DATABASES = {"default": env.db_url_config(_pg.get_uri())}
    except Exception:  # pragma: no cover - pgserver اختیاری است
        DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

REDIS_URL = ""
DEBUG = False
ARCADE_DEV_AUTH = False
BOT_TOKEN = "123456:TEST-TOKEN"
BOT_USERNAME = "test_bot"
SUPERADMIN_IDS = [999]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
LOGGING = {"version": 1, "disable_existing_loggers": False}
MINIAPP_BASE_URL = "https://arcade.test"
