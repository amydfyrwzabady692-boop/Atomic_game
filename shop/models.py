from django.db import models


class ShopItem(models.Model):
    """آیتم‌های فروشگاه فقط ظاهری‌اند و با سکه‌ی مجازی خریده می‌شوند (غیرقابل برگشت)."""

    class Kind(models.TextChoices):
        TITLE = "title", "عنوان"
        EMOJI = "emoji", "ایموجی اختصاصی"
        FRAME = "frame", "قاب پروفایل"

    kind = models.CharField(verbose_name="نوع", max_length=10, choices=Kind.choices)
    name = models.CharField(verbose_name="نام", max_length=64)
    value = models.CharField(verbose_name="مقدار نمایشی", max_length=64, help_text="متنی که نمایش داده می‌شود (عنوان، ایموجی یا قاب)")
    price = models.PositiveIntegerField(verbose_name="قیمت")
    stars_price = models.PositiveIntegerField(
        verbose_name="قیمت به استار تلگرام",
        null=True,
        blank=True,
        help_text="خالی = فقط با سکه‌ی مجازی. خرید با استار فقط آیتم ظاهری می‌دهد و به سکه تبدیل نمی‌شود.",
    )
    is_active = models.BooleanField(verbose_name="فعال", default=True)
    sort_order = models.PositiveSmallIntegerField(verbose_name="ترتیب", default=0)

    class Meta:
        verbose_name = "آیتم فروشگاه"
        verbose_name_plural = "آیتم‌های فروشگاه"
        ordering = ["kind", "sort_order", "price"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.name}"


class UserItem(models.Model):
    user = models.ForeignKey("core.TelegramUser", on_delete=models.CASCADE, related_name="items", verbose_name="کاربر")
    item = models.ForeignKey(ShopItem, on_delete=models.PROTECT, related_name="owners", verbose_name="آیتم")
    equipped = models.BooleanField(verbose_name="فعال", default=False)
    created_at = models.DateTimeField(verbose_name="تاریخ ایجاد", auto_now_add=True)

    class Meta:
        verbose_name = "آیتم کاربر"
        verbose_name_plural = "آیتم‌های کاربران"
        constraints = [models.UniqueConstraint(fields=["user", "item"], name="unique_user_item")]


class StarsPurchase(models.Model):
    """رسید خرید آیتم ظاهری با استار تلگرام (برای پیگیری و بازپرداخت از طریق خود تلگرام)."""

    user = models.ForeignKey("core.TelegramUser", on_delete=models.PROTECT, related_name="stars_purchases", verbose_name="کاربر")
    item = models.ForeignKey(ShopItem, on_delete=models.PROTECT, related_name="stars_purchases", verbose_name="آیتم")
    stars = models.PositiveIntegerField(verbose_name="استار")
    charge_id = models.CharField(verbose_name="شناسه‌ی پرداخت تلگرام", max_length=255, unique=True)
    created_at = models.DateTimeField(verbose_name="تاریخ", auto_now_add=True)

    class Meta:
        verbose_name = "خرید با استار"
        verbose_name_plural = "خریدهای استار"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user} — {self.item} ({self.stars}⭐)"
