import secrets

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from . import config


def _new_token() -> str:
    return secrets.token_urlsafe(9)


def _new_seed() -> int:
    return secrets.randbelow(2**31 - 1) + 1


class MatchStatus(models.TextChoices):
    LOBBY = "LOBBY", "عضوگیری"
    RUNNING = "RUNNING", "در حال اجرا"
    FINISHED = "FINISHED", "تمام‌شده"
    CANCELLED = "CANCELLED", "لغوشده"


ACTIVE_STATUSES = [MatchStatus.LOBBY, MatchStatus.RUNNING]


class Match(models.Model):
    group = models.ForeignKey("core.TelegramGroup", on_delete=models.CASCADE, related_name="matches", verbose_name="گروه")
    game_type = models.CharField(verbose_name="بازی", max_length=32)
    creator = models.ForeignKey("core.TelegramUser", on_delete=models.PROTECT, related_name="created_matches", verbose_name="سازنده")
    entry_fee = models.PositiveIntegerField(verbose_name="ورودی", default=0)
    prize_split = models.JSONField(verbose_name="تقسیم جایزه", default=list)
    status = models.CharField(verbose_name="وضعیت", max_length=10, choices=MatchStatus.choices, default=MatchStatus.LOBBY)
    join_deadline = models.DateTimeField(verbose_name="مهلت عضوگیری")
    min_players = models.PositiveSmallIntegerField(verbose_name="حداقل بازیکن", default=2)
    max_players = models.PositiveSmallIntegerField(verbose_name="حداکثر بازیکن", default=20)
    pot = models.BigIntegerField(verbose_name="جایزه‌ی کل", default=0)
    lobby_message_id = models.BigIntegerField(verbose_name="شناسه‌ی پیام لابی", null=True, blank=True)
    # تنظیمات انتخاب‌شده موقع ساخت (دسته‌ی کوییز، ایموجی دایس، تعداد راند، پنجره‌ی بازی آرکید…)
    options = models.JSONField(verbose_name="گزینه‌ها", default=dict, blank=True)
    # وضعیت لازم برای بازیابی بعد از ری‌استارت
    state = models.JSONField(verbose_name="وضعیت ذخیره‌شده", default=dict, blank=True)
    # فقط بازی‌های آرکید
    token = models.CharField(verbose_name="توکن", max_length=24, unique=True, default=_new_token)
    seed = models.BigIntegerField(verbose_name="seed", default=_new_seed)
    play_deadline = models.DateTimeField(verbose_name="پایان پنجره‌ی بازی", null=True, blank=True)
    cancel_reason = models.CharField(verbose_name="دلیل لغو", max_length=64, blank=True, default="")
    created_at = models.DateTimeField(verbose_name="تاریخ ایجاد", auto_now_add=True)
    started_at = models.DateTimeField(verbose_name="شروع", null=True, blank=True)
    finished_at = models.DateTimeField(verbose_name="پایان", null=True, blank=True)

    class Meta:
        verbose_name = "مسابقه"
        verbose_name_plural = "مسابقات"
        constraints = [
            models.UniqueConstraint(
                fields=["group"],
                condition=Q(status__in=["LOBBY", "RUNNING"]),
                name="one_active_match_per_group",
            ),
            models.CheckConstraint(condition=Q(pot__gte=0), name="match_pot_non_negative"),
        ]
        indexes = [models.Index(fields=["status"]), models.Index(fields=["group", "-finished_at"])]

    def __str__(self) -> str:
        return f"#{self.pk} {self.game_type} [{self.status}]"

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES


class MatchPlayer(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="players", verbose_name="مسابقه")
    user = models.ForeignKey("core.TelegramUser", on_delete=models.PROTECT, related_name="match_entries", verbose_name="کاربر")
    score = models.IntegerField(verbose_name="امتیاز", default=0)
    # لحظه‌ی رسیدن به امتیاز فعلی؛ برای شکستن تساوی
    score_at = models.FloatField(verbose_name="زمان رسیدن به امتیاز", null=True, blank=True)
    rank = models.PositiveSmallIntegerField(verbose_name="رتبه", null=True, blank=True)
    prize = models.BigIntegerField(verbose_name="جایزه", default=0)
    xp_gained = models.PositiveIntegerField(verbose_name="XP دریافتی", default=0)
    paid_fee = models.PositiveIntegerField(verbose_name="ورودی پرداخت‌شده", default=0)
    refunded = models.BooleanField(verbose_name="برگشت داده شد", default=False)
    joined_at = models.DateTimeField(verbose_name="زمان عضویت", auto_now_add=True)

    class Meta:
        verbose_name = "بازیکن مسابقه"
        verbose_name_plural = "بازیکنان مسابقه"
        constraints = [models.UniqueConstraint(fields=["match", "user"], name="unique_match_player")]
        ordering = ["joined_at", "id"]

    def __str__(self) -> str:
        return f"{self.match_id}:{self.user_id}"


