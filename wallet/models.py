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
