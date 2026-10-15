import uuid

from django.db import models


class ArcadeSession(models.Model):
    """یک تلاش در بازی آرکید. امتیاز فقط بعد از شبیه‌سازی دوباره در سرور معتبر است."""

    class Status(models.TextChoices):
        OPEN = "OPEN", "باز"
        VERIFIED = "VERIFIED", "تأییدشده"
        REJECTED = "REJECTED", "ردشده"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("core.TelegramUser", on_delete=models.CASCADE, related_name="arcade_sessions", verbose_name="کاربر")
    match = models.ForeignKey(
        "games.Match", null=True, blank=True, on_delete=models.CASCADE, related_name="arcade_sessions", verbose_name="مسابقه"
    )
    game_key = models.CharField(verbose_name="بازی", max_length=32)
    seed = models.BigIntegerField(verbose_name="seed")
    started_at = models.DateTimeField(verbose_name="شروع", auto_now_add=True)
    submitted_at = models.DateTimeField(verbose_name="زمان ثبت", null=True, blank=True)
    input_log = models.JSONField(verbose_name="لاگ ورودی", null=True, blank=True)
    claimed_score = models.IntegerField(verbose_name="امتیاز ادعایی", null=True, blank=True)
    verified_score = models.IntegerField(verbose_name="امتیاز تأییدشده", null=True, blank=True)
    level_reached = models.PositiveIntegerField(verbose_name="مرحله", default=0)
    duration_ms = models.PositiveIntegerField(verbose_name="مدت (میلی‌ثانیه)", default=0)
    status = models.CharField(verbose_name="وضعیت", max_length=10, choices=Status.choices, default=Status.OPEN)
    reject_reason = models.CharField(verbose_name="دلیل", max_length=64, blank=True, default="")
    flagged = models.BooleanField("مشکوک", default=False, db_index=True)

    class Meta:
        verbose_name = "جلسه‌ی آرکید"
        verbose_name_plural = "جلسه‌های آرکید"
        indexes = [models.Index(fields=["match", "user"]), models.Index(fields=["user", "game_key"])]

    def __str__(self) -> str:
        return f"{self.game_key}:{self.user_id}:{self.status}"


class ArcadeRecord(models.Model):
    """بهترین رکورد شخصی هر کاربر در هر بازی (تمرین و مسابقه)."""

    user = models.ForeignKey("core.TelegramUser", on_delete=models.CASCADE, related_name="arcade_records", verbose_name="کاربر")
    game_key = models.CharField(verbose_name="بازی", max_length=32)
    best_score = models.IntegerField(verbose_name="بهترین امتیاز", default=0)
    level_reached = models.PositiveIntegerField(verbose_name="مرحله", default=0)
    updated_at = models.DateTimeField(verbose_name="به‌روزرسانی", auto_now=True)

    class Meta:
        verbose_name = "رکورد آرکید"
        verbose_name_plural = "رکوردهای آرکید"
        constraints = [models.UniqueConstraint(fields=["user", "game_key"], name="unique_arcade_record")]


class ChessPractice(models.Model):
    """بازی شطرنج تمرینی یک کاربر با کامپیوتر در مینی‌اپ (بدون سکه)."""

    user = models.ForeignKey("core.TelegramUser", on_delete=models.CASCADE, related_name="chess_practice", verbose_name="کاربر")
    level = models.CharField(verbose_name="سطح", max_length=8, default="medium")
    state = models.JSONField(verbose_name="وضعیت", default=dict)
    finished = models.BooleanField(verbose_name="تمام‌شده", default=False)
    created_at = models.DateTimeField(verbose_name="شروع", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="آخرین حرکت", auto_now=True)

    class Meta:
        verbose_name = "شطرنج با کامپیوتر"
        verbose_name_plural = "شطرنج‌های با کامپیوتر"
        indexes = [models.Index(fields=["user", "finished"])]

    def __str__(self) -> str:
        return f"{self.user} ({self.level})"
