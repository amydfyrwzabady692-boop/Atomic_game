from html import escape

from django.db import models
from django.db.models import Q


class TelegramUser(models.Model):
    tg_id = models.BigIntegerField("شناسه تلگرام", unique=True)
    username = models.CharField(verbose_name="نام کاربری", max_length=64, blank=True, default="")
    first_name = models.CharField(verbose_name="نام", max_length=128, blank=True, default="")
    coins = models.BigIntegerField("سکه", default=0)
    xp = models.PositiveIntegerField(verbose_name="XP", default=0)
    level = models.PositiveIntegerField(verbose_name="سطح", default=1)
    daily_streak = models.PositiveIntegerField(verbose_name="روزهای پیاپی", default=0)
    last_daily_at = models.DateTimeField(verbose_name="آخرین جایزه‌ی روزانه", null=True, blank=True)
    last_rescue_at = models.DateTimeField(verbose_name="آخرین سکه‌ی نجات", null=True, blank=True)
    referred_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="referrals", verbose_name="دعوت‌کننده"
    )
    referral_rewarded = models.BooleanField(verbose_name="جایزه‌ی دعوت داده شد", default=False)
    started_bot = models.BooleanField("استارت در پیوی", default=False)
    is_banned = models.BooleanField(verbose_name="مسدود", default=False)
    games_played = models.PositiveIntegerField(verbose_name="تعداد بازی", default=0)
    wins = models.PositiveIntegerField(verbose_name="برد", default=0)
    created_at = models.DateTimeField(verbose_name="تاریخ ایجاد", auto_now_add=True)

    class Meta:
        verbose_name = "کاربر"
        verbose_name_plural = "کاربران"
        constraints = [
            models.CheckConstraint(condition=Q(coins__gte=0), name="user_coins_non_negative"),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.tg_id})"

    @property
    def display_name(self) -> str:
        return self.first_name or self.username or str(self.tg_id)

    @property
    def mention_html(self) -> str:
        return f'<a href="tg://user?id={self.tg_id}">{escape(self.display_name)}</a>'


class TelegramGroup(models.Model):
    chat_id = models.BigIntegerField(verbose_name="شناسه‌ی گروه", unique=True)
    title = models.CharField(verbose_name="عنوان", max_length=255, blank=True, default="")
    is_active = models.BooleanField(verbose_name="فعال", default=True)
    # لیست کلید بازی‌های فعال؛ خالی یعنی همه فعال‌اند.
    enabled_games = models.JSONField(verbose_name="بازی‌های فعال", default=list, blank=True)
    min_entry = models.PositiveIntegerField(verbose_name="حداقل ورودی", default=0)
    max_entry = models.PositiveIntegerField(verbose_name="حداکثر ورودی", default=1000)
    default_join_seconds = models.PositiveIntegerField(verbose_name="زمان عضوگیری پیش‌فرض", default=60)
    allow_user_created_games = models.BooleanField(verbose_name="ساخت بازی توسط همه", default=True)
    prize_note = models.CharField(
        verbose_name="جایزه‌ی ویژه",
        max_length=120,
        blank=True,
        default="",
        help_text="جایزه‌ای که برگزارکننده بیرون از ربات به نفر اول می‌دهد؛ در لابی و نتیجه نشان داده می‌شود.",
    )
    created_at = models.DateTimeField(verbose_name="تاریخ ایجاد", auto_now_add=True)

    class Meta:
        verbose_name = "گروه"
        verbose_name_plural = "گروه‌ها"

    def __str__(self) -> str:
        return self.title or str(self.chat_id)

    def game_enabled(self, key: str) -> bool:
        return not self.enabled_games or key in self.enabled_games

    def fee_allowed(self, fee: int) -> bool:
        return self.min_entry <= fee <= self.max_entry
