"""دسترسی‌های مدیران ربات.

مالک (``OWNER_TG_ID``) و ``SUPERADMIN_IDS`` همه‌ی دسترسی‌ها را دارند. بقیه‌ی مدیرها از پنل /admin با یک
نقش آماده یا دسترسی‌های دلخواه اضافه می‌شوند (مدل ``core.BotAdmin``) و هر بخش پنل، هر دستور مدیریتی و
هر هشدار (رسید شارژ، درخواست فروش، تیکت پشتیبانی) فقط به کسی می‌رسد که دسترسی همان بخش را دارد.
"""

PERMISSIONS = {
    "payments": "💳 رسیدهای شارژ و درخواست‌های فروش",
    "coins": "🪙 دادن یا کم کردن سکه",
    "users": "👤 کاربران و مسدود کردن",
    "support": "💬 پشتیبانی و پیام به کاربر",
    "games": "🎮 بازی‌ها و مسابقه‌های در جریان",
    "broadcast": "📢 پیام همگانی",
    "settings": "⚙️ تنظیمات اقتصاد سکه",
    "stats": "📊 آمار و حسابرسی",
    "admins": "👮 مدیران و پشتیبان دیتابیس",
}
ALL = frozenset(PERMISSIONS)

# نقش‌های آماده برای افزودن سریع مدیر؛ بعداً هر دسترسی جدا هم روشن/خاموش می‌شود
PRESETS = {
    "full": ("مدیر کامل", tuple(p for p in PERMISSIONS if p != "admins")),
    "finance": ("مالی", ("payments", "coins", "stats")),
    "support": ("پشتیبانی", ("support", "users", "payments")),
    "games": ("ناظر بازی‌ها", ("games", "users", "stats")),
    "viewer": ("فقط آمار", ("stats",)),
}


def clean(values) -> list[str]:
    """فقط کلیدهای معتبر، بدون تکرار و به ترتیب تعریف."""
    wanted = {str(v) for v in values or []}
    return [p for p in PERMISSIONS if p in wanted]


def role_name(permissions) -> str:
    """نام نقش برای نمایش: اگر با یکی از نقش‌های آماده یکی باشد همان نام، وگرنه «سفارشی»."""
    current = set(clean(permissions))
    if current == set(ALL):
        return "مدیر کل"
    for name, perms in PRESETS.values():
        if current == set(perms):
            return name
    return "سفارشی" if current else "بدون دسترسی"
