"""تنظیمات پروژه. همه‌ی مقادیر حساس از `.env` خوانده می‌شوند."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "wallet",
    "games",
    "leaderboard",
    "shop",
    "arcade",
    "bot",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {"default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "fa"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ---------------------------------------------------------------- تلگرام
BOT_TOKEN = env("BOT_TOKEN", default="")
BOT_USERNAME = env("BOT_USERNAME", default="")  # بدون @؛ اگر خالی باشد از getMe خوانده می‌شود
SUPERADMIN_IDS = [int(x) for x in env.list("SUPERADMIN_IDS", default=[])]
WEBHOOK_URL = env("WEBHOOK_URL", default="")  # خالی = polling
WEBHOOK_LISTEN = env("WEBHOOK_LISTEN", default="0.0.0.0")
WEBHOOK_PORT = env.int("WEBHOOK_PORT", default=8443)
WEBHOOK_SECRET = env("WEBHOOK_SECRET", default="")
REDIS_URL = env("REDIS_URL", default="")  # خالی = fakeredis درون‌حافظه‌ای (فقط توسعه/تست)
# نام و نماد واحد امتیاز مجازی در متن‌ها (مثلاً «اعتبار»). فقط ظاهر عوض می‌شود؛ ارزش پولی ندارد.
COIN_NAME = env("COIN_NAME", default="سکه")
COIN_EMOJI = env("COIN_EMOJI", default="🪙")
# دکمه‌های رنگی اینلاین (Bot API 9.4)؛ اگر به هر دلیلی مشکل‌ساز شد خاموشش کنید
BUTTON_STYLES = env.bool("BUTTON_STYLES", default=True)
# چند به‌روزرسانی هم‌زمان پردازش شود (ترتیب پیام‌های هر چت همیشه حفظ می‌شود)
BOT_CONCURRENT_UPDATES = env.int("BOT_CONCURRENT_UPDATES", default=32)

# ---------------------------------------------------------------- Mini App
MINIAPP_SHORT_NAME = env("MINIAPP_SHORT_NAME", default="arcade")
MINIAPP_BASE_URL = env("MINIAPP_BASE_URL", default="")  # مثل https://example.com
ARCADE_INITDATA_MAX_AGE = env.int("ARCADE_INITDATA_MAX_AGE", default=24 * 3600)
ARCADE_DEFAULT_ATTEMPTS = 3
ARCADE_SESSION_GRACE_MS = 15_000  # اختلاف مجاز زمان کلاینت و سرور
ARCADE_MIN_TAP_GAP_MS = 50
# فقط برای توسعه‌ی محلی: اجازه می‌دهد صفحه‌ی بازی بدون تلگرام در مرورگر باز شود (نیاز به DEBUG=True)
ARCADE_DEV_AUTH = env.bool("ARCADE_DEV_AUTH", default=False)

# ---------------------------------------------------------------- اقتصاد سکه (تماماً مجازی)
SIGNUP_BONUS = 1000
DAILY_BASE = 200
DAILY_STEP = 50
DAILY_MAX = 700
RESCUE_AMOUNT = 100
REFERRAL_REWARD = 300
REFERRAL_MIN_ACCOUNT_AGE_HOURS = 24
ENTRY_FEE_CHOICES = [0, 50, 100, 250, 500, 1000]
PRIZE_SPLITS = {
    "100": [100],
    "70-30": [70, 30],
    "60-30-10": [60, 30, 10],
    "50-30-20": [50, 30, 20],
}
JOIN_SECONDS_CHOICES = [30, 60, 120]
PLAY_WINDOW_CHOICES = [3, 5, 10]  # دقیقه، برای بازی‌های آرکید

XP_PARTICIPATION = 10
XP_BY_RANK = {1: 30, 2: 15, 3: 10}

# ---------------------------------------------------------------- لاگ
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "core.logging.JsonFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "httpx": {"level": "WARNING"},
        "apscheduler": {"level": "WARNING"},
    },
}