class Question(models.Model):
    class Category(models.TextChoices):
        GENERAL = "general", "عمومی"
        FREEFIRE = "freefire", "فری فایر"
        FOOTBALL = "football", "فوتبال"
        MOVIE = "movie", "فیلم"
        SCIENCE = "science", "علمی"

    category = models.CharField(verbose_name="دسته", max_length=32, choices=Category.choices, db_index=True)
    text = models.TextField(verbose_name="متن")
    options = models.JSONField(verbose_name="گزینه‌ها")
    correct_index = models.PositiveSmallIntegerField(verbose_name="اندیس جواب درست")
    difficulty = models.PositiveSmallIntegerField(verbose_name="سختی", default=1)
    is_active = models.BooleanField(verbose_name="فعال", default=True)

    class Meta:
        verbose_name = "سوال"
        verbose_name_plural = "بانک سوال"

    def __str__(self) -> str:
        return self.text[:60]


class WordEntry(models.Model):
    word = models.CharField(verbose_name="کلمه", max_length=32, unique=True)
    category = models.CharField(verbose_name="دسته", max_length=32, blank=True, default="general")
    length = models.PositiveSmallIntegerField(verbose_name="طول", db_index=True)
    difficulty = models.PositiveSmallIntegerField(verbose_name="سختی", default=1)

    class Meta:
        verbose_name = "کلمه"
        verbose_name_plural = "کلمات"

    def __str__(self) -> str:
        return self.word

    def save(self, *args, **kwargs):
        self.length = len(self.word)
        super().save(*args, **kwargs)


class EmojiPuzzle(models.Model):
    emojis = models.CharField(verbose_name="ایموجی‌ها", max_length=64)
    answer = models.CharField(verbose_name="جواب", max_length=64)
    alt_answers = models.JSONField(verbose_name="جواب‌های جایگزین", default=list, blank=True)
    is_active = models.BooleanField(verbose_name="فعال", default=True)

    class Meta:
        verbose_name = "پازل ایموجی"
        verbose_name_plural = "پازل‌های ایموجی"

    def __str__(self) -> str:
        return f"{self.emojis} → {self.answer}"


class TypingSentence(models.Model):
    text = models.CharField(verbose_name="متن", max_length=200, unique=True)
    is_active = models.BooleanField(verbose_name="فعال", default=True)

    class Meta:
        verbose_name = "جمله‌ی تایپ"
        verbose_name_plural = "جمله‌های تایپ"

    def __str__(self) -> str:
        return self.text[:60]


class GameSetting(models.Model):
    """تنظیمات سراسری یک بازی که ادمین از پنل عوض می‌کند (پیش‌فرض‌ها در کلاس خود بازی است)."""

    game_key = models.CharField(verbose_name="کلید بازی", max_length=32, unique=True)
    is_enabled = models.BooleanField(verbose_name="فعال", default=True)
    min_players = models.PositiveSmallIntegerField(verbose_name="حداقل شرکت‌کننده", default=2)
    max_players = models.PositiveSmallIntegerField(verbose_name="حداکثر شرکت‌کننده", default=20)
    updated_at = models.DateTimeField(verbose_name="آخرین تغییر", auto_now=True)

    class Meta:
        verbose_name = "تنظیمات بازی"
        verbose_name_plural = "تنظیمات بازی‌ها"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(min_players__gte=1) & Q(max_players__gte=F("min_players")),
                name="game_setting_players_range",
            ),
        ]

    def __str__(self) -> str:
        from .catalog import defaults

        info = defaults().get(self.game_key)
        return f"{info.emoji} {info.title_fa}" if info else self.game_key

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        config.invalidate()

    def clean(self):
        from .catalog import defaults

        info = defaults().get(self.game_key)
        if info is None:
            raise ValidationError("این بازی در ربات وجود ندارد.")
        errors = {}
        if not info.floor <= self.max_players <= info.ceiling:
            errors["max_players"] = f"برای این بازی باید بین {info.floor} و {info.ceiling} باشد."
        if not info.floor <= self.min_players <= info.ceiling:
            errors["min_players"] = f"برای این بازی باید بین {info.floor} و {info.ceiling} باشد."
        elif self.min_players > self.max_players:
            errors["min_players"] = "حداقل نمی‌تواند از حداکثر بیشتر باشد."
        if errors:
            raise ValidationError(errors)
