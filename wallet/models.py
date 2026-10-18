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
    TOPUP = "TOPUP", "شارژ کیف پول"
    SELL = "SELL", "فروش سکه"
    TRANSFER_OUT = "TRANSFER_OUT", "انتقال به کاربر"
    TRANSFER_IN = "TRANSFER_IN", "دریافت از کاربر"


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
        verbose_name="جایزه‌ی روزانه فعال", default=True, help_text="جایزه‌ی روزانه و سکه‌ی نجات (موجودی صفر)."
    )
    referral_every = models.PositiveIntegerField(
        verbose_name="تعداد دعوت برای هر جایزه",
        default=10,
        help_text="هر چند دوست دعوت‌شده یک جایزه می‌دهد.",
    )
    referral_reward = models.PositiveIntegerField(
        verbose_name="جایزه‌ی دعوت (سکه)", default=30, help_text="سکه‌ی هر جایزه‌ی دعوت (۳۰ سکه به ازای ۱۰ نفر). ۰ = خاموش."
    )
    coin_price_toman = models.PositiveIntegerField(
        verbose_name="قیمت هر سکه (تومان)", default=1000, help_text="قیمت پایه برای شارژ کیف پول (۱۰۰۰ تومان)"
    )
    topup_fee_percent = models.PositiveIntegerField(
        verbose_name="درصد کارمزد شارژ", default=10, help_text="کارمزد شارژ کیف پول (مثلاً ۱۰ برای ۱۰٪)"
    )
    card_number = models.CharField(
        verbose_name="شماره کارت واریز", max_length=32, blank=True, default="", help_text="شماره کارت مقصد جهت واریز وجه شارژ"
    )
    card_holder = models.CharField(
        verbose_name="نام صاحب کارت", max_length=128, blank=True, default="", help_text="نام دارنده کارت مقصد"
    )
    min_sell_coins = models.PositiveIntegerField(
        verbose_name="حداقل سکه برای فروش", default=100, help_text="حداقل تعداد سکه برای درخواست تسویه و فروش (۱۰۰ سکه)"
    )
    coin_sell_price_toman = models.PositiveIntegerField(
        verbose_name="قیمت فروش هر سکه (تومان)", default=1000, help_text="مبلغ پرداختی به کاربر به ازای هر سکه در فروش (۱۰۰۰ تومان)"
    )
    extra_admin_ids = models.JSONField(
        verbose_name="ادمین‌های اضافه",
        default=list,
        blank=True,
        help_text="لیست آیدی‌های عددی تلگرام ادمین‌های افزوده شده از پنل ربات",
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


class TopUpRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "در انتظار بررسی"
        APPROVED = "APPROVED", "تایید شده"
        REJECTED = "REJECTED", "رد شده"

    user = models.ForeignKey("core.TelegramUser", on_delete=models.CASCADE, related_name="topup_requests", verbose_name="کاربر")
    coins = models.PositiveIntegerField(verbose_name="تعداد سکه")
    amount_toman = models.PositiveIntegerField(verbose_name="مبلغ خام (تومان)")
    fee_toman = models.PositiveIntegerField(verbose_name="کارمزد (تومان)")
    total_toman = models.PositiveIntegerField(verbose_name="مبلغ کل پرداختی (تومان)")
    receipt_photo_id = models.CharField(verbose_name="شناسه عکس رسید تلگرام", max_length=255, blank=True)
    status = models.CharField(verbose_name="وضعیت", max_length=16, choices=Status.choices, default=Status.PENDING)
    admin_note = models.CharField(verbose_name="توضیح ادمین", max_length=255, blank=True)
    created_at = models.DateTimeField(verbose_name="تاریخ ایجاد", auto_now_add=True)
    reviewed_at = models.DateTimeField(verbose_name="تاریخ بررسی", null=True, blank=True)

    class Meta:
        verbose_name = "درخواست شارژ کیف پول"
        verbose_name_plural = "درخواست‌های شارژ کیف پول"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"TopUp #{self.pk} - {self.user} - {self.coins} coins ({self.status})"


class SellRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "در انتظار واریز"
        PAID = "PAID", "واریز شد"
        REJECTED = "REJECTED", "رد شده"

    user = models.ForeignKey("core.TelegramUser", on_delete=models.CASCADE, related_name="sell_requests", verbose_name="کاربر")
    coins = models.PositiveIntegerField(verbose_name="تعداد سکه")
    amount_toman = models.PositiveIntegerField(verbose_name="مبلغ واریزی (تومان)")
    card_number = models.CharField(verbose_name="شماره کارت", max_length=32)
    card_holder = models.CharField(verbose_name="نام دارنده کارت", max_length=128, blank=True)
    status = models.CharField(verbose_name="وضعیت", max_length=16, choices=Status.choices, default=Status.PENDING)
    admin_note = models.CharField(verbose_name="توضیح ادمین", max_length=255, blank=True)
    created_at = models.DateTimeField(verbose_name="تاریخ ایجاد", auto_now_add=True)
    reviewed_at = models.DateTimeField(verbose_name="تاریخ بررسی", null=True, blank=True)

    class Meta:
        verbose_name = "درخواست فروش سکه"
        verbose_name_plural = "درخواست‌های فروش سکه"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Sell #{self.pk} - {self.user} - {self.coins} coins ({self.status})"
