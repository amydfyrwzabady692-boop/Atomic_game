from django.db import models


class TxType(models.TextChoices):
    DAILY = "DAILY", "جایزه‌ی روزانه"
    REFERRAL = "REFERRAL", "دعوت دوست"
    ENTRY_FEE = "ENTRY_FEE", "ورودی بازی"
    PRIZE = "PRIZE", "جایزه‌ی بازی"
    REFUND = "REFUND", "برگشت ورودی"
    ADMIN_GRANT = "ADMIN_GRANT", "هدیه‌ی ادمین"
    SHOP = "SHOP", "خرید فروشگاه"
    ACHIEVEMENT = "ACHIEVEMENT", "دستاورد"
    SIGNUP_BONUS = "SIGNUP_BONUS", "هدیه‌ی ثبت‌نام"
    RESCUE = "RESCUE", "سکه‌ی نجات"


class LedgerImmutableError(Exception):
    pass


class CoinTransaction(models.Model):
    """دفتر کل سکه‌ی مجازی. ردیف‌ها فقط اضافه می‌شوند؛ ویرایش و حذف ممنوع است."""

    user = models.ForeignKey("core.TelegramUser", on_delete=models.PROTECT, related_name="transactions", verbose_name="کاربر")
    amount = models.BigIntegerField(verbose_name="مقدار")
    balance_after = models.BigIntegerField(verbose_name="موجودی بعد")
    type = models.CharField(verbose_name="نوع", max_length=16, choices=TxType.choices)
    ref_match = models.ForeignKey(
        "games.Match", null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions", verbose_name="مسابقه"
    )
    idempotency_key = models.CharField(verbose_name="کلید یکتا", max_length=128, unique=True)
    created_at = models.DateTimeField(verbose_name="تاریخ ایجاد", auto_now_add=True)

    class Meta:
        verbose_name = "تراکنش سکه"
        verbose_name_plural = "تراکنش‌های سکه"
        indexes = [models.Index(fields=["user", "-created_at"])]
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.user_id} {self.amount:+d} {self.type}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise LedgerImmutableError("تراکنش‌های ledger قابل ویرایش نیستند.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerImmutableError("تراکنش‌های ledger قابل حذف نیستند.")


class EconomySettings(models.Model):
    """تنظیمات اقتصاد سکه که از پنل ادمین عوض می‌شود. فقط یک ردیف (pk=1) دارد."""

    signup_bonus = models.PositiveIntegerField(
        verbose_name="هدیه‌ی ثبت‌نام", default=0, help_text="سکه‌ای که کاربر با اولین /start می‌گیرد. ۰ = خاموش."
    )
    daily_enabled = models.BooleanField(
        verbose_name="جایزه‌ی روزانه فعال", default=False, help_text="جایزه‌ی روزانه و سکه‌ی نجات (موجودی صفر)."
    )
    referral_every = models.PositiveIntegerField(
        verbose_name="تعداد دعوت برای هر جایزه",
        default=10,
        help_text="هر چند دوست دعوت‌شده (که اولین بازی سکه‌ای‌شان را انجام داده‌اند) یک جایزه می‌دهد.",
    )
    referral_reward = models.PositiveIntegerField(
        verbose_name="جایزه‌ی دعوت (سکه)", default=3, help_text="سکه‌ی هر جایزه‌ی دعوت. ۰ = خاموش."
    )
    updated_at = models.DateTimeField(verbose_name="آخرین تغییر", auto_now=True)

    class Meta:
        verbose_name = "تنظیمات اقتصاد سکه"
        verbose_name_plural = "تنظیمات اقتصاد سکه"

    def __str__(self) -> str:
        return "تنظیمات اقتصاد سکه"

    def save(self, *args, **kwargs):
        self.pk = 1
        self.referral_every = max(1, self.referral_every)
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "EconomySettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
