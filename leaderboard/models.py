from django.db import models


class Achievement(models.Model):
    code = models.CharField(verbose_name="کد", max_length=40, unique=True)
    title = models.CharField(verbose_name="عنوان", max_length=80)
    description = models.CharField(verbose_name="توضیح", max_length=200, blank=True, default="")
    emoji = models.CharField(verbose_name="ایموجی", max_length=8, default="🏅")
    reward_coins = models.PositiveIntegerField(verbose_name="جایزه (سکه)", default=0)

    class Meta:
        verbose_name = "دستاورد"
        verbose_name_plural = "دستاوردها"

    def __str__(self) -> str:
        return f"{self.emoji} {self.title}"


class UserAchievement(models.Model):
    user = models.ForeignKey("core.TelegramUser", on_delete=models.CASCADE, related_name="achievements", verbose_name="کاربر")
    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE, related_name="holders", verbose_name="دستاورد")
    created_at = models.DateTimeField(verbose_name="تاریخ ایجاد", auto_now_add=True)

    class Meta:
        verbose_name = "دستاورد کاربر"
        verbose_name_plural = "دستاوردهای کاربران"
        constraints = [models.UniqueConstraint(fields=["user", "achievement"], name="unique_user_achievement")]


class WeeklyChampion(models.Model):
    """قهرمان هفته‌ی هر گروه؛ برای اینکه اعلام هفتگی فقط یک بار انجام شود."""

    group = models.ForeignKey("core.TelegramGroup", on_delete=models.CASCADE, related_name="champions", verbose_name="گروه")
    week_start = models.DateField(verbose_name="شروع هفته")
    user = models.ForeignKey("core.TelegramUser", null=True, on_delete=models.SET_NULL, verbose_name="کاربر")
    coins_won = models.BigIntegerField(verbose_name="سکه‌ی برده", default=0)
    wins = models.PositiveIntegerField(verbose_name="برد", default=0)
    announced_at = models.DateTimeField(verbose_name="زمان اعلام", auto_now_add=True)

    class Meta:
        verbose_name = "قهرمان هفته"
        verbose_name_plural = "قهرمان‌های هفته"
        constraints = [models.UniqueConstraint(fields=["group", "week_start"], name="unique_group_week")]
